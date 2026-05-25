from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, ConfigDict
import re

class BaseCypherExampleRetriever(BaseModel, ABC):
    """
        这是一个示例检索器的抽象基类。
        它的子类必须实现 get_examples(query, k) -> str 这个方法，否则用不了
        约定：输入query → 输出格式化示例字符串

        为什么要抽这个抽象基类？

        因为 "从哪找 Cypher 示例" 有两种完全不同的实现路径：
        BaseCypherExampleRetriever  (约定：输入query → 输出格式化示例字符串)
                │
                ├── NorthwindCypherRetriever    ← 硬编码示例 + 关键词匹配打分
                │
                └── Neo4jVectorSearchCypherExampleRetriever  ← 向量相似度检索，从 Neo4j 查


    """
    # Pydantic 模型里要混用非标准类型时，必须开的开关。写在基类里，所有子类自动继承，不用每个子类再配一遍
    model_config: ConfigDict = ConfigDict(**{"arbitrary_types_allowed": True})  # type: ignore[misc]


    @abstractmethod
    def get_examples(self, query: str, k: int = 5) -> str:
        """
        根据用户查询返回相关的Cypher查询示例
        
        Parameters
        ----------
        query : str
            用户的自然语言查询
        k : int, optional
            返回的示例数量, by default 5
            
        Returns
        -------
        str
            格式化的示例字符串，每个示例包含问题和对应的Cypher查询
        """
        pass
