"""
RAG检索增强生成模块
- 构建Prompt
- 调用MiMo API生成回答
"""

from openai import OpenAI
from pdf_processor import PDFProcessor
from config import MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL, TOP_K


class RAGChain:
    def __init__(self, pdf_processor: PDFProcessor):
        self.pdf_processor = pdf_processor
        self.client = OpenAI(
            api_key=MIMO_API_KEY,
            base_url=MIMO_BASE_URL
        )
        self.history = []  # 多轮对话历史

    def build_prompt(self, query: str, context_docs: list) -> str:
        """构建RAG Prompt"""
        # 拼接检索到的上下文
        context = "\n\n---\n\n".join(
            [doc.page_content for doc, score in context_docs]
        )

        prompt = f"""你是一个智能文档问答助手。请根据以下参考文档内容来回答用户的问题。

## 规则
1. 只根据提供的参考文档内容回答，不要编造信息
2. 如果文档中没有相关信息，请如实说明
3. 回答要准确、清晰、有条理
4. 支持中文和英文问答，用用户提问的语言回答

## 参考文档内容
{context}

## 用户问题
{query}

## 回答"""
        return prompt

    def generate_answer(self, query: str) -> dict:
        """
        完整的RAG流程：检索 + 生成
        返回：回答 + 引用来源
        """
        # 1. 检索相关文档
        relevant_docs = self.pdf_processor.search(query, top_k=TOP_K)

        if not relevant_docs:
            return {
                "answer": "抱歉，未找到相关文档内容，请先上传PDF文档。",
                "sources": []
            }

        # 2. 构建Prompt
        prompt = self.build_prompt(query, relevant_docs)

        # 3. 构建消息（含多轮对话）
        messages = [
            {"role": "system", "content": "你是一个智能文档问答助手，擅长从文档中提取信息并准确回答问题。支持中文和英文。"}
        ]
        # 加入历史对话
        for role, content in self.history[-6:]:  # 最近3轮
            messages.append({"role": role, "content": content})
        # 加入当前问题
        messages.append({"role": "user", "content": prompt})

        # 4. 调用MiMo API
        try:
            response = self.client.chat.completions.create(
                model=MIMO_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=2048
            )
            answer = response.choices[0].message.content
        except Exception as e:
            return {
                "answer": f"API调用出错：{str(e)}",
                "sources": []
            }

        # 5. 保存对话历史
        self.history.append(("user", query))
        self.history.append(("assistant", answer))

        # 6. 提取来源信息
        sources = []
        for doc, score in relevant_docs:
            sources.append({
                "content": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content,
                "score": float(score)
            })

        return {
            "answer": answer,
            "sources": sources
        }

    def clear_history(self):
        """清空对话历史"""
        self.history = []
