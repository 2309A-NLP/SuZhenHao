#!/bin/bash
# 快速启动脚本 (Linux/Mac)

echo ""
echo "============================================================"
echo "招股说明书智能问答系统 - 快速启动"
echo "============================================================"
echo ""

# 设置 Python 解释器路径
PYTHON="D:/an10-1/envs/nlp_2/python.exe"

echo "启动系统..."
echo ""
echo "选择启动方式:"
echo " 1) 命令行交互模式 (推荐新手)"
echo " 2) Web界面 (推荐)"
echo " 3) 单个查询"
echo ""

read -p "请输入选择 (1-3): " choice

case $choice in
    1)
        echo ""
        echo "启动命令行模式..."
        echo ""
        $PYTHON 1.py
        ;;
    2)
        echo ""
        echo "启动Web界面..."
        echo "浏览器将自动打开: http://localhost:8080"
        echo ""
        start http://localhost:8080
        $PYTHON api_server.py
        ;;
    3)
        read -p "请输入问题: " query
        echo ""
        $PYTHON 1.py "$query"
        ;;
    *)
        echo "无效的选择"
        ;;
esac

echo ""