"""多语言支持验证脚本"""
import requests
import json
import sys
import os

BASE = "http://localhost:8080"

def test_chat(query, lang, label):
    """测试问答接口"""
    print(f"\n{'='*60}")
    print(f"[{label}] lang={lang}")
    print(f"问题: {query}")
    print(f"{'='*60}")
    try:
        resp = requests.post(
            f"{BASE}/api/chat",
            json={"query": query, "lang": lang},
            timeout=60,
        )
        print(f"状态码: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"答案: {data['answer'][:300]}")
            print(f"置信度: {data['confidence']:.1%}")
            print(f"来源数: {len(data.get('sources', []))}")
            return True
        else:
            print(f"错误: {resp.text}")
            return False
    except Exception as e:
        print(f"请求失败: {e}")
        return False


def test_health():
    """测试健康检查"""
    try:
        resp = requests.get(f"{BASE}/api/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    print("=" * 60)
    print("多语言支持验证")
    print("=" * 60)

    # 检查服务是否运行
    if not test_health():
        print("错误: 服务未运行，请先启动 api_server.py")
        sys.exit(1)
    print("✓ 服务健康检查通过")

    results = []

    # 中文测试
    zh_queries = [
        "公司的主营业务是什么？",
        "公司面临的主要风险因素有哪些？",
        "公司的主要产品有哪些？",
    ]

    print("\n\n" + "─" * 60)
    print("  中文问答测试")
    print("─" * 60)
    for q in zh_queries:
        ok = test_chat(q, "zh", "中文")
        results.append(("zh", q, ok))

    # 英文测试
    en_queries = [
        "What is the company's main business?",
        "What are the main risk factors the company faces?",
        "What are the company's main products?",
    ]

    print("\n\n" + "─" * 60)
    print("  英文问答测试")
    print("─" * 60)
    for q in en_queries:
        ok = test_chat(q, "en", "English")
        results.append(("en", q, ok))

    # 汇总
    print("\n\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    zh_ok = sum(1 for l, q, o in results if l == "zh" and o)
    zh_total = sum(1 for l, q, o in results if l == "zh")
    en_ok = sum(1 for l, q, o in results if l == "en" and o)
    en_total = sum(1 for l, q, o in results if l == "en")

    print(f"  中文: {zh_ok}/{zh_total} 通过")
    print(f"  英文: {en_ok}/{en_total} 通过")
    print(f"  总计: {zh_ok + en_ok}/{zh_total + en_total} 通过")

    if zh_ok == zh_total and en_ok == en_total:
        print("\n  ✓ 所有多语言测试通过！")
    else:
        print("\n  ✗ 部分测试失败，请检查日志")

    print("=" * 60)


if __name__ == "__main__":
    main()