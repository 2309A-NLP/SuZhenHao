"""
LLM 代理模块 - 支持 DeepSeek API 和本地兜底回答
"""
from typing import Dict, List

import requests

from config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, MAX_TOKENS, TEMPERATURE


class DeepSeekLLM:
    """DeepSeek LLM 代理。"""

    def __init__(
        self,
        api_key: str = DEEPSEEK_API_KEY,
        api_base: str = DEEPSEEK_API_BASE,
        model: str = DEEPSEEK_MODEL,
    ):
        self.api_key = api_key or ""
        self.api_base = api_base
        self.model = model
        self.available = bool(self.api_key)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def generate(self, prompt: str, max_tokens: int = MAX_TOKENS, temperature: float = TEMPERATURE) -> str:
        if not self.available:
            raise RuntimeError("未配置 DEEPSEEK_API_KEY")

        try:
            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            }

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=30,
            )

            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"]["content"]

            error_msg = response.json().get("error", {}).get("message", "未知错误")
            raise RuntimeError(f"API 请求失败: {error_msg}")
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"网络请求失败: {exc}") from exc

    def test_connection(self) -> bool:
        if not self.available:
            print("⚠️  未配置 DeepSeek API Key，跳过在线连接测试")
            return False

        try:
            print("测试 DeepSeek API 连接...")
            self.generate("请只回复 OK", max_tokens=10)
            print("✓ API 连接成功")
            return True
        except Exception as exc:
            print(f"✗ API 连接失败: {exc}")
            return False


class RAGGenerator:
    """基于检索结果的回答生成器。"""

    def __init__(self, llm: DeepSeekLLM = None):
        self.llm = llm or DeepSeekLLM()
        self.system_prompt = (
            "你是一个专业的问答助手。请严格依据提供的参考文档回答，"
            "不要编造信息。若文档中没有相关信息，请明确说明未找到。"
        )

    def _build_context(self, retrieved_docs: List[Dict], lang: str = "zh") -> str:
        if not retrieved_docs:
            return "（未找到相关文档）" if lang == "zh" else "(No relevant documents found)"

        parts = []
        for i, doc in enumerate(retrieved_docs, 1):
            if lang == "en":
                parts.append(
                    f"[Reference {i}] Page {doc.get('page', '?')}, relevance {doc.get('similarity', 0):.2%}\n"
                    f"{doc.get('content', '')}"
                )
            else:
                parts.append(
                    f"[参考{i}] 第{doc.get('page', '?')}页，相关度 {doc.get('similarity', 0):.2%}\n"
                    f"{doc.get('content', '')}"
                )
        return "\n\n".join(parts)

    def _build_prompt(self, query: str, context: str, lang: str = "zh") -> str:
        if lang == "en":
            return f"""You are a professional Q&A assistant. Answer strictly based on the provided reference documents. Do not fabricate information. If the document does not contain relevant information, clearly state that it was not found. **You MUST respond in English.**

Reference Documents:
{context}

User Question:
{query}

Please provide a concise and accurate answer in English."""
        else:
            return f"""{self.system_prompt}

参考文档：
{context}

用户问题：
{query}

请给出简洁、准确的答案。"""

    def _fallback_answer(self, query: str, retrieved_docs: List[Dict], lang: str = "zh") -> str:
        if not retrieved_docs:
            if lang == "en":
                return "No relevant information found in the document."
            return "文档中未找到相关信息。"

        highlights = []
        for doc in retrieved_docs[:3]:
            text = doc.get("content", "").replace("\n", " ").strip()
            if text:
                if lang == "en":
                    highlights.append(f"Page {doc.get('page', '?')}: {text[:160]}...")
                else:
                    highlights.append(f"第{doc.get('page', '?')}页：{text[:160]}...")
        if lang == "en":
            return "Based on relevant document content, the following clues were found:\n" + "\n".join(highlights)
        return "根据文档相关内容，找到如下线索：\n" + "\n".join(highlights)

    def generate_answer(self, query: str, retrieved_docs: List[Dict], lang: str = "zh") -> Dict:
        context = self._build_context(retrieved_docs, lang)
        prompt = self._build_prompt(query, context, lang)

        if self.llm.available:
            try:
                answer = self.llm.generate(prompt)
            except Exception as exc:
                if lang == "en":
                    answer = f"LLM call failed, switched to local answer: {exc}\n\n{self._fallback_answer(query, retrieved_docs, lang)}"
                else:
                    answer = f"LLM 调用失败，已切换到本地回答：{exc}\n\n{self._fallback_answer(query, retrieved_docs, lang)}"
        else:
            answer = self._fallback_answer(query, retrieved_docs, lang)

        return {
            "query": query,
            "answer": answer,
            "sources": self._extract_sources(retrieved_docs),
            "confidence": self._calculate_confidence(retrieved_docs),
        }

    def _extract_sources(self, retrieved_docs: List[Dict]) -> List[Dict]:
        return [
            {
                "page": doc.get("page"),
                "chunk_id": doc.get("chunk_id"),
                "similarity": doc.get("similarity"),
            }
            for doc in retrieved_docs
        ]

    def _calculate_confidence(self, retrieved_docs: List[Dict]) -> float:
        if not retrieved_docs:
            return 0.0

        max_similarity = max(doc.get("similarity", 0) for doc in retrieved_docs)
        doc_count_factor = min(len(retrieved_docs) / 5, 1.0)
        return min(max_similarity * 0.7 + doc_count_factor * 0.3, 1.0)


class QASystem:
    """完整问答系统。"""

    def __init__(self, retriever, query_processor=None):
        self.retriever = retriever
        self.query_processor = query_processor
        self.generator = RAGGenerator()

    def answer(self, query: str, lang: str = "zh") -> Dict:
        try:
            if self.query_processor:
                processed = self.query_processor.process_query(query)
                print(f"\n[Query分析] 意图: {processed['intent']}")

            print("[检索中] 搜索相关文档...")
            retrieved_docs = self.retriever.retrieve(query)
            print(f"[检索完成] 找到 {len(retrieved_docs)} 个相关段落")
            print("[生成中] LLM 正在生成答案...")
            return self.generator.generate_answer(query, retrieved_docs, lang)
        except Exception as exc:
            if lang == "en":
                return {
                    "query": query,
                    "answer": f"Error processing question: {exc}",
                    "sources": [],
                    "confidence": 0.0,
                }
            return {
                "query": query,
                "answer": f"处理问题时出错: {exc}",
                "sources": [],
                "confidence": 0.0,
            }


if __name__ == "__main__":
    llm = DeepSeekLLM()
    llm.test_connection()
