"""QQ group daily analysis plugin for NoneBot 2 and OneBot v11."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import time
from typing import Any

from nonebot import get_driver, on_command, require
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_apscheduler")
require("nonebot_plugin_alconna")
require("nonebot_plugin_session")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_waiter")

from bocchi.configs.path_config import DATA_PATH
from bocchi.configs.utils import PluginExtraData, RegisterConfig

from .nonebot_config import CONFIG_KEY, MODULE_NAME, BocchiPluginConfig, load_defaults
from .nonebot_host import KVStoreHost, NoneBotManager, html_render, scheduler_context
from .src.application.services.analysis_application_service import (
    AnalysisApplicationService,
    DuplicateGroupTaskError,
)
from .src.domain.services.analysis_domain_service import AnalysisDomainService
from .src.domain.services.incremental_merge_service import IncrementalMergeService
from .src.domain.services.statistics_service import StatisticsService
from .src.infrastructure.analysis.llm_analyzer import LLMAnalyzer
from .src.infrastructure.config.config_manager import ConfigManager
from .src.infrastructure.messaging.message_sender import MessageSender
from .src.infrastructure.persistence.history_manager import HistoryManager
from .src.infrastructure.persistence.incremental_store import IncrementalStore
from .src.infrastructure.reporting.generators import ReportGenerator
from .src.infrastructure.scheduler.auto_scheduler import AutoScheduler
from .src.shared.trace_context import TraceContext
from .src.utils.logger import logger
from .src.utils.resilience import GlobalRateLimiter

__plugin_meta__ = PluginMetadata(
    name="群日常分析",
    description="分析 QQ 群聊记录并生成话题、群友画像、金句与活跃度日报",
    usage=(
        "群分析 [天数]\n"
        "设置格式 [image|text|html]\n"
        "设置模板 [模板名|序号]\n"
        "查看模板\n"
        "分析设置 [enable|disable|status|reload|test|incremental_debug]\n"
        "增量状态"
    ),
    type="application",
    supported_adapters={"~onebot.v11"},
    extra=PluginExtraData(
        author="",
        version="",
        admin_level=5,
        configs=[
            RegisterConfig(
                module=MODULE_NAME,
                key=CONFIG_KEY,
                value=load_defaults(),
                default_value=load_defaults(),
                type=dict,
                help="群日常分析完整配置（沿用原插件分组结构）",
            )
        ],
    ).dict(),
)


class DailyAnalysisRuntime(KVStoreHost):
    def __init__(self) -> None:
        super().__init__()
        self.config = BocchiPluginConfig.load()
        self.config_manager = ConfigManager(self.config)
        self.bot_manager = NoneBotManager(self.config_manager)
        plugin_data_dir = DATA_PATH / MODULE_NAME
        self.history_manager = HistoryManager(self)
        self.report_generator = ReportGenerator(self.config_manager, plugin_data_dir)
        self.statistics_service = StatisticsService()
        self.analysis_domain_service = AnalysisDomainService()
        self.llm_analyzer = LLMAnalyzer(None, self.config_manager)
        self.incremental_store = IncrementalStore(self)
        self.incremental_merge_service = IncrementalMergeService()
        self.analysis_service = AnalysisApplicationService(
            self.config_manager,
            self.bot_manager,
            self.history_manager,
            self.report_generator,
            self.llm_analyzer,
            self.statistics_service,
            self.analysis_domain_service,
            incremental_store=self.incremental_store,
            incremental_merge_service=self.incremental_merge_service,
        )
        self.message_sender = MessageSender(self.bot_manager, self.config_manager)
        self.context = scheduler_context()
        self.auto_scheduler = AutoScheduler(
            self.config_manager,
            self.analysis_service,
            self.bot_manager,
            self.report_generator,
            html_render,
            plugin_instance=self,
        )
        self._scheduled = False
        GlobalRateLimiter.get_instance(self.config_manager.get_llm_max_concurrent())

    async def register_bot(self, bot: Bot) -> str:
        platform_id = self.bot_manager.register(bot)
        if not self._scheduled:
            self.auto_scheduler.schedule_jobs(self.context)
            self._scheduled = True
        return platform_id

    async def shutdown(self) -> None:
        self.auto_scheduler.unschedule_jobs(self.context)
        await self.report_generator.close()
        self.close()

    async def send_report(self, result: dict[str, Any]) -> None:
        group_id = result["group_id"]
        platform_id = result["platform_id"]
        analysis_result = result["analysis_result"]
        adapter = result["adapter"]
        output_format = self.config_manager.get_output_format()

        async def avatar_url_getter(user_id: str) -> str | None:
            return await adapter.get_user_avatar_url(user_id)

        async def nickname_getter(user_id: str) -> str | None:
            member = await adapter.get_member_info(group_id, user_id)
            return (member.card or member.nickname) if member else None

        if output_format == "image":
            image_path, _ = await self.report_generator.generate_image_report(
                analysis_result,
                group_id,
                html_render,
                avatar_url_getter=avatar_url_getter,
                nickname_getter=nickname_getter,
                avatar_cache_namespace=platform_id,
            )
            if image_path and await adapter.send_image(
                group_id, image_path, TraceContext.make_report_caption()
            ):
                return
            logger.warning(f"群 {group_id} 图片报告发送失败，回退到文本")

        elif output_format == "html":
            html_path, _ = await self.report_generator.generate_html_report(
                analysis_result,
                group_id,
                avatar_url_getter=avatar_url_getter,
                nickname_getter=nickname_getter,
                avatar_cache_namespace=platform_id,
            )
            if html_path:
                if self.config_manager.get_html_only_url():
                    base_url = self.config_manager.get_html_base_url()
                    if base_url:
                        output_dir = self.config_manager.get_html_output_dir() or str(
                            DATA_PATH / MODULE_NAME / "self_hosted_html_reports"
                        )
                        relative = os.path.relpath(html_path, output_dir).replace(
                            os.sep, "/"
                        )
                        report_url = f"{base_url.rstrip('/')}/{relative}"
                        if await adapter.send_text(
                            group_id, f"📊 今日群聊分析报告：\n{report_url}"
                        ):
                            return
                if await self.message_sender.send_file(
                    group_id,
                    html_path,
                    self.report_generator.build_html_caption(html_path),
                    platform_id,
                ):
                    return
            logger.warning(f"群 {group_id} HTML 报告发送失败，回退到文本")

        text_report = self.report_generator.generate_text_report(analysis_result)
        await adapter.send_text_report(group_id, text_report)


runtime = DailyAnalysisRuntime()
driver = get_driver()
admin_permission = SUPERUSER | GROUP_ADMIN | GROUP_OWNER


@driver.on_bot_connect
async def _on_bot_connect(bot: Bot) -> None:
    if isinstance(bot, Bot):
        await runtime.register_bot(bot)
        logger.info(f"OneBot {bot.self_id} 已接入群日常分析")


@driver.on_bot_disconnect
async def _on_bot_disconnect(bot: Bot) -> None:
    if isinstance(bot, Bot):
        runtime.bot_manager.unregister(bot)


@driver.on_shutdown
async def _on_shutdown() -> None:
    await runtime.shutdown()


analyze_cmd = on_command(
    "群分析", aliases={"group_analysis"}, permission=admin_permission, block=True
)
format_cmd = on_command(
    "设置格式", aliases={"set_format"}, permission=admin_permission, block=True
)
template_cmd = on_command(
    "设置模板", aliases={"set_template"}, permission=admin_permission, block=True
)
template_view_cmd = on_command(
    "查看模板", aliases={"view_templates"}, permission=admin_permission, block=True
)
settings_cmd = on_command(
    "分析设置", aliases={"analysis_settings"}, permission=admin_permission, block=True
)
incremental_cmd = on_command(
    "增量状态", aliases={"incremental_status"}, permission=admin_permission, block=True
)


def _argument_text(argument: Message) -> str:
    return argument.extract_plain_text().strip()


async def _prepare(bot: Bot, event: GroupMessageEvent) -> tuple[str, str]:
    platform_id = await runtime.register_bot(bot)
    return str(event.group_id), platform_id


@analyze_cmd.handle()
async def _analyze(
    bot: Bot, event: GroupMessageEvent, argument: Message = CommandArg()
) -> None:
    group_id, platform_id = await _prepare(bot, event)
    target = f"{platform_id}:GroupMessage:{group_id}"
    if not runtime.config_manager.is_group_allowed(target):
        await analyze_cmd.finish("❌ 此群未启用日常分析功能")
    days_text = _argument_text(argument)
    try:
        days = int(days_text) if days_text else None
        if days is not None and days <= 0:
            raise ValueError
    except ValueError:
        await analyze_cmd.finish("❌ 天数必须是正整数")

    adapter = runtime.bot_manager.get_adapter(platform_id)
    group_info = await adapter.get_group_info(group_id) if adapter else None
    TraceContext.set(
        TraceContext.generate(
            "manual", (group_info.group_name if group_info else group_id)
        )
    )
    await analyze_cmd.send("🔍 正在拉取群聊记录并生成分析报告...")
    try:
        result = await runtime.analysis_service.execute_daily_analysis(
            group_id, platform_id, manual=True, days=days
        )
        if not result.get("success"):
            reason = result.get("reason")
            message = {
                "no_messages": "❌ 未找到足够的群聊记录",
                "muted": "❌ Bot 当前在群内被禁言",
            }.get(reason, f"❌ 分析未完成：{reason or '未知原因'}")
            await analyze_cmd.finish(message)
        await runtime.send_report(result)
    except DuplicateGroupTaskError:
        await analyze_cmd.finish("📊 该群的分析任务正在执行中，请稍后再试")
    except Exception as exc:
        logger.exception(f"手动群分析失败: {exc}")
        await analyze_cmd.finish(f"❌ 分析失败：{exc}")


@format_cmd.handle()
async def _set_format(argument: Message = CommandArg()) -> None:
    value = _argument_text(argument).lower()
    formats = ["image", "text", "html"]
    if not value:
        await format_cmd.finish(
            f"📊 当前格式：{runtime.config_manager.get_output_format()}\n"
            "可用格式：1. image  2. text  3. html"
        )
    if value.isdigit() and 1 <= int(value) <= len(formats):
        value = formats[int(value) - 1]
    if value not in formats:
        await format_cmd.finish("❌ 可用格式为 image、text、html（或序号 1-3）")
    runtime.config_manager.set_output_format(value)
    await format_cmd.finish(f"✅ 输出格式已设置为：{value}")


def _templates() -> list[str]:
    root = Path(__file__).parent / "src/infrastructure/reporting/templates"
    return sorted(path.name for path in root.iterdir() if path.is_dir())


@template_cmd.handle()
async def _set_template(argument: Message = CommandArg()) -> None:
    value = _argument_text(argument)
    templates = _templates()
    if not value:
        listing = "\n".join(f"{i}. {name}" for i, name in enumerate(templates, 1))
        await template_cmd.finish(
            f"🎨 当前模板：{runtime.config_manager.get_report_template()}\n{listing}"
        )
    if value.isdigit() and 1 <= int(value) <= len(templates):
        value = templates[int(value) - 1]
    if value not in templates:
        await template_cmd.finish(f"❌ 模板不存在：{value}")
    runtime.config_manager.set_report_template(value)
    await template_cmd.finish(f"✅ 报告模板已设置为：{value}")


@template_view_cmd.handle()
async def _view_templates(bot: Bot, event: GroupMessageEvent) -> None:
    templates = _templates()
    current = runtime.config_manager.get_report_template()
    nodes: list[dict[str, Any]] = [
        {
            "type": "node",
            "data": {
                "name": "模板预览",
                "uin": str(bot.self_id),
                "content": f"可用报告模板（当前：{current}）",
            },
        }
    ]
    for index, name in enumerate(templates, 1):
        content: list[dict[str, Any]] = [
            {"type": "text", "data": {"text": f"{index}. {name}"}}
        ]
        preview = Path(__file__).parent / "assets" / f"{name}-demo.jpg"
        if preview.exists():
            content.append(
                {"type": "image", "data": {"file": f"file://{preview.resolve()}"}}
            )
        nodes.append(
            {
                "type": "node",
                "data": {"name": name, "uin": str(bot.self_id), "content": content},
            }
        )
    await bot.call_api(
        "send_group_forward_msg", group_id=event.group_id, messages=nodes
    )


@settings_cmd.handle()
async def _settings(
    bot: Bot, event: GroupMessageEvent, argument: Message = CommandArg()
) -> None:
    group_id, platform_id = await _prepare(bot, event)
    action = _argument_text(argument).lower() or "status"
    target = f"{platform_id}:GroupMessage:{group_id}"
    mode = runtime.config_manager.get_group_list_mode()
    groups = runtime.config_manager.get_group_list()

    if action in {"enable", "disable"}:
        enable = action == "enable"
        changed = False
        if mode == "whitelist":
            should_contain = enable
        elif mode == "blacklist":
            should_contain = not enable
        else:
            await settings_cmd.finish(
                "ℹ️ 当前为无限制模式；请先在插件配置中切换白名单或黑名单模式"
            )
        matching = [item for item in groups if str(item) in {target, group_id}]
        if should_contain and not matching:
            groups.append(target)
            changed = True
        elif not should_contain and matching:
            groups[:] = [item for item in groups if item not in matching]
            changed = True
        if changed:
            runtime.config_manager.set_group_list(groups)
            runtime.auto_scheduler.schedule_jobs(runtime.context)
        await settings_cmd.finish(
            f"✅ 当前群分析已{'启用' if enable else '禁用'}"
            if changed
            else "ℹ️ 当前群设置无需变更"
        )

    if action == "reload":
        runtime.config.reload_config()
        runtime.auto_scheduler.schedule_jobs(runtime.context)
        await settings_cmd.finish("✅ 配置已重新加载，定时任务已重建")
    if action == "test":
        if not runtime.config_manager.is_group_allowed(target):
            await settings_cmd.finish("❌ 请先启用当前群的分析功能")
        await settings_cmd.send("🧪 开始测试自动分析...")
        await runtime.auto_scheduler._perform_auto_analysis_for_group(
            group_id, platform_id
        )
        await settings_cmd.finish("✅ 自动分析测试完成")
    if action == "incremental_debug":
        enabled = not runtime.config_manager.get_incremental_report_immediately()
        runtime.config_manager.set_incremental_report_immediately(enabled)
        await settings_cmd.finish(
            f"✅ 增量立即报告模式已{'开启' if enabled else '关闭'}"
        )
    if action != "status":
        await settings_cmd.finish(
            "❌ 可用操作：enable、disable、status、reload、test、incremental_debug"
        )

    allowed = runtime.config_manager.is_group_allowed(target)
    incremental = runtime.config_manager.get_incremental_enabled()
    auto_enabled = runtime.config_manager.is_auto_analysis_enabled()
    await settings_cmd.finish(
        "📊 当前群分析状态\n"
        f"• 群分析：{'已启用' if allowed else '未启用'}（{mode}）\n"
        f"• 自动分析：{'已启用' if auto_enabled else '未启用'}\n"
        f"• 执行时间：{runtime.config_manager.get_auto_analysis_time()}\n"
        f"• 增量分析：{'已启用' if incremental else '未启用'}\n"
        f"• 输出格式：{runtime.config_manager.get_output_format()}\n"
        f"• 最小消息数：{runtime.config_manager.get_min_messages_threshold()}"
    )


@incremental_cmd.handle()
async def _incremental(event: GroupMessageEvent) -> None:
    if not runtime.config_manager.get_incremental_enabled():
        await incremental_cmd.finish("ℹ️ 增量分析模式未启用")
    group_id = str(event.group_id)
    window_end = time.time()
    window_start = window_end - runtime.config_manager.get_analysis_days() * 86400
    batches = await runtime.incremental_store.query_batches(
        group_id, window_start, window_end
    )
    if not batches:
        start = datetime.fromtimestamp(window_start).strftime("%m-%d %H:%M")
        end = datetime.fromtimestamp(window_end).strftime("%m-%d %H:%M")
        await incremental_cmd.finish(f"📊 滑动窗口（{start} ~ {end}）内尚无数据")
    state = runtime.incremental_merge_service.merge_batches(
        batches, window_start, window_end
    )
    summary = state.get_summary()
    await incremental_cmd.finish(
        f"📊 增量分析状态（{summary['window']}）\n"
        f"• 分析次数：{summary['total_analyses']}\n"
        f"• 累计消息：{summary['total_messages']}\n"
        f"• 话题数：{summary['topics_count']}\n"
        f"• 金句数：{summary['quotes_count']}\n"
        f"• 参与者：{summary['participants']}\n"
        f"• 高峰时段：{summary['peak_hours']}"
    )
