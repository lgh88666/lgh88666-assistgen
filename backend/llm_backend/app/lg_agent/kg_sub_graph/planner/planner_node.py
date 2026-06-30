from typing import Any, Callable, Coroutine, Dict

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables.base import Runnable
from typing import Annotated, Any, Dict, List, Optional

from pydantic import BaseModel, Field
from typing_extensions import TypedDict
from app.lg_agent.kg_sub_graph.kg_states import CypherOutputState

from langchain_core.prompts import ChatPromptTemplate


planner_system = """
        你必须分析输入问题并将其分解为单独的子任务。
        如果存在适当的独立任务，则将其作为列表提供，否则返回空列表。
        任务不应该相互依赖。
        返回要完成的任务列表。
"""


def create_planner_prompt_template() -> ChatPromptTemplate:
    """
    创建规划器提示模板。

    Returns
    -------
    ChatPromptTemplate
        提示模板
    """
    message = """
    规则:
        * 确保任务不会返回重复或相似的信息。
        * 确保任务不依赖于从其他任务收集的信息！
        * 相互依赖的任务应合并为单个问题。
        * 返回相同信息的任务应合并为单个问题。

        问题: {question}
    """
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                planner_system,
            ),
            (
                "human",
                (message),
            ),
        ]
    )

planner_prompt = create_planner_prompt_template()


class CypherHistoryRecord(TypedDict):
    """CypherOutputState 的简化表示"""

    task: str
    statement: str
    records: List[Dict[str, Any]]


class HistoryRecord(TypedDict):
    """可能对后续用户问题有用的历史信息。"""

    question: str
    answer: str
    cyphers: List[CypherHistoryRecord]


def update_history(
    history: List[HistoryRecord], new: List[HistoryRecord]
) -> List[HistoryRecord]:
    """
    更新历史记录。任何时候只保留最大数量的记录。

    Parameters
    ----------
    history : List[HistoryRecord]
        当前历史记录列表。
    new : List[HistoryRecord]
        要新增的记录，应为单元素列表。

    Returns
    -------
    List[HistoryRecord]
        添加新记录并移除旧记录后，保持大小限制的新列表。
    """

    SIZE: int = 5

    history.extend(new)
    return history[-SIZE:]

class InputState(TypedDict):
    """多智能体工作流的输入状态。"""

    question: str
    data: List[Dict[str, Any]]
    history: Annotated[List[HistoryRecord], update_history]


def create_planner_node(
    llm: BaseChatModel, ignore_node: bool = False, next_action: str = "tool_selection"
) -> Callable[[InputState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建一个用于 LangGraph 工作流的规划器节点。

    Parameters
    ----------
    llm : BaseChatModel
        用于处理数据的 LLM。
    ignore_node : bool, optional
        是否在工作流中忽略该节点，默认值为 False

    Returns
    -------
    Coroutine 的三个泛型参数分别对应协程规范中的三个通道：
    - 第一个 Any — yield 产出的类型（生成器用，协程一般不用，所以 Any）
    - 第二个 Any — send 接收的类型（同上，Any）
    - 第三个 Dict[str, Any] — 最终 return 的类型（这才是关心的）
    Callable[[InputState], OverallState]
        LangGraph 节点。
    """

    planner_chain: Runnable[Dict[str, Any], Any] = (
        planner_prompt | llm.with_structured_output(PlannerOutput)
    )


    async def planner(state: InputState) -> Dict[str, Any]:
        """
        按需将用户查询拆分为子问题 / 文本片段。
        """
        print("我现在要开始任务分解了！！！")
        if not ignore_node:
            print("我进入的是实际执行！！！！")
            planner_output: PlannerOutput = await planner_chain.ainvoke(
                {"question": state.get("question", "")}
            )
            print(f"planner_output: {planner_output}")
        else:
            print("我进入的是 空列表")
            planner_output = PlannerOutput(tasks=[])
            print(f"planner_output: {planner_output}")
        print("我执行完了！！！")
    
        return {
            "next_action": next_action,
            "tasks": planner_output.tasks
            or [
                Task(
                    question=state.get("question", ""),
                    parent_task=state.get("question", ""),
                )
            ],
            "steps": ["planner"],
        }

    return planner


class Task(BaseModel):
    question: str = Field(..., description="要处理的问题。")
    parent_task: str = Field(
        ..., description="此任务所属的父任务。"
    )
    requires_visualization: bool = Field(
        default=False,
        description="此任务是否需要返回可视化结果。",
    )
    data: Optional[CypherOutputState] = Field(
        default=None, description="Cypher 查询结果详情。"
    )


class PlannerOutput(BaseModel):
    tasks: List[Task] = Field(
        default=[],
        description="为满足输入问题而必须完成的任务列表。",
    )





