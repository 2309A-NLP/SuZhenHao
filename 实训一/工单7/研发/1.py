"""主程序入口 - 快速启动 RAG 问答系统"""
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

from config import FAISS_INDEX_PATH
from document_loader import prepare_documents
from embedding import RAGRetriever
from llm_agent import DeepSeekLLM, QASystem
from query_processor import QueryProcessor


def initialize_system():
    print("\n" + "=" * 60)
    print("🚀 RAG问答系统初始化")
    print("=" * 60)

    retriever = RAGRetriever()
    query_processor = QueryProcessor()

    index_exists = os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index")) or os.path.exists(
        os.path.join(FAISS_INDEX_PATH, "chunks.pkl")
    )
    non_interactive = len(sys.argv) > 1 or not sys.stdin.isatty()

    if index_exists:
        print("\n[加载中] 从本地索引加载...")
        try:
            retriever.load_from_index()
            print("✓ 索引加载完成")
        except Exception as exc:
            print(f"✗ 加载失败: {exc}")
            print("将重新构建索引...")
            chunks = prepare_documents()
            retriever.initialize(chunks)
    else:
        print("\n[构建中] 首次运行，构建索引...")
        chunks = prepare_documents()
        retriever.initialize(chunks)

    llm = DeepSeekLLM()
    if llm.available:
        print("\n[测试] 检查 DeepSeek API 连接...")
        llm.test_connection()
    else:
        print("\n[提示] 未配置 DeepSeek API Key，将使用本地兜底回答")

    qa_system = QASystem(retriever, query_processor)

    print("\n" + "=" * 60)
    print("✓ 系统初始化完成")
    print("=" * 60)
    return qa_system


def interactive_mode(qa_system: QASystem):
    print("\n" + "=" * 60)
    print("📚 进入问答模式 (输入 'quit' 退出)")
    print("=" * 60)

    while True:
        print("\n" + "-" * 60)
        query = input("\n👤 请输入您的问题: ").strip()

        if query.lower() in ["quit", "exit", "q"]:
            print("\n👋 再见！")
            break

        if not query:
            print("❌ 请输入有效的问题")
            continue

        print("\n🔍 正在处理您的问题...")
        print("-" * 60)

        try:
            result = qa_system.answer(query)

            print("\n" + "=" * 60)
            print("📋 回答结果")
            print("=" * 60)
            print(f"\n💬 问题: {result['query']}")
            print(f"\n📄 答案:\n{result['answer']}")
            print(f"\n🎯 置信度: {result['confidence']:.1%}")

            if result["sources"]:
                print(f"\n📚 参考来源({len(result['sources'])} 个):")
                for i, source in enumerate(result["sources"], 1):
                    print(f"   {i}. 第{source['page']}页(相似度 {source['similarity']:.1%})")
        except Exception as exc:
            print(f"\n❌ 错误: {exc}")


def batch_mode(qa_system: QASystem, queries_file: str):
    if not os.path.exists(queries_file):
        print(f"❌ 查询文件不存在: {queries_file}")
        return

    print(f"\n📄 从文件加载查询: {queries_file}")
    with open(queries_file, "r", encoding="utf-8") as f:
        queries = [line.strip() for line in f if line.strip()]

    print(f"📊 共 {len(queries)} 个查询")

    results = []
    for i, query in enumerate(queries, 1):
        print(f"\n[{i}/{len(queries)}] 处理: {query}")
        results.append(qa_system.answer(query))

    output_file = queries_file.replace(".txt", "_results.txt")
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(f"Q: {result['query']}\n")
            f.write(f"A: {result['answer']}\n")
            f.write(f"Confidence: {result['confidence']:.1%}\n")
            f.write("-" * 60 + "\n\n")

    print(f"\n✓ 结果已保存到: {output_file}")


def main():
    qa_system = initialize_system()

    if len(sys.argv) > 1:
        if sys.argv[1] == "--batch" and len(sys.argv) > 2:
            batch_mode(qa_system, sys.argv[2])
        else:
            query = " ".join(sys.argv[1:])
            print(f"\n📚 查询: {query}\n")
            result = qa_system.answer(query)
            print(f"\n📄 答案:\n{result['answer']}\n")
            print(f"🎯 置信度: {result['confidence']:.1%}")
    else:
        interactive_mode(qa_system)


if __name__ == "__main__":
    main()
