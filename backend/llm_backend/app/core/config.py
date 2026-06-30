from pydantic_settings import BaseSettings
from enum import Enum
from pathlib import Path
"""全局配置中心"""
# 获取项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"

class ServiceType(str, Enum):
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"

class Settings(BaseSettings):
    # Deepseek settings
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    
    # Vision Model settings (独立配置)
    VISION_API_KEY: str = ""
    VISION_BASE_URL: str = "https://api.deepseek.com"
    VISION_MODEL: str = "deepseek-chat"
    
    # Ollama settings
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_CHAT_MODEL: str = "qwen2.5"
    OLLAMA_REASON_MODEL: str = "deepseek-r1"
    OLLAMA_EMBEDDING_MODEL: str = "bge-m3"
    OLLAMA_AGENT_MODEL: str = "qwen2.5"
    # Service selection
    CHAT_SERVICE: ServiceType = ServiceType.DEEPSEEK
    REASON_SERVICE: ServiceType = ServiceType.OLLAMA
    AGENT_SERVICE: ServiceType = ServiceType.DEEPSEEK
    
    # Search settings
    SERPAPI_KEY: str = ""
    SEARCH_RESULT_COUNT: int = 3
    
    # Database settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "assist_gen"
    
    # Neo4j settings
    NEO4J_URL: str = "bolt://localhost:7687"
    NEO4J_USERNAME: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_DATABASE: str = "neo4j"
    
    # JWT settings
    SECRET_KEY: str = "your-secret-key"  # 在生产环境中使用安全的密钥
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Redis settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""
    REDIS_CACHE_EXPIRE: int = 3600
    REDIS_CACHE_THRESHOLD: float = 0.8
    
    # Embedding settings
    EMBEDDING_PROVIDER: str = "local"     # "local" | "dashscope"
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v4"
    EMBEDDING_DIMENSION: int = 512
    EMBEDDING_BATCH_SIZE: int = 10  # DashScope text-embedding-v4 limit: max 10 per request
    EMBEDDING_CACHE_ENABLED: bool = True
    EMBEDDING_THRESHOLD: float = 0.90  # 语义相似度阈值
    
    # GraphRAG settings
    GRAPHRAG_PROJECT_DIR: str = "llm_backend/app/graphrag"  # GraphRAG项目目录
    GRAPHRAG_DATA_DIR: str = "data"                         # 数据目录名称
    GRAPHRAG_QUERY_TYPE: str = "local"                      # 查询类型
    GRAPHRAG_RESPONSE_TYPE: str = "text"                    # 响应类型
    GRAPHRAG_COMMUNITY_LEVEL: int = 3                       # 社区级别
    GRAPHRAG_DYNAMIC_COMMUNITY: bool = False                # 是否动态选择社区

    # Qdrant settings
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_COLLECTION_PRODUCTS: str = "assistgen_products"
    QDRANT_VECTOR_SIZE: int = 512
    QDRANT_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # Product retrieval settings
    PRODUCT_DATA_PATH: str = "app/data/products.csv"
    RETRIEVAL_DENSE_TOP_K: int = 30
    RETRIEVAL_SPARSE_TOP_K: int = 30
    RETRIEVAL_RERANK_TOP_K: int = 8

    # Recommendation scoring weights. Tune these after real ecommerce data lands.
    RECOMMENDATION_RETRIEVAL_WEIGHT: float = 0.35
    RECOMMENDATION_GRAPH_WEIGHT: float = 0.50
    RECOMMENDATION_BUSINESS_WEIGHT: float = 0.15
    RECOMMENDATION_TOP_K: int = 6

    # External reranker API. If empty, Hybrid RAG falls back to fusion score.
    # RERANKER_PROVIDER: "dashscope" to use DashScope gte-rerank-v2, "" for local fallback.
    RERANKER_PROVIDER: str = ""
    RERANKER_API_URL: str = ""
    RERANKER_API_KEY: str = ""
    RERANKER_MODEL: str = "gte-rerank-v2"
    RERANKER_TIMEOUT_SECONDS: int = 30
    
    @property
    def DATABASE_URL(self) -> str:
        return f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    @property
    def REDIS_URL(self) -> str:
        """构建Redis URL"""
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    @property
    def NEO4J_CONN_URL(self) -> str:
        """构建Neo4j连接URL"""
        return f"{self.NEO4J_URL}"
    
    class Config:
        env_file = str(ENV_FILE)  # 使用绝对路径
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings() 
