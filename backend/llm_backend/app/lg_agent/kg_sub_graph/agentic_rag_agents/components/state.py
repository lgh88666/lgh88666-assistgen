from operator import add
from typing import Annotated, Any, Dict, List, Optional

from langchain_core.messages import ToolCall
from typing_extensions import TypedDict

from ..components.models import Task
from .text2cypher.state import CypherOutputState
from .visualize.state import VisualizationOutputState


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


class OverallState(TypedDict):
    """多智能体工作流的主状态。"""

    question: str
    tasks: Annotated[List[Task], add]
    next_action: str
    cyphers: Annotated[List[CypherOutputState], add]
    summary: str
    steps: Annotated[List[str], add]
    history: Annotated[List[HistoryRecord], update_history]


class OutputState(TypedDict):
    """多智能体工作流的最终输出。"""

    answer: str
    question: str
    steps: List[str]
    cyphers: List[CypherOutputState]
    visualizations: List[VisualizationOutputState]
    history: Annotated[List[HistoryRecord], update_history]


class TaskState(TypedDict):
    """单个任务的状态。"""

    question: str
    parent_task: str
    requires_visualization: bool
    data: CypherOutputState
    visualization: VisualizationOutputState


class PredefinedCypherInputState(TypedDict):
    """预定义 Cypher 节点的输入状态。"""

    task: str
    query_name: str
    query_parameters: Dict[str, Any]
    steps: List[str]


class ToolSelectionInputState(TypedDict):
    """工具选择节点的输入状态。"""
    question: str
    parent_task: str
    context: Any


class ToolSelectionOutputState(TypedDict):
    """工具选择节点的输出状态。"""
    tool_selection_task: str
    tool_call: Optional[ToolCall]
    steps: List[str]


class ToolSelectionErrorState(TypedDict):
    """工具选择错误处理节点的输入状态。"""
    task: str
    errors: List[str]
    steps: List[str]
