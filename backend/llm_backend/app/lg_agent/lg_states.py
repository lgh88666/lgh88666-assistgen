from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from typing import Annotated, Literal, TypedDict, List
from langchain_core.messages import AnyMessage
from langgraph.graph import add_messages


class Router(TypedDict):
    """标准化用户提问."""
    logic: str
    type: Literal["general-query", "additional-query", "graphrag-query", "image-query", "file-query"]
    question: str = field(default_factory=str)

class GradeHallucinations(BaseModel):
    """判断生成的回答里有没有瞎编（幻觉），给出是 / 否的评分结果"""

    binary_score: str = Field(
        description="Answer is grounded in the facts, '1' or '0'"
    )

# Agent 输入状态：仅包含消息列表，外部调用者通过此状态向 Agent 传递用户输入
@dataclass(kw_only=True)
class InputState:
    """Agent 的输入状态，定义用户与 Agent 之间交换的消息结构。"""

    messages: Annotated[list[AnyMessage], add_messages]
    """消息列表，通过 add_messages reducer 合并新旧消息，相同 ID 的消息会被替换，否则追加。"""

# Agent 完整状态：继承 InputState，增加路由分类、步骤记录、问题/答案及幻觉检测等字段
@dataclass(kw_only=True)
class AgentState(InputState):
    """检索图/Agent 的完整状态。"""
    router: Router = field(default_factory=lambda: Router(type="general-query", logic=""))
    """LLM 对用户查询的分类结果。"""
    steps: list[str] = field(default_factory=list)
    """检索器填充的文档列表，供 Agent 参考。"""
    question: str = field(default_factory=str)
    """当前用户问题。"""
    answer: str = field(default_factory=str)
    """当前生成的回答。"""
    hallucination: GradeHallucinations = field(default_factory=lambda: GradeHallucinations(binary_score="0"))
    """幻觉检测结果，0 表示无幻觉，1 表示存在幻觉。"""
