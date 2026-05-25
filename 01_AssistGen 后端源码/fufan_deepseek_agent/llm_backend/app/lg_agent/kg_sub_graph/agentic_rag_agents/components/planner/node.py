from typing import Any, Callable, Coroutine, Dict
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables.base import Runnable
from app.core.logger import get_logger

# 获取日志记录器
logger = get_logger(service="planner_node")

from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.models import Task
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner.models import PlannerOutput
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner.prompts import create_planner_prompt_template
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import InputState


# 定义planner prompt
planner_prompt = create_planner_prompt_template()

def create_planner_node(
    llm: BaseChatModel, ignore_node: bool = False, next_action: str = "tool_selection"
) -> Callable[[InputState], Coroutine[Any, Any, Dict[str, Any]]]:
    """
    创建一个用于 LangGraph 工作流 的规划器节点.

    Parameters
    ----------
    llm : BaseChatModel

    ignore_node : bool, optional
        是否在工作流中忽略该节点，默认值为 False
    - ignore_node = False（默认） → if not ignore_node 为 True，走真实逻辑：调用 LLM 把用户问题拆分成多个子任务
    - ignore_node = True → if not ignore_node 为 False，跳过分词逻辑，直接返回空任务列表 PlannerOutput(tasks=[])
    这个参数实质上是个"预留开关"——设计时考虑到可能某些流程不需要任务分解，但实际所有 workflow 都走了分解逻辑，所以从未被启用过

    Returns
    -------
    Callable[[InputState], OverallState]
        The LangGraph node.
    """

    # 创建planner chain，Runnable[输入类型, 输出类型]
    planner_chain: Runnable[Dict[str, Any], Any] = (
        planner_prompt | llm.with_structured_output(PlannerOutput)
    )

    async def planner(state: InputState) -> Dict[str, Any]:
        """
        按需将用户查询拆分为子问题 / 文本片段
        """

        if not ignore_node:
            planner_output: PlannerOutput = await planner_chain.ainvoke(
                {"question": state.get("question", "")}
            )
        else:
            planner_output = PlannerOutput(tasks=[])

        planner_task_decomposition = {
            "next_action": next_action,
            "tasks": planner_output.tasks
            or [
                Task(
                    question=state.get("question", ""),
                    parent_task=state.get("question", ""),
                )   
            ]
        }

        # 日志打印格式，分别打印每个任务
        logger.info(f"Total Sub Task: {len(planner_task_decomposition['tasks'])}")
   
        for i, task in enumerate(planner_task_decomposition['tasks']):
            logger.info(f"Sub Task[{i+1}]: {task.question}")
             
        return planner_task_decomposition

    return planner
