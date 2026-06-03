# 数据集说明

## 概述

本数据集是通过使用 **mimo-v2-flash** 模型进行提示词蒸馏生成的中文对话数据集。数据集包含了多个场景的对话记录，涵盖了编程、学习、生活、技术、旅游等多个领域。

## 数据集生成过程

1. **提示词蒸馏**: 使用 mimo-v2-flash 模型对原始数据进行提示词蒸馏
2. **数据收集**: 收集蒸馏后的对话数据
3. **数据清洗**: 删除训练干扰字段（description、user_prompt、user_followups）
4. **数据整理**: 按场景分类整理数据

## 数据集结构

每个 JSON 文件包含以下结构：

```json
{
  "scenario": {
    "name": "场景名称",
    "ai_role": "AI角色提示词"
  },
  "conversation": [
    {
      "role": "user",
      "content": "AI扮演的用户消息"
    },
    {
      "role": "assistant",
      "content": "AI回复"
    }
  ]
}
```

### 字段说明

- **scenario.name**: 场景名称，标识对话的主题或类别
- **scenario.ai_role**: AI 的角色设定和职责描述
- **conversation**: 对话记录数组
  - **role**: 对话角色，值为 "user" 或 "assistant"
  - **content**: 对话内容

## 数据集统计

- **总文件数**: 234 个 JSON 文件
- **场景类别**: 55 个不同的场景
- **数据格式**: JSON

### 主要场景类别

- 编程相关: Python编程基础、代码优化建议、常见错误排查、机器学习入门、技术概念解释、项目开发指导等
- 学习相关: 学习方法指导、数学建模、数学竞赛、线性代数、概率统计、微积分入门等
- 生活相关: 日常问题解决、时间管理技巧、理财规划建议、健康饮食指导、节能环保生活等
- 旅游相关: 上海、北京、天津、重庆、江苏、浙江、安徽、福建、江西、河南、吉林、辽宁、黑龙江等
- 其他: 猫娘系列等角色扮演对话

## 数据处理

### 已删除字段

为了优化训练效果，以下字段已被删除：

none

### 数据目录

- **原始数据**: `distill/` - 未处理的原始数据
- **处理后数据**: `data/` - 清理后的训练数据
- **按前缀合并**: `merged_by_prefix/` - 按场景前缀合并的数据

## 使用方法

### 单个文件读取

```python
import json

with open('data/Python编程基础_20260111_210219.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    
print(f"场景: {data['scenario']['name']}")
print(f"AI角色: {data['scenario']['ai_role']}")
print(f"对话轮数: {len(data['conversation'])}")
```

### 批量处理

```python
import json
from pathlib import Path

data_dir = Path('data')

for json_file in data_dir.glob('*.json'):
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 处理数据...
    print(f"处理文件: {json_file.name}")
```

### 用于模型训练

本数据集适合用于：

- 指令微调 (Instruction Tuning)
- 对话模型训练
- 多轮对话生成
- 角色扮演训练

## 数据集特点

1. **多样性**: 涵盖多个领域的对话场景
2. **高质量**: 通过 mimo-v2-flash 模型蒸馏生成，保证对话质量
3. **结构化**: 统一的 JSON 格式，便于处理和使用
4. **已清洗**: 删除了干扰训练的字段，适合直接用于训练

## 注意事项

1. 数据集包含中文对话，适合中文模型训练
2. 每个文件代表一个完整的对话场景
3. 对话长度不一，可根据需要进行筛选
4. 建议在使用前根据具体任务进行数据预处理

## 许可证

本数据集采用 Apache License 2.0 许可证。详情请参见 [LICENSE](LICENSE) 文件。

## 联系方式

如有问题或建议，请联系数据集维护者。