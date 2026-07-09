from typing import ClassVar
from typing_extensions import Self

from tortoise import fields

from bocchi.services.db_context import Model
from bocchi.services.log import logger
from bocchi.utils.enum import CacheType, DbLockType


class NjuitStu(Model):
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增主键"""
    user_id = fields.CharField(255, null=False, unique=True)
    """用户ID"""
    class_name = fields.CharField(255, null=True)  # 使用 class_name 避免与 Python 关键字冲突
    """班级"""
    dorm_id = fields.CharField(255, null=True)
    """宿舍号"""
    push = fields.BooleanField(default=False)
    """是否推送通知（布尔型）"""

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "njuit_stu"
        table_description = "南工院学生信息表"
        indexes = [("user_id",), ("dorm_id",)]  # 常用查询字段索引

    cache_type = CacheType.USERS  # 根据实际需求调整缓存类型
    """缓存类型"""
    cache_key_field = "user_id"
    """缓存键字段"""
    enable_lock: ClassVar[list[DbLockType]] = [DbLockType.CREATE, DbLockType.UPSERT]
    """开启锁"""

    @classmethod
    async def get_data(cls, user_id: str | None) -> Self | None:
        """获取单条学生数据"""
        if not user_id:
            return None
        return await cls.safe_get_or_none(user_id=user_id)

    @classmethod
    async def update_push_status(
        cls, user_id: str, status: bool
    ) -> bool:
        """更新推送状态"""
        student = await cls.get_data(user_id)
        if student:
            student.push = status
            await student.save()
            logger.debug(f"更新推送状态: {status}", target=f"{user_id}")
            return True
        return False

    @classmethod
    async def get_dorm_mates(cls, dorm_id: str) -> list[Self]:
        """获取同宿舍学生列表"""
        return await cls.filter(dorm_id=dorm_id).all()

    @classmethod
    async def _run_script(cls):
        """初始化数据库索引（可选）"""
        return [
            "CREATE INDEX idx_njuit_stu_user_id ON njuit_stu(user_id);",
            "CREATE INDEX idx_njuit_stu_dorm_id ON njuit_stu(dorm_id);",
        ]