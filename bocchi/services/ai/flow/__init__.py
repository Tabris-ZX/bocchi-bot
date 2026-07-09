"""
bocchi AI - Flow (核心编排引擎)

提供大模型任务编排的三大范式：
1. Agent: 基于动态工具调用的自主推理流。
2. Team: 多智能体协同的群体决策流。
3. Workflow: 基于图元/状态机的静态控制流。
"""

from .agent.agent import Agent
from .team.team import Team
from .workflow.engine import Workflow

__all__ = [
    "Agent",
    "Team",
    "Workflow",
]
