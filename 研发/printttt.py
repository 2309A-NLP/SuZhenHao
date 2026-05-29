# -*- coding: utf-8 -*-
import requests
response = requests.post(
    "http://localhost:8080/chat",
    json={"user_id": "test", "message": "劳动合同到期不续签有赔偿吗？"}
)
print(response.json())



# 离婚冷静期是多少天？
# 企业必须为职工缴纳工伤保险吗？
# 未成年人打赏主播能退款吗？
# 劳动合同到期不续签有赔偿吗？




# ！！! 前提必须先运行main.py
# 需要先运行main.py 运行  printttt.py  是在python看到答案
# 网页版   http://localhost:8080/docs  输入问题进行回答
# postman  http://localhost:8080/chat  在body中进行问题  send后出答案

# http://localhost:8080