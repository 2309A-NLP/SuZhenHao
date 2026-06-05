@echo off
REM 快速启动聊天 Web 界面

REM 设置 Python 解释器路径
set "PYTHON=D:/an10-1/envs/nlp_2/python.exe"

echo 启动中: http://localhost:8080
start http://localhost:8080
%PYTHON% api_server.py
pause