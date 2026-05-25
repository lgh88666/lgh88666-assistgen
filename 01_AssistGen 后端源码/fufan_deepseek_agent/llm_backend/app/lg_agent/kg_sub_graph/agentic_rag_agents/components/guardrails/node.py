"""
This code is based on content found in the LangGraph documentation: https://python.langchain.com/docs/tutorials/graph/#advanced-implementation-with-langgraph
"""

from typing import Any, Callable, Coroutine, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.runnables.base import Runnable
from langchain_neo4j import Neo4jGraph


from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.guardrails.models import GuardrailsOutput
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.guardrails.prompts import create_guardrails_prompt_template
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import InputState
from app.core.logger import get_logger

# 获取日志记录器
logger = get_logger(service="guardrails_node")


def create_guardrails_node(
    llm: BaseChatModel,
    graph: Optional[Neo4jGraph] = None,
    scope_description: Optional[str] = None,
) -> Callable[[InputState], Coroutine[Any, Any, dict[str, Any]]]:
    """
    创建一个 guardrails 节点，用于 LangGraph 工作流中判断用户问题是否在业务范围内。

    参数
    ----------
    llm : BaseChatModel
        用于处理数据的大语言模型。
    graph : Optional[Neo4jGraph], optional
        Neo4jGraph 对象，用于生成图结构定义，默认为 None。
    scope_description : Optional[str], optional
        应用业务范围的描述，默认为 None。

    返回
    -------
    Callable[[InputState], OverallState]
    LangGraph 节点。
    """

    # 获取包含了图表结构和范围描述的guardrails完整提示词
    guardrails_prompt = create_guardrails_prompt_template(
        graph=graph, scope_description=scope_description
    )

    # 使用LLM进行结构化输出
    guardrails_chain: Runnable[Dict[str, Any], Any] = (
        guardrails_prompt | llm.with_structured_output(GuardrailsOutput)
    )

    async def guardrails(state: InputState) -> Dict[str, Any]:
        """
        判断用户问题是否在业务范围内。
        """

        # 提取到输入的问题
        question = state.get("question", "")

        # 使用LLM进行结构化输出
        guardrails_output: GuardrailsOutput = await guardrails_chain.ainvoke(
            {"question": question}
        )
        
        summary = None

        if guardrails_output.decision == "end":
            summary = "抱歉，我家暂时没有这方面的商品，可以在别家看看哦~"

        decision_info = {
            "next_action": guardrails_output.decision,
            "summary": summary,
            "steps": ["guardrails"],
        }
        
        logger.info(f"Guardrails Decision Info: {decision_info}")

        return decision_info


    return guardrails
