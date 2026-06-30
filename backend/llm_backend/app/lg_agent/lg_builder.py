from app.lg_agent.lg_states import AgentState, Router
from app.lg_agent.lg_prompts import (
    ROUTER_SYSTEM_PROMPT,
    GET_ADDITIONAL_SYSTEM_PROMPT,
    GENERAL_QUERY_SYSTEM_PROMPT,
    GET_IMAGE_SYSTEM_PROMPT,
    GUARDRAILS_SYSTEM_PROMPT,
    RAGSEARCH_SYSTEM_PROMPT,
    CHECK_HALLUCINATIONS,
    GENERATE_QUERIES_SYSTEM_PROMPT,
    FILE_QUERY_SYSTEM_PROMPT
)
from langchain_core.runnables import RunnableConfig
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from app.core.config import settings, ServiceType
from app.core.logger import get_logger
from typing import cast, Literal, TypedDict, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from app.lg_agent.lg_states import AgentState, InputState, Router, GradeHallucinations
from app.lg_agent.kg_sub_graph.agentic_rag_agents.retrievers.cypher_examples.northwind_retriever import NorthwindCypherRetriever
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.planner.node import create_planner_node
from app.lg_agent.kg_sub_graph.agentic_rag_agents.workflows.multi_agent.multi_tool import create_multi_tool_workflow
from app.lg_agent.kg_sub_graph.kg_neo4j_conn import get_neo4j_graph
from pydantic import BaseModel
from typing import Dict, List
from langchain_core.messages import AIMessage
from langchain_core.runnables.base import Runnable
from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.utils.utils import retrieve_and_parse_schema_from_graph_for_prompts
from langchain_core.prompts import ChatPromptTemplate
import base64
import os
import aiohttp
import asyncio
import json
import time
from pathlib import Path


from typing import Literal
from pydantic import BaseModel, Field


class AdditionalGuardrailsOutput(BaseModel):
    """
    格式化输出，用于判断用户的问题是否与图谱内容相关
    decision（决策结果）只能二选一
    """
    decision: Literal["end", "continue"] = Field(
        description="Decision on whether the question is related to the graph contents."
    )


# 构建日志记录器
logger = get_logger(service="lg_builder")

# 用LLM将用户问题分类为5种类型（general/additional/graphrag/image/file），决定下游走哪条分支
async def analyze_and_route_query(
    state: AgentState, *, config: RunnableConfig
) -> dict[str, Router]:
    """
    分析用户查询并确定合适的路由路径。
    本函数通过语言模型对用户查询进行分类，进而确定对话流程中的流转路由方式。
    参数:
        state (AgentState)：智能体当前状态，包含对话历史记录。
        config (RunnableConfig)：搭载查询分析所用模型的配置项。
    返回值:
        dict[str, Router]：包含router键的字典，该键对应的值为分类结果（含分类类型与逻辑）。
    """
    # 选择模型实例，通过.env文件中的AGENT_SERVICE参数选择
    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["router"])
        logger.info(f"Using DeepSeek model: {settings.DEEPSEEK_MODEL}")
    else:
        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["router"])
        logger.info(f"Using Ollama model: {settings.OLLAMA_AGENT_MODEL}")

    # 拼接提示模版 + 用户的实时问题（包含历史上下文对话）
    messages = []
    # 添加系统角色提示
    messages.append({"role": "system", "content": ROUTER_SYSTEM_PROMPT})
    # 循环添加历史对话
    for msg in state.messages:
        messages.append(msg)

    logger.info("-----Analyze user query type-----")
    logger.info(f"History messages: {state.messages}")
    
    # 使用结构化输出，输出问题类型
    response = cast(
        Router, await model.with_structured_output(Router).ainvoke(messages)
    )
    """
    1.ainvoke = 异步执行 LLM 调用
    2.with_structured_output = 让 LLM 按固定 JSON 格式输出
    3.cast(类型, 值)的意思是："类型检查器你听着，我把这个值当成 Router 类型，你别报错"。
    4.在这个项目里用 ainvoke 的原因是 FastAPI 本身就是异步框架——你用invoke 会卡死整个 worker
      线程，其他并发请求全排队等着。用 ainvoke，一个请求等 LLM 的同时，worker 可以处理别的请求
    """
    logger.info(f"Analyze user query type completed, result: {response}")
    return {"router": response}

# 根据Router的分类结果，映射到对应的节点名（条件边的路由函数）
def route_query(
    state: AgentState,
) -> Literal["respond_to_general_query", "get_additional_info", "create_research_plan", "create_image_query", "create_file_query"]:
    """根据查询分类确定下一步操作。

    Args:
        state (AgentState): 当前代理状态，包括路由器的分类。

    Returns:
        Literal["respond_to_general_query", "get_additional_info", "create_research_plan", "create_image_query", "create_file_query"]: 下一步操作。
        Literal 是 Python 类型提示中的一个特殊类型，用于限定值只能是某几个具体的字面量。
    """
    _type = state.router["type"]
    """从analyze_and_route_query返回的response字典里拿到type对应的键值"""
    
    # 文件/图片优先级覆盖：无论 LLM 分类结果如何，只要用户上传了文件或图片，直接走对应分支
    configurable = state.config.get("configurable", {}) if hasattr(state, "config") and state.config else {}
    if configurable.get("image_path"):
        logger.info("检测到图片路径，强制走图片分析分支")
        return "create_image_query"
    if configurable.get("file_path"):
        logger.info("检测到文件路径，强制走文件查询分支")
        return "create_file_query"

    if _type == "general-query":
        return "respond_to_general_query"
    elif _type == "additional-query":
        return "get_additional_info"
    elif _type == "graphrag-query":
        return "create_research_plan"
    elif _type == "image-query":
        return "create_image_query"
    elif _type == "file-query":
        return "create_file_query"
    else:
        raise ValueError(f"Unknown router type {_type}")
    
# 通用闲聊回复：纯靠LLM回答，不调任何外部工具或知识库
async def respond_to_general_query(
    state: AgentState, *, config: RunnableConfig
) -> Dict[str, List[BaseMessage]]:
    """生成对一般查询的响应，完全基于大模型，不会触发任何外部服务的调用，包括自定义工具、知识库查询等。

    当路由器将查询分类为一般问题时，将调用此节点。

    Args:
        state (AgentState): 当前代理状态，包括对话历史和路由逻辑。
        config (RunnableConfig): 用于配置响应生成的模型。

    Returns:
        Dict[str, List[BaseMessage]]: 包含'messages'键的字典，其中包含生成的响应。
    """
    logger.info("-----generate general-query response-----")
    
    # 使用大模型生成回复
    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["general_query"])
    else:
        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["general_query"])
    
    system_prompt = GENERAL_QUERY_SYSTEM_PROMPT.format(
        logic=state.router["logic"]
    )
    """
    logic是router的参数，在analyze_and_route_query调用llm的时候填充了，代表llm自己解释为什么这么分类
    这里用state.router["logic"]来替换掉提示词模板里面的{logic} 占位符
    """
    
    messages = [{"role": "system", "content": system_prompt}] + state.messages
    response = await model.ainvoke(messages)
    return {"messages": [response]}

# 信息不足时追问用户：先用Neo4j guardrails检查是否在经营范围，再引导用户补充细节
async def get_additional_info(
    state: AgentState, *, config: RunnableConfig
) -> Dict[str, List[BaseMessage]]:
    """生成一个响应，要求用户提供更多信息。

    当路由确定需要从用户那里获取更多信息时，将调用此函数。

    Args:
        state (AgentState): 当前代理状态，包括对话历史和路由逻辑。
        config (RunnableConfig): 用于配置响应生成的模型。

    Returns:
        Dict[str, List[BaseMessage]]: 包含'messages'键的字典，其中包含生成的响应。
    """
    logger.info("------continue to get additional info------")
    
    # 使用大模型生成回复
    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["additional_info"])
    else:
        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["additional_info"])

    # 如果用户的问题是电商相关，但与自己的业务无关，则需要返回"无关问题"

    # 首先连接 Neo4j 图数据库
    try:
        neo4j_graph = get_neo4j_graph()
        logger.info("success to get Neo4j graph database connection")
    except Exception as e:
        logger.error(f"failed to get Neo4j graph database connection: {e}")

    # 定义电商经营范围
    scope_description = """
    个人电商经营范围：智能家居产品，包括但不限于：
    - 智能照明（灯泡、灯带、开关）
    - 智能安防（摄像头、门锁、传感器）
    - 智能控制（温控器、遥控器、集线器）
    - 智能音箱（语音助手、音响）
    - 智能厨电（电饭煲、冰箱、洗碗机）
    - 智能清洁（扫地机器人、洗衣机）
    
    不包含：服装、鞋类、体育用品、化妆品、食品等非智能家居产品。
    """

    scope_context = (
        f"参考此范围描述来决策:\n{scope_description}"
        if scope_description is not None
        else ""
    )

    # 动态从 Neo4j 图表中获取图表结构
    graph_context = (
        f"\n参考图表结构来回答:\n{retrieve_and_parse_schema_from_graph_for_prompts(neo4j_graph)}"
        if neo4j_graph is not None
        else ""
    )

    message = scope_context + graph_context + "\nQuestion: {question}"

    # 拼接提示模版
    full_system_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                GUARDRAILS_SYSTEM_PROMPT,
            ),
            (
                "human",
                (message),
            ),
        ]
    )

    # 构建格式化输出的 Chain， 如果匹配，返回 continue，否则返回 end
    guardrails_chain = full_system_prompt | model.with_structured_output(AdditionalGuardrailsOutput)
    guardrails_output = await guardrails_chain.ainvoke(
            {"question": state.messages[-1].content if state.messages else ""}
        )

    # 根据格式化输出的结果，返回不同的响应
    if guardrails_output.decision == "end":
        logger.info("-----Fail to pass guardrails check-----")
        return {"messages": [AIMessage(content="抱歉，我家暂时没有这方面的商品，可以在别家看看哦~")]}
    else:
        logger.info("-----Pass guardrails check-----")
        system_prompt = GET_ADDITIONAL_SYSTEM_PROMPT.format(
            logic=state.router["logic"]
        )
        messages = [{"role": "system", "content": system_prompt}] + state.messages
        response = await model.ainvoke(messages)
        return {"messages": [response]}

# 图片分析：视觉模型解析图片 → 生成描述 → LLM 结合用户问题回复（多模型协作）
async def create_image_query(
    state: AgentState, *, config: RunnableConfig
) -> Dict[str, List[BaseMessage]]:
    """处理图片查询并生成描述回复

    Args:
        state (AgentState): 当前代理状态，包括对话历史
        config (RunnableConfig): 运行时配置，image_path 从 config.configurable 传入而非 state（请求级参数不持久化）

    Returns:
        Dict[str, List[BaseMessage]]: 包含'messages'键的字典，通过 add_messages reducer 追加到 state
    """
    logger.info("-----Found User Upload Image-----")
    # 从 config.configurable 取 image_path，而非 state —— 图片路径是请求级运行时参数，不应持久化到对话状态
    image_path = config.get("configurable", {}).get("image_path", None)

    # 容错：图片不存在 → 降级返回友好提示，不抛异常
    if not image_path or not Path(image_path).exists():
        logger.warning(f"User Upload Image Not Found: {image_path}")
        return {"messages": [AIMessage(content="抱歉，我无法查看这张图片，请重新上传。")]}

    # 视觉模型独立配置（VISION_API_KEY / VISION_BASE_URL / VISION_MODEL），与对话 LLM 解耦，可独立升级
    api_key = settings.VISION_API_KEY
    base_url = settings.VISION_BASE_URL
    vision_model = settings.VISION_MODEL

    # 容错：视觉模型配置不全 → 降级
    if not api_key or not base_url or not vision_model:
        logger.error("Vision Model Configuration Not Complete")
        return {"messages": [AIMessage(content="抱歉，我无法查看这张图片，请重新上传。")]}

    logger.info(f"Using Vision Model: {vision_model} to process image: {image_path}")

    try:
        from PIL import Image
        import io

        # 图片预处理：限制最大尺寸 + 转JPEG压缩 + base64编码 → 减少体积，降低API延迟和成本
        with Image.open(image_path) as img:
            max_size = 1024  # 常见视觉API上限
            width, height = img.size
            ratio = min(max_size / width, max_size / height)

            if width <= max_size and height <= max_size:
                resized_img = img
            else:
                new_width = int(width * ratio)
                new_height = int(height * ratio)
                resized_img = img.resize((new_width, new_height), Image.LANCZOS)

            # 统一转RGB再出JPEG（PNG/RGBA → RGB → JPEG），quality=85 平衡体积与画质
            img_byte_arr = io.BytesIO()
            if resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            resized_img.save(img_byte_arr, format='JPEG', quality=85)
            img_byte_arr.seek(0)

            # base64 编码后体积膨胀约33%，前面压缩是为了对冲这个膨胀
            image_data = base64.b64encode(img_byte_arr.read()).decode('utf-8')

            logger.info(f"Image Compressed, Original Size: {width}x{height}, New Size: {resized_img.width}x{resized_img.height}")

        # OpenAI 兼容的视觉 API 请求：图片以 Data URL 格式嵌入
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        payload = {
            "model": vision_model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是一个专业的图像分析助手。请详细分析图片中的内容，特别关注产品细节、品牌、型号等信息。"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4000,
            "temperature": 0.7
        }

        # 异步 HTTP 调用（aiohttp），匹配 FastAPI 异步框架，避免同步请求阻塞 worker
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    image_description = result["choices"][0]["message"]["content"]
                    logger.info(f"Successfully processed image and generated description")
                    # 两阶段流水线：视觉模型出描述 → 对话 LLM 结合用户问题生成回复

                    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
                        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["image_query"])
                    else:
                        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["image_query"])
                    # 将视觉模型的描述注入提示词模板，让对话LLM基于图片内容回答
                    system_prompt = GET_IMAGE_SYSTEM_PROMPT.format(
                        image_description=image_description
                    )
                    messages = [{"role": "system", "content": system_prompt}] + state.messages
                    response = await model.ainvoke(messages)
                    return {"messages": [response]}

                else:
                    # API调用失败也走降级，不崩掉整个流程
                    error_text = await response.text()
                    logger.error(f"Vision API Request Failed: {response.status} - {error_text}")
                    return {"messages": [AIMessage(content=f"抱歉，我无法查看这张图片，请重新上传。")]}





    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        return {"messages": [AIMessage(content=f"抱歉，我无法查看这张图片，请重新上传。")]}

# 文件查询：读取上传文件内容 → 提取文本 → LLM 结合用户问题回复
async def create_file_query(
    state: AgentState, *, config: RunnableConfig
) -> Dict[str, List[BaseMessage]]:
    """处理文件查询并基于文件内容生成回复

    Args:
        state (AgentState): 当前代理状态，包括对话历史
        config (RunnableConfig): 运行时配置，file_path 从 config.configurable 传入（请求级参数不持久化）

    Returns:
        Dict[str, List[BaseMessage]]: 包含'messages'键的字典，通过 add_messages reducer 追加到 state
    """
    logger.info("-----Found User Upload File-----")
    # 从 config.configurable 取 file_path，而非 state —— 文件路径是请求级运行时参数，不应持久化到对话状态
    file_path = config.get("configurable", {}).get("file_path", None)

    # 容错：文件不存在 → 降级返回友好提示，不抛异常
    if not file_path or not Path(file_path).exists():
        logger.warning(f"User Upload File Not Found: {file_path}")
        return {"messages": [AIMessage(content="抱歉，我无法查看这份文件，请重新上传。")]}

    logger.info(f"Processing file: {file_path}")

    try:
        from PyPDF2 import PdfReader

        # 提取文件文本：支持 PDF（PyPDF2）和纯文本，其他格式降级
        file_path_obj = Path(file_path)
        suffix = file_path_obj.suffix.lower()
        text_content = ""

        if suffix == ".pdf":
            with open(file_path, "rb") as f:
                pdf_reader = PdfReader(f)
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_content += page_text + "\n"
            if not text_content.strip():
                return {"messages": [AIMessage(content="抱歉，这份PDF文件无法提取文本内容，可能是扫描件或图片格式。")]}
        elif suffix in (".txt", ".md", ".csv", ".log"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text_content = f.read()
        else:
            return {"messages": [AIMessage(content=f"抱歉，暂不支持 {suffix} 格式的文件分析，请上传PDF或文本文件。")]}

        # 如果文件内容过长，截取前8000字符（约2000中文token），保留头尾以避免丢失尾部关键信息
        max_chars = 8000
        if len(text_content) > max_chars:
            half = max_chars // 2
            text_content = text_content[:half] + "\n...(内容过长，已截断)...\n" + text_content[-half:]

        logger.info(f"Extracted {len(text_content)} chars from file")

        # 选择模型
        if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
            model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["file_query"])
        else:
            model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["file_query"])

        # 将文件内容注入提示词，让 LLM 基于文档内容回答
        system_prompt = FILE_QUERY_SYSTEM_PROMPT.format(file_content=text_content)
        messages = [{"role": "system", "content": system_prompt}] + state.messages
        response = await model.ainvoke(messages)
        return {"messages": [response]}

    except Exception as e:
        logger.error(f"Error processing file: {str(e)}")
        return {"messages": [AIMessage(content="抱歉，处理文件时遇到问题，请稍后重试。")]}

# 知识库查询（KG子图入口）：连接Neo4j→创建Cypher检索器→构建多工具子图→执行并返回答案
async def create_research_plan(
    state: AgentState, *, config: RunnableConfig
) -> Dict[str, List[str] | str]:
    """通过查询本地知识库回答客户问题，执行任务分解，创建分布查询计划。

    Args:
        state (AgentState): 当前代理状态，包括对话历史。
        config (RunnableConfig): 用于配置计划生成的模型。

    Returns:
        Dict[str, List[str] | str]: 包含'steps'键的字典，其中包含研究步骤列表。
    """
    logger.info("------execute local knowledge base query------")

    # 使用大模型生成查询/多跳、并行查询计划
    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["research_plan"])
    else:
        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["research_plan"])
    
    # 初始化必要参数
    # 1. Neo4j图数据库连接 - 使用配置中的连接信息
    try:
        neo4j_graph = get_neo4j_graph()
        logger.info("success to get Neo4j graph database connection")
    except Exception as e:
        logger.error(f"failed to get Neo4j graph database connection: {e}")

    # 2. 创建自定义检索器实例，根据 Graph Schema 创建 Cypher 示例，用来引导大模型生成正确的Cypher 查询语句
    cypher_retriever = NorthwindCypherRetriever()
    """当 LLM 需要生成 Cypher 查询时，这个检索器从 40+ 条预存示例中挑最相关的几条，塞进提示词让 LLM 照着写"""

    # step 3. 定义工具模式列表    
    from app.lg_agent.kg_sub_graph.kg_tools_list import cypher_query, predefined_cypher, microsoft_graphrag_query
    tool_schemas: List[type[BaseModel]] = [cypher_query, predefined_cypher, microsoft_graphrag_query]
    """ 告诉 LLM "你有三把武器可选"。每个类是一个工具的 Schema，bind_tools 后 LLM 会根据 docstring 自动选
         LLM 看到用户问题后自己决定选哪个，不需要硬编码 if-else。
    """

    # 3. 预定义的Cypher查询 - 为电商场景定义有用的查询
    from app.lg_agent.kg_sub_graph.agentic_rag_agents.components.predefined_cypher.cypher_dict import predefined_cypher_dict
    """ 就是把常用查询预先写好存起来，避免每次都让 LLM 现场生成
        当 LLM 选了 predefined_cypher 工具后，直接从字典里取现成的 Cypher 执行，又快又准
    """

    # 定义电商经营范围
    scope_description = """
    个人电商经营范围：智能家居产品，包括但不限于：
    - 智能照明（灯泡、灯带、开关）
    - 智能安防（摄像头、门锁、传感器）
    - 智能控制（温控器、遥控器、集线器）
    - 智能音箱（语音助手、音响）
    - 智能厨电（电饭煲、冰箱、洗碗机）
    - 智能清洁（扫地机器人、洗衣机）
    
    不包含：服装、鞋类、体育用品、化妆品、食品等非智能家居产品。
    """

    # 创建多工具工作流
    multi_tool_workflow = create_multi_tool_workflow(
        llm=model,
        graph=neo4j_graph,
        tool_schemas=tool_schemas, # 工具菜单：LLM 用 bind_tools 选
        predefined_cypher_dict=predefined_cypher_dict, # 预定义的Cypher查询,高频场景直接套，不生成
        cypher_example_retriever=cypher_retriever, # 抄作业源：Few-shot 示例检索
        scope_description=scope_description, # 边界：guardrails 用，过滤无关问题
        llm_cypher_validation=True, # LLM 二次检查 Cypher 正确性
    )
    
    # return multi_tool_workflow
    # 准备输入状态
    """这里的last_message就代表用户输入"""
    last_message = state.messages[-1].content if state.messages else ""
    input_state = {
        "question": last_message,
        "data": [],
        "history": []
    }
    
    # 执行工作流
    response = await multi_tool_workflow.ainvoke(input_state)
    return {"messages": [AIMessage(content=response["answer"])]}

# 幻觉检查：用LLM判断生成回复是否基于检索文档的事实，输出0/1评分
async def check_hallucinations(
    state: AgentState, *, config: RunnableConfig
) -> dict[str, Any]:
    """
    分析用户的问题，再对照从文档里查到的资料，判断回答能不能靠这些资料支撑，最后给出一个 “是 / 否” 的判断结果。
        参数：
            state：智能体当前的状态，里面存着聊天记录
            config：运行配置，里面指定了用哪个模型来分析
        返回：
            一个字典，里面有个叫 router 的字段，存着分类结果（属于哪一类、为什么这么分）

    """
    if settings.AGENT_SERVICE == ServiceType.DEEPSEEK:
        model = ChatDeepSeek(api_key=settings.DEEPSEEK_API_KEY, api_base=settings.DEEPSEEK_BASE_URL, model_name=settings.DEEPSEEK_MODEL, temperature=0.7, tags=["hallucinations"])
    else:
        model = ChatOllama(model=settings.OLLAMA_AGENT_MODEL, base_url=settings.OLLAMA_BASE_URL, temperature=0.7, tags=["hallucinations"])
    
    system_prompt = CHECK_HALLUCINATIONS.format(
        documents=state.documents,
        generation=state.messages[-1]
    )

    messages = [
        {"role": "system", "content": system_prompt}
    ] + state.messages

    logger.info("---CHECK HALLUCINATIONS---")
    
    response = cast(GradeHallucinations, await model.with_structured_output(GradeHallucinations).ainvoke(messages))
    """GradeHallucinations:用于判断是否幻觉"""
    return {"hallucination": response} 


# 定义持久化存储，也可以使用SQLiteSaver()、PostgresSaver()等
# LangGraph官方地址：https://langchain-ai.github.io/langgraph/how-tos/persistence/
checkpointer = MemorySaver()

# 定义状态图
builder = StateGraph(AgentState, input=InputState)
"""
这里InputState是外部可传入的输入
"""
# 添加节点
builder.add_node(analyze_and_route_query)
builder.add_node(respond_to_general_query)
builder.add_node(get_additional_info)
builder.add_node("create_research_plan", create_research_plan)  # 这里是子图
builder.add_node(create_image_query)
builder.add_node(create_file_query)
"""
  简单说：入参是完整 state，返回是"要更新的字段"的字典，LangGraph 负责合并。
"""

# 添加边
builder.add_edge(START, "analyze_and_route_query")
builder.add_conditional_edges("analyze_and_route_query", route_query)


graph = builder.compile(checkpointer=checkpointer)
# compile 做的事情就是把前面"画"的图变成可执行的图

# from IPython.display import Image, display
# display(Image(graph.get_graph().draw_mermaid_png()))
