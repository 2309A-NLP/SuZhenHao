# -*- coding: utf-8 -*-
import requests
import json

url = "http://localhost:30000/v1/chat/completions"

payload = {
    "model": "default",
    "messages": [
        {"role": "user", "content": "讲一个关于 AI 的短故事，100字左右"}
    ],
    "stream": True,          # 开启流式输出
    "max_tokens": 200
}

headers = {
    "Content-Type": "application/json"
}

# 使用 stream=True 获取事件流
with requests.post(url, headers=headers, json=payload, stream=True) as response:
    if response.status_code != 200:
        print(f"错误: {response.status_code}")
        print(response.text)
        exit()

    # 逐行读取 SSE 数据
    for line in response.iter_lines(decode_unicode=True):
        if line:
            # SSE 格式: data: {json}
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    # 提取增量内容
                    if "choices" in chunk and len(chunk["choices"]) > 0:
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            print(content, end="", flush=True)
                except json.JSONDecodeError:
                    continue
    print()  # 换行




