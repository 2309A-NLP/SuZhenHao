"""系统测试脚本"""
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    print("\n" + "=" * 60)
    print("测试1: 模块导入")
    print("=" * 60)
    try:
        import config  # noqa: F401
        print("✓ config 模块导入成功")
        import query_processor  # noqa: F401
        print("✓ query_processor 模块导入成功")
        import document_loader  # noqa: F401
        print("✓ document_loader 模块导入成功")
        import embedding  # noqa: F401
        print("✓ embedding 模块导入成功")
        import llm_agent  # noqa: F401
        print("✓ llm_agent 模块导入成功")
        return True
    except Exception as exc:
        print(f"✗ 模块导入失败: {exc}")
        return False


def test_query_processor():
    print("\n" + "=" * 60)
    print("测试2: Query处理模块")
    print("=" * 60)
    try:
        from query_processor import QueryProcessor

        processor = QueryProcessor()
        query = "公司2023年的财务状况如何？"
        intent = processor.get_intent(query)
        print(f"✓ 意图识别: '{query}' -> {intent}")
        sub_queries = processor.decompose_query("公司的财务状况和风险分析是什么？")
        print(f"✓ 问题分解: {len(sub_queries)} 个子问题")
        result = processor.process_query(query)
        print(f"✓ 完整处理:\n  - 意图: {result['intent']}\n  - 子查询数: {len(result['sub_queries'])}\n  - 实体: {result['entities']}")
        return True
    except Exception as exc:
        print(f"✗ Query处理失败: {exc}")
        return False


def test_config():
    print("\n" + "=" * 60)
    print("测试6: 系统配置")
    print("=" * 60)
    try:
        from config import CHUNK_SIZE, DEEPSEEK_API_KEY, MAX_TOKENS, PDF_PATH, TEMPERATURE, TOP_K

        print(f"✓ API密钥: {'已配置' if DEEPSEEK_API_KEY else '未配置'}")
        print(f"✓ PDF路径: {PDF_PATH}")
        print(f"✓ 块大小: {CHUNK_SIZE}")
        print(f"✓ 检索数量: {TOP_K}")
        print(f"✓ 温度参数: {TEMPERATURE}")
        print(f"✓ 最大令牌: {MAX_TOKENS}")
        return True
    except Exception as exc:
        print(f"✗ 配置测试失败: {exc}")
        return False


def test_document_processing():
    print("\n" + "=" * 60)
    print("测试4: 文档处理")
    print("=" * 60)
    try:
        from document_loader import TextChunker

        test_text = "这是一个测试文本。这个文本用来演示文本分块的功能。" * 10
        chunker = TextChunker(chunk_size=100, overlap=20)
        chunks = chunker.chunk_text(test_text, page_num=1)
        print(f"✓ 文本分块: {len(test_text)} 字符 -> {len(chunks)} 个块")
        if chunks:
            print(f"✓ 第一个块: {chunks[0]['content'][:50]}...")
        return True
    except Exception as exc:
        print(f"✗ 文档处理失败: {exc}")
        return False


def test_embedding():
    print("\n" + "=" * 60)
    print("测试5: 向量嵌入")
    print("=" * 60)
    try:
        from embedding import EmbeddingManager
        import numpy as np  # noqa: F401

        manager = EmbeddingManager()
        if not manager.available:
            print("⚠️  测试跳过: 本地未缓存 sentence-transformers 模型")
            return None

        test_texts = ["公司财务状况", "产品介绍", "风险分析"]
        embeddings = manager.model.encode(test_texts, convert_to_numpy=True)
        print(f"✓ 文本嵌入: {len(test_texts)} 个文本 -> {embeddings.shape}")
        print(f"✓ 嵌入维度: {embeddings.shape[1]}")
        from sklearn.metrics.pairwise import cosine_similarity

        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
        print(f"✓ 相似度示例: '财务' vs '产品' = {similarity:.3f}")
        return True
    except Exception as exc:
        print(f"✗ 向量嵌入测试失败: {exc}")
        return False


def test_deepseek_api():
    print("\n" + "=" * 60)
    print("测试3: DeepSeek API连接")
    print("=" * 60)
    try:
        from llm_agent import DeepSeekLLM

        llm = DeepSeekLLM()
        if not llm.available:
            print("⚠️  测试跳过: 未配置 DeepSeek API Key")
            return None

        print("测试API连接...")
        if llm.test_connection():
            print("✓ API连接成功")
            return True

        print("✗ API连接失败")
        return False
    except Exception as exc:
        print(f"✗ DeepSeek API测试失败: {exc}")
        return False


def run_all_tests():
    print("\n" + "=" * 60)
    print("开始运行系统测试")
    print("=" * 60)

    tests = [
        ("模块导入", test_imports),
        ("Query处理", test_query_processor),
        ("系统配置", test_config),
        ("文档处理", test_document_processing),
        ("向量嵌入", test_embedding),
        ("DeepSeek API", test_deepseek_api),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as exc:
            print(f"\n✗ 测试异常: {exc}")
            results[name] = False

    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    for name, result in results.items():
        if result is True:
            status = "✅ 通过"
        elif result is False:
            status = "❌ 失败"
        else:
            status = "⏭️  跳过"
        print(f"{status} - {name}")

    passed = sum(1 for r in results.values() if r is True)
    skipped = sum(1 for r in results.values() if r is None)
    total = len(results)
    print(f"\n总体: {passed}/{total} 通过，{skipped} 项跳过")
    return passed > 0


def main():
    run_all_tests()


if __name__ == "__main__":
    main()
