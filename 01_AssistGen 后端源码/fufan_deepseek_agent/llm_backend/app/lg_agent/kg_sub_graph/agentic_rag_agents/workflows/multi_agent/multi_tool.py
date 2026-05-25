from typing import Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_neo4j import Neo4jGraph
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph
from pydantic import BaseModel

# 导入输入输出状态定义
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import (
    InputState,
    OutputState,
    OverallState,
)
# 导入guardrails逻辑
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.guardrails.node import create_guardrails_node
# 导入分解节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner import create_planner_node
# 导入工具选择节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.tool_selection import create_tool_selection_node
# 导入 text2cypher 节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.cypher_tools import create_cypher_query_node
# 导入Cypher示例检索器基类
from app.lg_agent.kg_sub_graph.agentic_rag_agents.retrievers.cypher_examples.base import BaseCypherExampleRetriever
# 导入预定义Cypher节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher import create_predefined_cypher_node
# 导入自定义工具函数节点
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.customer_tools import create_graphrag_query_node



from ...components.errors import create_error_tool_selection_node
from ...components.final_answer import create_final_answer_node



from ...components.summarize import create_summarization_node



from .edges import (
    guardrails_conditional_edge,
    map_reduce_planner_to_tool_selection,
)

from dataclasses import dataclass, field
# 强制要求数据类中的所有字段必须以关键字参数的形式提供。即不能以位置参数的方式传递。
@dataclass(kw_only=True)
class AgentState(InputState):
    """
        steps:就是个执行轨迹，每个节点跑完留下脚印
    """
    steps: list[str] = field(default_factory=list)
    question: str = field(default_factory=str) # 这个参数用来与子图进行交互
    answer: str = field(default_factory=str)  # 这个参数用来与子图进行交互

# 创建子图函数
def create_multi_tool_workflow(
    llm: BaseChatModel,
    graph: Neo4jGraph,
    tool_schemas: List[type[BaseModel]],
    predefined_cypher_dict: Dict[str, str],
    cypher_example_retriever: BaseCypherExampleRetriever,
    scope_description: Optional[str] = None,
    llm_cypher_validation: bool = True,
    max_attempts: int = 3,
    attempt_cypher_execution_on_final_attempt: bool = False,
    default_to_text2cypher: bool = True,
) -> CompiledStateGraph:
    """
    使用 LangGraph 创建多工具 Agent 工作流。
    该工作流允许 Agent 从多个工具中选择最合适的一个来完成每个识别出的任务。

    参数
    ----------
    llm : BaseChatModel
        用于处理的大语言模型
    graph : Neo4jGraph
        Neo4j 图数据库连接封装
    tool_schemas : List[BaseModel]
        可用工具的 Pydantic Schema 列表，定义每个工具的用途和参数
    predefined_cypher_dict : Dict[str, str]
        预定义的 Cypher 查询字典，键为查询名称，值为 Cypher 查询语句
    scope_description: Optional[str], optional
        经营范围描述，用于 guardrails 判断问题是否在业务范围内，默认为 None
    cypher_example_retriever: BaseCypherExampleRetriever
        用于检索 Cypher 示例的检索器，为 Text2Cypher 提供 Few-shot 提示
    llm_cypher_validation : bool, optional
        是否启用 LLM 验证生成的 Cypher 语句，默认 True
    max_attempts: int, optional
        生成有效 Cypher 的最大重试次数，默认 3
    attempt_cypher_execution_on_final_attempt, bool, optional
        注意：此选项可能存在风险。
        是否在最后一次重试时强制执行 Cypher（即使语句可能包含错误），默认 False
    default_to_text2cypher : bool, optional
        LLM 未返回工具调用时，是否默认走 Text2Cypher 路径，默认 True
    initial_state: Optional[InputState], optional
        从父图传入的初始状态，默认 None

    返回
    -------
    CompiledStateGraph
        编译后的可执行工作流图
    """
    # 1. 创建guardrails节点
    # Guardrails 节点决定传入的问题是否在检索的范围内（比如是否和电商（自家的产品相关））。如果不在，则提供默认消息，并且工作流路由到最终的答案生成。
    guardrails = create_guardrails_node(
        llm=llm, graph=graph, scope_description=scope_description
    )

    # 2. 创建planner节点
    # 如果通过guardrails，则会针对用户的问题进行任务分解
    planner = create_planner_node(llm=llm)

    # 3. 创建cypher_query节点，用来根据用户的问题生成Cypher查询语句

    # 通过 LLM 动态生成 Cypher 语句去查 Neo4j
    cypher_query = create_cypher_query_node()

    # 不走 LLM，直接从预定义的 Cypher 字典里按名称匹配一条写死的查询语句执行
    predefined_cypher = create_predefined_cypher_node(
        graph=graph, predefined_cypher_dict=predefined_cypher_dict
    )

    # 调用 GraphRAG 做知识图谱检索，不走 Cypher
    customer_tools = create_graphrag_query_node()

    # 工具选择节点，根据用户的问题选择合适的工具
    tool_selection = create_tool_selection_node(
        llm=llm,
        tool_schemas=tool_schemas,
        default_to_text2cypher=default_to_text2cypher,
    )
    summarize = create_summarization_node(llm=llm)

    final_answer = create_final_answer_node()

    error_tool_selection = create_error_tool_selection_node()

    # 创建状态图
    main_graph_builder = StateGraph(OverallState, input=InputState, output=OutputState)

    main_graph_builder.add_node("guardrails", guardrails)
    main_graph_builder.add_node("planner", planner)
    main_graph_builder.add_node("tool_selection", tool_selection)
    main_graph_builder.add_node("cypher_query", cypher_query)
    main_graph_builder.add_node("predefined_cypher", predefined_cypher)
    main_graph_builder.add_node("customer_tools", customer_tools)
    main_graph_builder.add_node("summarize", summarize)
    main_graph_builder.add_node("final_answer", final_answer)
    main_graph_builder.add_node("error_tool_selection", error_tool_selection)


    # 添加边
    main_graph_builder.add_edge(START, "guardrails")
    main_graph_builder.add_conditional_edges(
        "guardrails",
        guardrails_conditional_edge,
    ) # 这里guardrails_conditional_edge直接返回节点名字符串，所以不需要第三个参数指定目的地列表


    main_graph_builder.add_conditional_edges(
        "planner",
        map_reduce_planner_to_tool_selection,  # type: ignore[arg-type, unused-ignore]
        ["tool_selection"],
        # path_map，它不是目的地列表，而是声明"这些是合法目的地"
    )

    main_graph_builder.add_edge("cypher_query", "summarize")
    main_graph_builder.add_edge("predefined_cypher", "summarize")
    main_graph_builder.add_edge("customer_tools", "summarize")
    main_graph_builder.add_edge("summarize", "final_answer")

    main_graph_builder.add_edge("final_answer", END)

    return main_graph_builder.compile()

