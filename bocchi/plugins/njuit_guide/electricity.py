import re
import httpx
import asyncio
import smtplib
from pathlib import Path
from typing import Optional
from email.mime.text import MIMEText
from email.utils import formataddr
from nonebot import get_bot
from bocchi import ui

from bocchi.configs.path_config import DATA_PATH, THEMES_PATH
from bocchi.services.log import logger
from nonebot_plugin_uninfo import get_interface

from .config import njuit_config
from .model import NjuitStu


FILE_PATH = DATA_PATH / "njuit_guide"
TEMPLATES_PATH = THEMES_PATH / "default" / "templates" /"pages"/"extra"/ "njuit_guide"
CLASS_NAME_PATTERN = re.compile(r"^[^\d\s]{2}(\d{2})\d{2}$")


class Electricity:
    """电费相关服务类"""

    @classmethod
    def _generate_user_html(cls, user: dict) -> str:
        """生成单个用户的HTML"""
        avatar_html = f'<img src="{user.get("avatar", "")}" class="user-avatar" onerror="this.style.display=\'none\'">' if user.get('avatar') else ''
        
        if user['error']:
            return f'''
            <div class="user-item error-item">
                <div class="user-info">
                    {avatar_html}
                    <div class="user-name">{user['name']}</div>
                </div>
                <div class="balance-info">
                    <span class="balance-label">电费余额</span>
                    <span class="balance-amount error-amount">{user['balance']}</span>
                </div>
            </div>
            '''
        
        # 根据余额判断样式
        balance_class = "high" if user['value'] >= 50 else "medium" if user['value'] >= 20 else "low"
        
        return f'''
        <div class="user-item">
            <div class="user-info">
                {avatar_html}
                <div class="user-name">{user['name']}</div>
            </div>
            <div class="balance-info">
                <span class="balance-label">电费余额</span>
                <span class="balance-amount {balance_class}">{user['balance']}</span>
            </div>
        </div>
        '''

    @classmethod
    async def _get_electricity_balance(cls, dorm_id: str) -> dict:
        """获取宿舍电费余额信息"""
        try:
            async with httpx.AsyncClient(headers=njuit_config.bill_header, timeout=30.0) as client:
                response = await client.get(f"{njuit_config.bill_url}roomAccountID={dorm_id}")
                response.raise_for_status()
                html = response.text
                
                balance_match = re.search(
                    r'可用余额</label>\s*<span class="weui-form-preview__value">([^<]+)',
                    html
                )
                
                if balance_match:
                    balance_raw = balance_match.group(1).strip()
                    try:
                        match = re.search(r'[\d.]+', balance_raw)
                        if match:
                            balance_value = float(match.group())
                            return {
                                'balance': f"{balance_value:.2f}元",
                                'value': balance_value,
                                'error': False
                            }
                    except ValueError:
                        pass
                    return {'balance': balance_raw, 'value': 0, 'error': False}
                else:
                    return {'balance': '查询失败', 'value': 0, 'error': True}
                    
        except Exception as e:
            logger.error(f"查询宿舍 {dorm_id} 电费失败: {e}")
            return {'balance': '查询失败', 'value': 0, 'error': True}
    
    @classmethod
    async def validate_dorm_id(cls, dorm_id: str) -> bool:
        """验证宿舍ID是否有效（能正常查询电费）"""
        balance_info = await cls._get_electricity_balance(dorm_id)
        return not balance_info['error']

    @classmethod
    async def validate_class_name(cls, class_name: str) -> bool:
        """验证班级名是否符合命名规则"""
        match = CLASS_NAME_PATTERN.fullmatch(class_name)
        if not match:
            return False
        return int(match.group(1)) <= 28

    @classmethod
    async def bind_info(cls, user_id, class_name=None, dorm_id=None) -> bool:
        """绑定用户信息（包含班级和宿舍验证）"""
        try:
            # 过滤空字符串，转换为None
            class_name = class_name if class_name else None
            dorm_id = dorm_id if dorm_id else None

            # 如果提供了班级名，先验证班级格式是否有效
            if class_name:
                if not await cls.validate_class_name(class_name):
                    logger.warning(f"班级 {class_name} 验证失败")
                    return False
            
            # 如果提供了宿舍ID，先验证宿舍是否有效
            if dorm_id:
                if not await cls.validate_dorm_id(dorm_id):
                    logger.warning(f"宿舍 {dorm_id} 验证失败，无法查询电费余额")
                    return False
            
            #todo 仅绑定一项时会使另一项变空

            # 仅使用 user_id 作为键
            await NjuitStu.update_or_create(
                user_id=user_id,
                defaults={
                    'class_name': class_name,
                    'dorm_id': dorm_id,
                    'push': True
                }
            )
            logger.info(f"绑定信息成功: user_id={user_id}, dorm_id={dorm_id}")
            return True
        except Exception as e:
            logger.error(f"绑定信息失败: {e}")
            return False

    @classmethod
    async def query_balance(cls, user_id):
        """查询用户宿舍电费余额"""
        data = await NjuitStu.get_data(user_id=user_id)
        if not data or not data.dorm_id:
            dorm_id_path = FILE_PATH/"dorm_id.png"
            return ["你还没有绑定宿舍捏~ \n私聊小波奇发送\n南工绑定  dorm  宿舍id\n来绑定宿舍吧~",dorm_id_path]
        
        balance_info = await cls._get_electricity_balance(data.dorm_id)
        if balance_info['error']:
            return "网络开小差了，请稍后再试~"
        
        return f"你宿舍的电费还有{balance_info['balance']}呢"

    @classmethod
    async def get_daily_electricity_reminder_for_group(cls, group_id: str) -> Optional[Path]:
        """获取指定群组的电费提醒消息内容"""
        try:
            bot = get_bot()
            # 获取群中开启推送的用户
            group_members = await bot.get_group_member_list(group_id=int(group_id))
            member_ids = [str(member['user_id']) for member in group_members]
            njuit_users = await NjuitStu.filter(push=True, user_id__in=member_ids, dorm_id__isnull=False).all()
            if not njuit_users:
                return None
            
            # 收集群中用户的电费信息
            users_data = []
            interface = get_interface(bot)
            if not interface:
                return None
            for user in njuit_users:
                try:
                    fetch_user = await asyncio.wait_for(interface.get_user(user.user_id), timeout=2.0)
                    if fetch_user is None:
                        continue
                    name = getattr(fetch_user, "name", None)
                    avatar = getattr(fetch_user, "avatar", None)
                    balance_info = await cls._get_electricity_balance(user.dorm_id)
                    users_data.append({
                        'name': name or f'用户{user.user_id}',
                        'avatar': avatar or '',
                        'balance': balance_info['balance'],
                        'value': balance_info['value'],
                        'error': balance_info['error']
                    })
                except Exception as e:
                    logger.warning(f"获取用户 {user.user_id} 信息失败: {e}")
                    continue
            # 按电费余额升序排序，异常项置后
            try:
                users_data.sort(key=lambda u: (u.get('error', False), u.get('value', float('inf'))))
            except Exception:
                pass

            return await cls.generate_electricity_image(users_data) if users_data else None
                
        except Exception as e:
            logger.error(f"获取群组 {group_id} 电费提醒失败: {e}")
            return None

    @classmethod
    async def generate_electricity_image(cls, user_data: list) -> Optional[Path]:
        """生成电费提醒的图片（统一UI渲染）"""
        try:
            # 生成内容区域html
            content_html = "".join(cls._generate_user_html(user) for user in user_data)
            # 使用UI统一渲染
            image_bytes = await ui.render_template(
                "pages/extra/njuit_guide/electricity_template.html",
                data={"content": content_html},
                viewport={"width": 400, "height": 10},
            )

            # 兼容原有返回文件路径的调用方：写入到固定路径后返回
            save_path = FILE_PATH / "electricity_reminder.jpg"
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(image_bytes)
            return save_path
                
        except Exception as e:
            logger.error(f"生成电费图片失败: {e}")
            return None
    
    @classmethod
    async def check_low_balance_and_send_email(cls,threshold=15.0):
        """检查电费不足用户并发送邮件提醒，返回发送邮件数量"""
        try:
            # 获取所有开启推送且有宿舍ID的用户
            users = await NjuitStu.filter(push=True, dorm_id__isnull=False).all()
            if not users:
                logger.info("没有开启推送的用户需要检查电费")
                return 0
            
            sent_count = 0
            for user in users:
                try:
                    # 查询电费余额
                    balance_info = await Electricity._get_electricity_balance(user.dorm_id)
                    if balance_info['error'] or balance_info['value'] >= threshold:
                        continue
                    
                    # 发送邮件提醒
                    subject = f"电费不足提醒"
                    import textwrap
                    content = textwrap.dedent(f"""
                        呜……那、那个……
                        我刚刚查了一下你的电费余额，好像还剩 {balance_info['balance']}……
                        要、要注意别花太多了呀(>_<)
                    """)
                    
                    email = f"{user.user_id}@qq.com"
                    
                    success = cls.send_mail(email, content)
                    if success:
                        sent_count += 1
                        logger.info(f"电费不足邮件已发送给用户 {user.user_id}，宿舍 {user.dorm_id}")
                    
                except Exception as e:
                    logger.error(f"处理用户 {user.user_id} 电费检查失败: {e}")
                    continue
            
            logger.info(f"电费不足邮件发送完成，共发送 {sent_count} 封邮件")
            return sent_count
            
        except Exception as e:
            logger.error(f"检查电费不足并发送邮件失败: {e}")
            return 0

    @classmethod
    def send_mail(cls,to, text, subject="你的电费好像不太够了啊..."):
        """发送邮件（同步方式，忽略 QQ SMTP 伪错误）"""
        sender_email = '3541219424@qq.com'

        msg = MIMEText(text, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = formataddr(('可爱的小波奇', sender_email))
        msg['To'] = to

        try:
            with smtplib.SMTP_SSL('smtp.qq.com', 465, timeout=10) as s:
                s.login(sender_email, "qkznleckjvhtchce")
                s.sendmail(sender_email, to, msg.as_string())
            print(f"✅ 邮件发送成功: {to}")
            return True

        except smtplib.SMTPResponseException as e:
            if e.smtp_code == -1 and e.smtp_error == b'\x00\x00\x00':
                print(f"✅ 邮件发送成功: {to}")
                return True
            else:
                print(f"❌ 邮件发送失败: {to}, 错误: {e}")
                return False

        except Exception as e:
            print(f"❌ 邮件发送失败: {to}, 错误: {e}")
            return False
