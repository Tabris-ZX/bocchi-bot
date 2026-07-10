from bocchi.services.ai.tools.core.toolkit import BaseToolkit


class BaseKnowledge(BaseToolkit):
    """
    知识库基类。
    继承自 BaseToolkit，允许知识库向 Agent 提供自定义的检索工具（如搜索、读取）。
    """

    pass
