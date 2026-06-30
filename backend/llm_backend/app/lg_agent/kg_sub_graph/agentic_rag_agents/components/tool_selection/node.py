"""
tool_selection 节点职责：
* 每次只处理一个任务
* 获取可用的工具列表
    * text2cypher
    * 自定义预写 Cypher 执行器
        * 数量可能很多，检索方式与 CypherQuery 节点内容一致
    * 非结构化文本搜索（sim search）
* 为任务选择合适的工具
* 生成并验证所选工具的参数
* 将验证后的参数发送到对应的工具节点
"""

from typing import Any, Callable, Coroutine, Dict, List, Literal, Set
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import PydanticToolsParser
from langchain_core.runnables.base import Runnable
from langgraph.types import Command, Send
from pydantic import BaseModel


from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.state import ToolSelectionInputState
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.tool_selection.prompts import create_tool_selection_prompt_template

# 定义工具选择提示词
tool_selection_prompt = create_tool_selection_prompt_template()


# 声明式的使用可配置模型：https://python.langchain.com/docs/how_to/chat_models_universal_init/#using-a-configurable-model-declaratively
def create_tool_selection_node(
    llm: BaseChatModel,
    tool_schemas: List[type[BaseModel]],
    default_to_text2cypher: bool = True,
) -> Callable[[ToolSelectionInputState], Coroutine[Any, Any, Command[Any]]]:
    """
    创建一个 tool_selection 节点，用于 LangGraph 工作流。

    参数
    ----------
    llm : BaseChatModel
        用于处理数据的 LLM。
    tool_schemas : Sequence[Union[Dict[str, Any], type, Callable, BaseTool]
        工具 schema 列表，告知 LLM 有哪些工具可用。
    default_to_text2cypher : bool, optional
        当 LLM 未返回任何工具调用时，是否默认走 Text2Cypher，默认 True。

    返回
    -------
    Callable[[ToolSelectionInputState], ToolSelectionOutputState]
        LangGraph 节点函数。
    """

    # 构建工具选择链，由大模型根据传递过来的 Task，在预定义的工具列表中选择一个工具。
    tool_selection_chain: Runnable[Dict[str, Any], Any] = (
        tool_selection_prompt
        | llm.bind_tools(tools=tool_schemas)
        | PydanticToolsParser(tools=tool_schemas, first_tool_only=True)
    )

    # 从传入的tool_schemas列表中，获取每个工具的title属性，创建出一个工具名称集合。
    predefined_cypher_tools: Set[str] = {
        t.model_json_schema().get("title", "") for t in tool_schemas
    }


    async def tool_selection(
        state: ToolSelectionInputState,
    ) -> Command[Literal["cypher_query", "predefined_cypher", "customer_tools"]]:
        """
        为给定任务选择合适的工具。
        """
        go_to_text2cypher = Command(
            goto=Send(
                "cypher_query",
                {
                    "task": state.get("question", ""),
                    "steps": ["tool_selection"],
                },
            )
        )

        # 调用工具选择链，生成针对每个任务要调用的工具名称和参数
        tool_selection_output: BaseModel = await tool_selection_chain.ainvoke(
            {"question": state.get("question", "")}
        )

        # 根据路由到对应的工具节点
        if tool_selection_output is not None:
            tool_name: str = tool_selection_output.model_json_schema().get("title", "")
            tool_args: Dict[str, Any] = tool_selection_output.model_dump() 
            if tool_name == "predefined_cypher":
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
            elif tool_name == "cypher_query":
                return Command(
                    goto=Send(
                        "cypher_query",
                        {
                            "task": state.get("question", ""),
                            "query_name": tool_name,
                            "query_parameters": tool_args,
                            "steps": ["tool_selection"],
                        },
                    )
                )
            
            else:
                return Command(
                    goto=Send(
                        "customer_tools",
                        {
                            "task": state.get("question", ""),
                            "query_name": tool_name,
                            "query_parameters": tool_args,
                            "steps": ["tool_selection"],
                        },
                    )
                )


           
                
        elif default_to_text2cypher:
            return go_to_text2cypher

        # 处理未选择任何工具的情况
        else:
            return Command(
                goto=Send(
                    "error_tool_selection",
                    {
                        "task": state.get("question", ""),
                        "errors": [
                            f"Unable to assign tool to question: `{state.get('question', '')}`"
                        ],
                        "steps": ["tool_selection"],
                    },
                )
            )

        return go_to_text2cypher

    return tool_selection
