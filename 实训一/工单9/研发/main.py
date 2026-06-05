"""
智能文档问答系统 - 启动入口
运行方式：streamlit run app.py
"""

import subprocess
import sys

if __name__ == "__main__":
    print("🦞 正在启动智能文档问答系统...")
    print("📌 请在浏览器中打开 http://localhost:8501")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
