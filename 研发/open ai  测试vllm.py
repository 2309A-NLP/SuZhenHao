#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from openai import OpenAI

# ========== 配置 ==========
API_BASE_URL = "http://172.31.45.40:8000/v1"   # 注意末尾的 /v1
API_KEY = "EMPTY"                              # vLLM 默认不校验 key

# 创建客户端
client = OpenAI(
    api_key=API_KEY,
    base_url=API_BASE_URL,
)

# ========== 发送请求 ==========
try:
    response = client.chat.completions.create(
        model="Qwen/Qwen3-0.6B",
        messages=[
            {"role": "system", "content": "你是一个直接的助手，不要输出任何思考过程（不要使用<think>标签），只给出最终答案。"},
            {"role": "user", "content": "你好，请介绍一下你自己"}
        ],
        max_tokens=200,
        temperature=0.7,
        # stream=False,   # 若需要流式输出，改为 True 并参考下方注释代码
    )

    # 提取并打印回复内容
    reply = response.choices[0].message.content
    print("模型回复：", reply)

except Exception as e:
    print(f"请求失败：{e}")