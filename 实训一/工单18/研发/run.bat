@echo off
REM ============================================================
REM 文档质量评估工具 — 一键运行脚本 (Windows)
REM ============================================================

set SCRIPT_DIR=%~dp0
set SKILL_DIR=%SCRIPT_DIR%.cursor\skills\document-quality-assessment

echo ========================================
echo  DocumentQualityAssessmentSkill
echo  文档质量评估工具
echo ========================================
echo.

REM 检查参数
if "%~1"=="" (
    echo 用法: run.bat ^<文档目录^> [输出目录]
    echo 示例: run.bat D:\my_documents D:\output
    exit /b 1
)

set INPUT_DIR=%~1
set OUTPUT_DIR=%~2
if "%OUTPUT_DIR%"=="" set OUTPUT_DIR=%SCRIPT_DIR%quality_report

REM 安装依赖
echo [1/3] 检查依赖...
pip install -r "%SKILL_DIR%\requirements.txt" -q 2>nul

REM 运行评估
echo [2/3] 执行质量评估...
python "%SKILL_DIR%\scripts\assess_documents.py" --input "%INPUT_DIR%" --output-dir "%OUTPUT_DIR%"

REM 完成
echo.
echo [3/3] 完成！
echo JSON报告: %OUTPUT_DIR%\quality_report.json
echo HTML简报: %OUTPUT_DIR%\quality_brief.html
echo.
echo 在浏览器中打开 HTML 简报查看可视化结果。
