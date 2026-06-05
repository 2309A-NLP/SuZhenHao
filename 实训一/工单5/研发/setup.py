"""
项目初始化脚本 - 一键配置项目环境
"""
import os
import sys
import subprocess
from pathlib import Path


def setup_environment():
    """初始化项目环境"""
    print("="*60)
    print("🚀 招股说明书问答系统 - 项目初始化")
    print("="*60)
    
    project_root = Path(__file__).parent
    
    # Step 1: 创建目录
    print("\n[1/4] 创建项目目录...")
    dirs_to_create = [
        project_root / "data",
        project_root / "results",
        project_root / "data" / "faiss_index",
    ]
    
    for dir_path in dirs_to_create:
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ {dir_path}")
    
    # Step 2: 检查依赖
    print("\n[2/4] 检查并安装依赖...")
    requirements_file = project_root / "requirements.txt"
    
    if requirements_file.exists():
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install", 
                "-r", str(requirements_file)
            ])
            print("  ✓ 依赖安装完成")
        except subprocess.CalledProcessError:
            print("  ✗ 依赖安装失败，请手动运行: pip install -r requirements.txt")
            return False
    else:
        print("  ✗ requirements.txt 文件不存在")
        return False
    
    # Step 3: 检查PDF文件
    print("\n[3/4] 检查PDF文件...")
    pdf_path = project_root / "data" / "招股说明书1-无水印.pdf"
    
    if pdf_path.exists():
        print(f"  ✓ PDF文件已找到: {pdf_path}")
    else:
        print(f"  ⚠️  PDF文件未找到: {pdf_path}")
        print("  请手动将PDF文件放入 data/ 目录")
    
    # Step 4: 验证配置
    print("\n[4/4] 验证配置...")
    config_file = project_root / "config.py"
    
    try:
        sys.path.insert(0, str(project_root))
        from config import DEEPSEEK_API_KEY
        
        if DEEPSEEK_API_KEY and not DEEPSEEK_API_KEY.startswith("sk-"):
            print("  ⚠️  DeepSeek API密钥可能未正确配置")
        else:
            print("  ✓ API配置验证完成")
    except Exception as e:
        print(f"  ✗ 配置验证失败: {e}")
    
    print("\n" + "="*60)
    print("✓ 项目初始化完成！")
    print("="*60)
    
    print("\n📖 下一步：")
    print("  1. 确保已将PDF文件放入 data/ 目录")
    print("  2. 运行主程序: python 1.py")
    print("  3. 或启动Web界面: streamlit run ui_app.py")
    
    return True


def create_sample_queries():
    """创建示例查询文件"""
    queries = [
        "公司2023年的营业收入是多少？",
        "公司的主要产品有哪些？",
        "公司面临的主要风险是什么？",
        "公司的发展战略是什么？",
        "公司有多少员工？",
    ]
    
    queries_file = Path(__file__).parent / "sample_queries.txt"
    with open(queries_file, 'w', encoding='utf-8') as f:
        for query in queries:
            f.write(query + "\n")
    
    print(f"✓ 示例查询文件已创建: {queries_file}")


def main():
    """主函数"""
    try:
        if setup_environment():
            create_sample_queries()
            print("\n✨ 所有初始化步骤完成！")
        else:
            print("\n❌ 初始化过程中出现错误")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
