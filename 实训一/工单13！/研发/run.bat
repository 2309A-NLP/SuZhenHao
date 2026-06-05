@echo off
REM 快速启动脚本 (Windows)

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo 招股说明书智能问答系统 - 快速启动
echo ============================================================
echo.

REM 设置 Python 解释器路径
set "PYTHON=D:/an10-1/envs/nlp_2/python.exe"

echo.
echo [1/1] 启动系统...
echo.
echo 选择启动方式:
echo  1) 命令行交互模式
echo  2) 聊天式 Web 界面 (推荐)
echo  3) 单个查询
echo  4) Streamlit 旧版界面
echo.

set /p choice="请输入选择 (1-4): "

if "%choice%"=="1" (
    echo.
    echo 启动命令行模式...
    echo.
    %PYTHON% 1.py
) else if "%choice%"=="2" (
    echo.
    echo 启动聊天 Web 界面...
    echo 浏览器将自动打开: http://localhost:8080
    echo.
    start http://localhost:8080
    %PYTHON% api_server.py
) else if "%choice%"=="3" (
    set /p query="请输入问题: "
    echo.
    %PYTHON% 1.py "%query%"
) else if "%choice%"=="4" (
    echo.
    echo 启动 Streamlit 界面...
    start http://localhost:8501
    %PYTHON% -m streamlit run ui_app.py
) else (
    echo 无效的选择
)

echo.
pause