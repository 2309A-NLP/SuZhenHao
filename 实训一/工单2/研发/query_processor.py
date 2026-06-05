"""
Query理解模块 - 处理用户问题的意图识别和分解
"""
import re
from typing import Dict, List, Any


class QueryProcessor:
    """查询处理器 - 实现意图识别、消歧、分解和抽象"""
    
    def __init__(self):
        # 定义查询意图分类
        self.intent_keywords = {
            "财务信息": ["财务", "收入", "利润", "成本", "利润率", "资产", "负债", "现金"],
            "公司信息": ["公司", "企业", "组织结构", "管理团队", "高管", "股东", "注册地"],
            "产品服务": ["产品", "服务", "业务", "主营业务", "经营范围"],
            "风险分析": ["风险", "风险因素", "不确定性", "竞争风险", "市场风险"],
            "发展战略": ["战略", "规划", "目标", "发展方向", "投资方向"],
            "市场分析": ["市场", "行业", "竞争", "市场规模", "增长率"],
        }
        
    def get_intent(self, query: str) -> str:
        """识别查询意图"""
        query_lower = query.lower()
        for intent, keywords in self.intent_keywords.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return intent
        return "一般信息"
    
    def decompose_query(self, query: str) -> List[str]:
        """分解复杂查询为多个子问题"""
        # 按照连接词分解
        connectors = ["并且", "和", "还有", "另外", "以及", "、"]
        
        sub_queries = [query]  # 默认不分解
        
        for connector in connectors:
            if connector in query:
                parts = query.split(connector)
                if len(parts) > 1:
                    sub_queries = [p.strip() for p in parts if p.strip()]
                    break
        
        return sub_queries
    
    def extract_key_entities(self, query: str) -> Dict[str, Any]:
        """提取关键实体（时间、金额、指标等）"""
        entities = {
            "time": self._extract_time(query),
            "number": self._extract_numbers(query),
            "keywords": self._extract_keywords(query),
        }
        return entities
    
    def _extract_time(self, query: str) -> List[str]:
        """提取时间表达"""
        time_patterns = r'\d{4}年|第\d+季度|2024|2023|2022'
        return re.findall(time_patterns, query)
    
    def _extract_numbers(self, query: str) -> List[str]:
        """提取数字和金额"""
        number_patterns = r'\d+\.?\d*(?:万|亿|百万|千万)?'
        return re.findall(number_patterns, query)
    
    def _extract_keywords(self, query: str) -> List[str]:
        """提取关键词"""
        # 移除常见停用词
        stopwords = {"了", "吗", "呢", "啊", "的", "是", "有", "和", "与", "中"}
        words = query.split()
        return [w for w in words if len(w) > 1 and w not in stopwords]
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """处理查询 - 综合的查询处理"""
        return {
            "original_query": query,
            "intent": self.get_intent(query),
            "sub_queries": self.decompose_query(query),
            "entities": self.extract_key_entities(query),
        }


if __name__ == "__main__":
    processor = QueryProcessor()
    
    # 测试示例
    test_queries = [
        "公司2023年的财务状况如何，收入和利润分别是多少？",
        "请介绍公司的主营业务和产品服务",
        "公司面临哪些主要风险？",
    ]
    
    for query in test_queries:
        result = processor.process_query(query)
        print(f"\n查询: {query}")
        print(f"意图: {result['intent']}")
        print(f"子查询: {result['sub_queries']}")
        print(f"关键实体: {result['entities']}")
