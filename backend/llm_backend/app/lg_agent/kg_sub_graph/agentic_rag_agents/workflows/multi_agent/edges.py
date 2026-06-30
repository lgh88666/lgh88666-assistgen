"""在多个工作流中复用的 LangGraph 边定义。"""

from typing import List, Literal

from langgraph.types import Send

from ...components.state import OverallState, ToolSelectionOutputState
from ...components.text2cypher.state import CypherOutputState


# 边界检查后的路由：end/final_answer → 终结，planner → 继续拆任务
def guardrails_conditional_edge(
    state: OverallState,
) -> Literal["planner", "final_answer"]:
    match state.get("next_action"):
        case "final_answer":
            return "final_answer"
        case "end":
            return "final_answer"
        case "planner":
            return "planner"
        case _:
            return "final_answer"


# 工具执行完后判断：是否还需要汇总(summarize)，还是直接返回(final_answer)
def tool_select_conditional_edge(
    state: OverallState,
) -> Literal["summarize", "final_answer"]:
    match state.get("next_action"):
        case "summarize":
            return "summarize"
        case "final_answer":
            return "final_answer"
        case _:
            return "final_answer"


# 校验最终答案后路由：确认没问题就走 final_answer，否则重试 text2cypher
def validate_final_answer_router(
    state: OverallState,
) -> Send:
    match state.get("next_action"):
        case "final_answer":
            return Send("final_answer", state)
        case "text2cypher":
            # currently only allow for a single follow up question at a time
            tasks = state.get("tasks", list())
            new_task = tasks[-1]
            return Send("text2cypher", {"task": new_task.question})
        case _:
            return Send("final_answer", state)


# Map 操作：把每个子任务的 question 发给 text2cypher 子图（并行执行）
def query_mapper_edge(state: OverallState) -> List[Send]:
    """将每个子任务的问题映射到 Text2Cypher 子图。"""

    return [
        Send("text2cypher", {"task": task.question})
        for task in state.get("tasks", list())
    ]


# Map 操作：把 planner 拆出的每个子任务并行派发给 tool_selection 节点
def map_reduce_planner_to_tool_selection(state: OverallState) -> List[Send]:
    """将 planner 拆分出的每个子任务，发给 tool_selection 节点并行处理。"""
    tasks = state.get("tasks", [])
    parallel_tasks = []
    for task in tasks:
        parallel_tasks.append(
            Send(
                "tool_selection",
                {
                    "question": task.question,
                    "parent_task": task.parent_task,
                },
            )
        )
    return parallel_tasks


# 工具选择后的路由：根据 next_action 决定走 text2cypher / predefined_cypher / 报错
def tool_selection_output_router(state: ToolSelectionOutputState) -> Send:
    match state.get("next_action", ""):
        case "text2cypher":
            return Send("text2cypher", {"task": state.get("task", "")})
        case "predefined_cypher":
            return Send(
                "predefined_cypher",
                {
                    "task": state.get("task", ""),
                    "tool_call": state.get("tool_call", dict()),
                },
            )
        case "error":
            return Send("final_answer", dict())
        case _:
            return Send("final_answer", dict())
