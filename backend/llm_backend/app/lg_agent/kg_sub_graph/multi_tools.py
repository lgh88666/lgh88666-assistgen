from __future__ import annotations

from typing import Dict, List, Optional, Any, Callable, Coroutine, Annotated, Literal, Set

from langchain_core.language_models import BaseChatModel
from langchain_neo4j import Neo4jGraph
from langgraph.constants import END, START
from langgraph.graph.state import CompiledStateGraph, StateGraph

from pydantic import BaseModel
from typing_extensions import TypedDict
from langchain_core.tools import ToolCall
from operator import add


from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.guardrails.node import create_guardrails_node
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher import create_predefined_cypher_node
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.models import Task
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.tool_selection import create_tool_selection_node
from app.lg_agent.kg_sub_graph.agentic_rag_agents.retrievers.cypher_examples.base import BaseCypherExampleRetriever
from app.lg_agent.kg_sub_graph.agentic_rag_agents.workflows.single_agent import create_text2cypher_agent
from app.lg_agent.kg_sub_graph.agentic_rag_agents.workflows.multi_agent.edges import (
    guardrails_conditional_edge,
    map_reduce_planner_to_tool_selection,
)


class ToolSelectionInputState(TypedDict):
    """工具选择节点的输入状态"""

    question: str
    parent_task: str
    requires_visualization: bool
    context: Any


class ToolSelectionOutputState(TypedDict):
    """工具选择节点的输出状态"""
    tool_selection_task: str
    tool_call: Optional[ToolCall]
    steps: List[str]


class ToolSelectionErrorState(TypedDict):
    """工具选择错误处理节点的输入状态"""

    task: str
    errors: List[str]
    steps: List[str]


class CypherInputState(TypedDict):
    """Cypher 节点的输入状态"""
    task: str


class CypherState(TypedDict):
    """Cypher 生成/验证/修正流水线内部状态"""
    task: str
    statement: str
    parameters: Optional[Dict[str, Any]]
    errors: List[str]
    records: List[Dict[str, Any]]
    next_action_cypher: str
    attempts: int
    steps: Annotated[List[str], add]


class CypherOutputState(TypedDict):
    """Cypher 流水线最终输出"""
    task: str
    statement: str
    parameters: Optional[Dict[str, Any]]
    errors: List[str]
    records: List[Dict[str, Any]]
    steps: List[str]


# 工具选择失败时的兜底节点：将错误包装为空的 Cypher 结果返回
def create_error_tool_selection_node() \
        -> (Callable[[ToolSelectionErrorState], Coroutine[Any, Any, Dict[str, Any]]]):
    """创建工具选择错误处理节点

    Returns:
        Callable: 接收 ToolSelectionErrorState，返回包含错误信息和空记录的 CypherOutputState
    """

    async def error_tool_selection(state: ToolSelectionErrorState) -> Dict[str, Any]:
        """处理工具选择失败的情况，将错误信息包装为空的 Cypher 结果"""
        errors: List[str] = list()
        steps = ["error_tool_selection"]

        errors.extend(state.get("errors", list()))

        return {
            "cyphers": [
                CypherOutputState(
                    **{
                        "task": state.get("task", ""),
                        "statement": "",
                        "parameters": None,
                        "errors": errors,
                        "records": list(),
                        "steps": steps,
                    }
                )
            ],
            "steps": steps,
        }

    return error_tool_selection


# 最终答案组装节点：从 state.summary 提取最终 answer 并写入对话历史
def create_final_answer_node() -> (Callable[[OverallState], Coroutine[Any, Any, dict[str, Any]]]):
    """创建最终答案组装节点

    Returns:
        Callable: 接受 OverallState，将 summary 组装为最终 answer 并记录到 history
    """

    async def final_answer(state: OverallState) -> dict[str, Any]:
        """从 state.summary 提取最终答案，同时生成历史记录写入 state.history"""

        ERROR = "抱歉，无法回答此问题。"

        answer = state.get("summary", ERROR)

        history_record = {
            "question": state.get("question", ""),
            "answer": answer,
            "cyphers": [
                {
                    "task": c.get("task", ""),
                    "statement": c.get("statement", ""),
                    "records": c.get("records", list()),
                }
                for c in state.get("cyphers", list())
            ],
        }

        return {
            "answer": answer,
            "steps": ["final_answer"],
            "history": [history_record],
        }

    return final_answer

class CypherHistoryRecord(TypedDict):
    """单次 Cypher 查询的历史记录（精简版 CypherOutputState）"""

    task: str
    statement: str
    records: List[Dict[str, Any]]

class HistoryRecord(TypedDict):
    """一次问答的完整历史记录"""

    question: str
    answer: str
    cyphers: List[CypherHistoryRecord]


# 对话历史更新函数：追加新记录并截断保留最近 5 条
def update_history(
    history: List[HistoryRecord], new: List[HistoryRecord]
) -> List[HistoryRecord]:
    """更新对话历史，仅保留最近 5 条记录

    Args:
        history: 当前历史列表
        new: 新增记录（通常为单条）

    Returns:
        截断后的历史列表（最多 5 条）
    """

    SIZE: int = 5

    history.extend(new)
    return history[-SIZE:]

class InputState(TypedDict):
    """多工具工作流的输入状态"""

    question: str
    data: List[Dict[str, Any]]
    history: Annotated[List[HistoryRecord], update_history]


class OverallState(TypedDict):
    """多工具工作流的主状态（各节点读写此状态）"""

    question: str
    tasks: Annotated[List[Task], add]
    next_action: str
    cyphers: Annotated[List[CypherOutputState], add]
    summary: str
    steps: Annotated[List[str], add]
    history: Annotated[List[HistoryRecord], update_history]


class OutputState(TypedDict):
    """多工具工作流的最终输出"""

    answer: str
    question: str
    steps: List[str]
    cyphers: List[CypherOutputState]
    history: Annotated[List[HistoryRecord], update_history]


# 构造汇总提示词模板：要求 LLM 根据事实数据回答用户问题并生成摘要
def create_summarization_prompt_template() -> ChatPromptTemplate:
    """创建结果汇总提示词模板"""

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是一个乐于助人的助手",
            ),
            (
                "human",
                (
                    """事实数据: {results}

    * 根据以上事实数据回答问题 "{question}"，并生成摘要
    * 当数据不为空时，假设问题是有效的，答案是正确的
    * 不要返回额外的帮助信息、解释或道歉
    * 只返回摘要结果，不要以"以下是摘要"开头
    * 当结果多于一条时，使用富文本格式列出
    * 不要报告空字符串的结果，但保留值为 0 或 0.0 的结果"""
                ),
            ),
        ]
    )

generate_summary_prompt = create_summarization_prompt_template()

# 结果汇总节点：遍历所有 Cypher 查询记录，调用 LLM 合并为最终摘要
def create_summarization_node(
    llm: BaseChatModel,
) -> Callable[[OverallState], Coroutine[Any, Any, dict[str, Any]]]:
    """创建结果汇总节点

    Args:
        llm: 用于生成摘要的语言模型
    """

    generate_summary = generate_summary_prompt | llm | StrOutputParser()

    async def summarize(state: OverallState) -> Dict[str, Any]:
        """遍历 state.cyphers 中的记录，调用 LLM 汇总"""

        results = [
            cypher.get("records")
            for cypher in state.get("cyphers", list())
            if cypher.get("records") is not None
        ]

        if results:
            summary = await generate_summary.ainvoke(
                {
                    "question": state.get("question"),
                    "results": results,
                }
            )

        else:
            summary = "没有可汇总的数据。"

        return {"summary": summary, "steps": ["summarize"]}

    return summarize


system = """
你负责为给定的问题选择合适的工具。只能使用提供的工具。
默认选择 text2cypher 工具，除非另一个工具与问题要求完全匹配。
"""


# 构造工具选择提示词：要求 LLM 从可用工具中为给定问题选择最合适的工具
def create_tool_selection_prompt_template() -> ChatPromptTemplate:
    """创建工具选择提示词模板"""

    message = "问题: {question}"

    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system,
            ),
            (
                "human",
                (message),
            ),
        ]
    )

tool_selection_prompt = create_tool_selection_prompt_template()

from langgraph.types import Command, Send
from langchain_core.runnables.base import Runnable
from langchain_core.output_parsers import PydanticToolsParser


# 工具选择路由节点：LLM 决策后将任务 Send 到 text2cypher / predefined_cypher / error 分支
def create_tool_selection_node(
    llm: BaseChatModel,
    tool_schemas: List[type[BaseModel]],
    default_to_text2cypher: bool = True,
) -> Callable[[ToolSelectionInputState], Coroutine[Any, Any, Command[Any]]]:
    """创建工具选择节点

    Args:
        llm: 用于工具选择的语言模型
        tool_schemas: 可用工具的 Pydantic Schema 列表
        default_to_text2cypher: LLM 未返回工具调用时，是否默认走 Text2Cypher
    """

    tool_selection_chain: Runnable[Dict[str, Any], Any] = (
        tool_selection_prompt
        | llm.bind_tools(tools=tool_schemas)
        | PydanticToolsParser(tools=tool_schemas, first_tool_only=True)
    )

    # 从 tool_schemas 中提取除 text2cypher 和 visualize 之外的预定义工具名
    predefined_cypher_tools: Set[str] = {
        t.model_json_schema().get("title", "") for t in tool_schemas
    }

    predefined_cypher_tools.discard("text2cypher")
    predefined_cypher_tools.discard("visualize")

    async def tool_selection(
        state: ToolSelectionInputState,
    ) -> Command[Literal["text2cypher", "error_tool_selection", "predefined_cypher"]]:
        """根据任务选择合适工具，通过 Command + Send 路由到对应节点"""

        go_to_text2cypher: Command[
            Literal[
                "text2cypher", "error_tool_selection", "predefined_cypher"
            ]  # 实际只会路由到 text2cypher，扩展类型定义是为了通过 mypy 静态检查
        ] = Command(
            goto=Send(
                "text2cypher",
                {
                    "task": state.get("question", ""),
                    "steps": ["tool_selection"],
                },
            )
        )

        # 捷径：只剩 text2cypher 一个工具时，跳过 LLM 调用直接路由
        if (
            len(predefined_cypher_tools) == 1
            and predefined_cypher_tools.pop().lower() == "text2cypher"
        ):
            return go_to_text2cypher

        # 调用 LLM 决定使用哪个工具
        tool_selection_output: BaseModel = await tool_selection_chain.ainvoke(
            {"question": state.get("question", "")}
        )

        # 根据 LLM 返回的工具名路由到对应节点
        if tool_selection_output is not None:
            tool_name: str = tool_selection_output.model_json_schema().get("title", "")
            tool_args: Dict[str, Any] = tool_selection_output.model_dump()

            if tool_name in predefined_cypher_tools:
                return Command(
                    goto=Send(
                        "predefined_cypher",
                        {
                            "task": state.get("question", ""),
                            "query_name": tool_name,
                            "query_parameters": tool_args,
                            "steps": ["tool_selection"],
                        },
                    )
                )
            elif tool_name == "text2cypher":
                return go_to_text2cypher

        elif default_to_text2cypher:
            return go_to_text2cypher

        # LLM 无法匹配任何工具 → 进入错误处理节点
        else:
            return Command(
                goto=Send(
                    "error_tool_selection",
                    {
                        "task": state.get("question", ""),
                        "errors": [
                            f"无法为问题分配工具: `{state.get('question', '')}`"
                        ],
                        "steps": ["tool_selection"],
                    },
                )
            )

        return go_to_text2cypher

    return tool_selection




# 组装完整的多工具 Agent 工作流图：guardrails → planner → 工具选择 → 汇总 → 最终答案
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
    """创建多工具 Agent 工作流

    工作流结构:
        START → guardrails → planner → tool_selection (Send fan-out)
          ├─ text2cypher      → summarize
          ├─ predefined_cypher → summarize
          └─ error_tool_selection → summarize
             → final_answer → END

    Args:
        llm: 处理用的语言模型
        graph: Neo4j 图数据库连接
        tool_schemas: 可用工具的 Pydantic Schema 列表
        predefined_cypher_dict: 预定义 Cypher 查询字典 {名称: 查询语句}
        cypher_example_retriever: Few-shot Cypher 示例检索器
        scope_description: 经营范围描述，用于 guardrails 范围检查
        llm_cypher_validation: 是否启用 LLM 验证生成的 Cypher
        max_attempts: Cypher 生成最大重试次数，默认 3
        attempt_cypher_execution_on_final_attempt: 最后一次尝试是否强制执行 Cypher（可能有风险）
        default_to_text2cypher: LLM 未返回工具调用时是否默认走 Text2Cypher

    Returns:
        CompiledStateGraph: 编译后的可执行工作流图
    """

    guardrails = create_guardrails_node(
        llm=llm, graph=graph, scope_description=scope_description
    )

    from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner import create_planner_node
    planner = create_planner_node(llm=llm)
    predefined_cypher = create_predefined_cypher_node(
        graph=graph, predefined_cypher_dict=predefined_cypher_dict
    )
    text2cypher = create_text2cypher_agent(
        llm=llm,
        graph=graph,
        cypher_example_retriever=cypher_example_retriever,
        llm_cypher_validation=llm_cypher_validation,
        max_attempts=max_attempts,
        attempt_cypher_execution_on_final_attempt=attempt_cypher_execution_on_final_attempt,
    )
    tool_selection = create_tool_selection_node(
        llm=llm,
        tool_schemas=tool_schemas,
        default_to_text2cypher=default_to_text2cypher,
    )
    error_tool_selection = create_error_tool_selection_node()
    summarize = create_summarization_node(llm=llm)

    final_answer = create_final_answer_node()

    main_graph_builder = StateGraph(OverallState, input=InputState, output=OutputState)
    main_graph_builder.add_node("guardrails", guardrails)
    main_graph_builder.add_node("planner", planner)
    main_graph_builder.add_node("text2cypher", text2cypher)
    main_graph_builder.add_node("predefined_cypher", predefined_cypher)
    main_graph_builder.add_node("summarize", summarize)
    main_graph_builder.add_node("tool_selection", tool_selection)
    main_graph_builder.add_node("error_tool_selection", error_tool_selection)
    main_graph_builder.add_node("final_answer", final_answer)

    # 边定义
    main_graph_builder.add_edge(START, "guardrails")
    main_graph_builder.add_conditional_edges(
        "guardrails",
        guardrails_conditional_edge,
    )
    main_graph_builder.add_conditional_edges(
        "planner",
        map_reduce_planner_to_tool_selection,  # type: ignore[arg-type, unused-ignore]
        ["tool_selection"],
    )
    # 三个工具节点汇聚到 summarize
    main_graph_builder.add_edge("error_tool_selection", "summarize")
    main_graph_builder.add_edge("text2cypher", "summarize")
    main_graph_builder.add_edge("predefined_cypher", "summarize")
    main_graph_builder.add_edge("summarize", "final_answer")

    main_graph_builder.add_edge("final_answer", END)

    return main_graph_builder.compile()
