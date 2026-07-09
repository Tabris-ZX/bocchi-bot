"""
LLM 服务内部状态与配置数据模型。
"""

from enum import Enum

from pydantic import BaseModel, Field


class HttpClientConfig(BaseModel):
    """HTTP 客户端底层连接池配置"""

    timeout: int = 180
    """请求超时时间（秒）"""
    max_connections: int = 100
    """连接池最大允许的总连接数"""
    max_keepalive_connections: int = 20
    """连接池允许保持复用的最大 Keep-Alive 连接数"""


class RouteHealthState(str, Enum):
    """模型路由级别健康状态枚举"""

    CLOSED = "CLOSED"
    """闭合状态：健康正常，放行所有请求"""
    OPEN = "OPEN"
    """打开状态：熔断器已触发，拒绝所有请求"""
    HALF_OPEN = "HALF_OPEN"
    """半开状态：冷却期结束，允许少量探活请求试探服务是否恢复"""


class KeyHealthStatus(BaseModel):
    """API 密钥凭证级别的详细状态信息"""

    status: str = "HEALTHY"
    """当前密钥的健康状态 (HEALTHY, WARNING, COOLDOWN, DISABLED 等)"""
    successes: int = 0
    """该密钥请求成功的总次数"""
    failures: int = 0
    """该密钥请求失败的总次数"""
    cooldown_until: float = 0.0
    """冷却解锁的 Unix 时间戳，0.0 表示无冷却"""
    last_error: str | None = None
    """最近一次请求失败记录的错误原因"""


class RouteHealthStatus(BaseModel):
    """模型路由级别的遥测与熔断状态信息"""

    state: RouteHealthState = RouteHealthState.CLOSED
    """当前路由节点的熔断器状态"""
    cooldown_until: float = 0.0
    """熔断器探活冷却解锁的 Unix 时间戳"""
    success_rate: float = 100.0
    """该路由的请求成功率百分比 (0.0 - 100.0)"""
    successes: int = 0
    """该路由请求成功的总次数"""
    failures: int = 0
    """该路由请求失败的总次数"""
    latency_ema: float = 0.0
    """平滑指数移动平均 (EMA) 的响应延迟预估值（毫秒）"""
    last_error: str | None = None
    """该路由最近一次发生服务端故障的错误原因"""


class ProviderHealthStatus(BaseModel):
    """单一提供商（服务商）的综合健康状态"""

    api_keys: dict[str, KeyHealthStatus] = Field(default_factory=dict)
    """该提供商下绑定的所有 API 密钥状态映射表"""


class GlobalHealthState(BaseModel):
    """全局 AI 服务遥测与健康状态基座持久化模型"""

    providers: dict[str, ProviderHealthStatus] = Field(default_factory=dict)
    """所有提供商维度的状态映射表"""
    routes: dict[str, RouteHealthStatus] = Field(default_factory=dict)
    """所有模型路由端点维度的状态映射表"""


class CircuitBreakerPolicy(BaseModel):
    """熔断器与密钥冷却策略配置"""

    rate_limit_cooldown: int = Field(default=60)
    """被限流时的短时冷却时间（秒）"""
    auth_error_cooldown: int = Field(default=31536000)
    """凭证错误/鉴权失败时的长时冷却（默认1年即为禁用）"""
    server_error_cooldown: int = Field(default=120)
    """服务端发生崩溃(500)等异常时的模型节点熔断时间（秒）"""
    quota_error_cooldown: int = Field(default=3600)
    """API 额度耗尽时的冷却时间（秒）"""


class RetryConfig:
    """请求重试与轮询策略配置"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True,
        key_rotation: bool = True,
    ):
        self.max_retries = max_retries
        """发生可恢复异常时的最大重试次数"""
        self.retry_delay = retry_delay
        """基础重试等待延迟（秒）"""
        self.exponential_backoff = exponential_backoff
        """是否启用指数退避策略（延迟时间随重试次数翻倍）"""
        self.key_rotation = key_rotation
        """发生凭证错误或限流时，是否自动轮换到下一个可用的 API Key"""
