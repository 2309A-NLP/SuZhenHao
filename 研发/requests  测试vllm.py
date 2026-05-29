# -*- coding: utf-8 -*-
import requests
import json

# vLLM 服务地址（如果 vLLM 运行在 WSL 中，请替换为 WSL 的 IP）
url = "http://172.31.45.40:8000/v1/chat/completions"

# 请求头
headers = {
    "Content-Type": "application/json"
}

# 请求体
payload = {
    "model": "Qwen/Qwen3-0.6B",
    "messages": [
        {"role": "system", "content": "你是一个直接的助手，不要输出任何思考过程，只给出最终答案。"},
        {"role": "user", "content": "你好，请介绍一下你自己"}
    ],
    "max_tokens": 200,
    "temperature": 0.7
}

# 发送 POST 请求
response = requests.post(url, headers=headers, json=payload)

# 检查状态码
if response.status_code == 200:
    result = response.json()
    # 提取模型的回复内容
    reply = result['choices'][0]['message']['content']
    print("模型回复：", reply)
else:
    print(f"请求失败，状态码：{response.status_code}")
    print("错误信息：", response.text)