# -*- coding: utf-8 -*-
from openai import OpenAI

# 创建客户端，关键是指向您的本地 SGLang 服务地址
client = OpenAI(
    base_url="http://localhost:30000/v1",  # 指向您本地的 SGLang 服务
    api_key="EMPTY",  # SGLang 服务无需 API Key 验证，此处填任意值即可
)

# 发起聊天补全请求
response = client.chat.completions.create(
    model="default",  # 模型标识，SGLang 默认支持 "default"
    messages=[
        {"role": "user", "content": "你好，请介绍一下自己"}
    ],
    max_tokens=100,
    temperature=0.7,
)

# 打印回复
print(response.choices[0].message.content)