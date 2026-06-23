# DocumentQualityAssessmentSkill — 输出格式参考

## JSON 报告 Schema

```json
{
  "meta": {
    "input_dir": "string",
    "scanned_at": "ISO8601",
    "total_files": 0,
    "total_size_bytes": 0,
    "duration_seconds": 0.0,
    "errors": [
      { "file": "path", "error": "message" }
    ]
  },
  "format_distribution": {
    "by_extension": {
      ".pdf": { "count": 0, "percentage": 0.0, "total_size_bytes": 0 }
    },
    "summary": {
      "unique_extensions": 0,
      "most_common": ".pdf"
    }
  },
  "pdf_page_types": {
    "files": [
      {
        "path": "relative/path.pdf",
        "total_pages": 0,
        "page_breakdown": {
          "text": 0,
          "scanned": 0,
          "mixed": 0,
          "empty": 0
        },
        "document_type": "text|scanned|mixed|empty",
        "text_page_ratio": 0.0
      }
    ],
    "summary": {
      "total_pdfs": 0,
      "by_document_type": {
        "text": 0,
        "scanned": 0,
        "mixed": 0,
        "empty": 0
      }
    }
  },
  "length_distribution": {
    "statistics": {
      "count": 0,
      "min": 0,
      "max": 0,
      "mean": 0.0,
      "p25": 0,
      "p50": 0,
      "p75": 0,
      "p90": 0,
      "p95": 0
    },
    "buckets": {
      "0-500": 0,
      "500-2000": 0,
      "2000-10000": 0,
      "10000+": 0
    },
    "files": [
      { "path": "relative/path.txt", "char_count": 0 }
    ]
  },
  "duplicates": {
    "exact": {
      "groups": [
        {
          "md5": "hex",
          "files": ["path1", "path2"],
          "size_bytes": 0
        }
      ],
      "total_groups": 0,
      "total_duplicate_files": 0
    },
    "approximate": {
      "pairs": [
        {
          "file_a": "path1",
          "file_b": "path2",
          "hamming_distance": 0,
          "similarity": 0.0
        }
      ],
      "threshold": 3,
      "total_pairs": 0
    }
  },
  "sensitive_info": {
    "findings": [
      {
        "file": "relative/path.txt",
        "type": "phone|email|id_card",
        "value_masked": "138****5678",
        "position": 0,
        "context": "...前后各50字符的上下文..."
      }
    ],
    "summary": {
      "total_findings": 0,
      "by_type": {
        "phone": 0,
        "email": 0,
        "id_card": 0
      },
      "files_affected": 0
    }
  }
}
```

## HTML 简报结构

HTML 简报包含以下区块：

1. **标题与元信息** — 扫描时间、文件总数、耗时
2. **格式分布** — 表格展示扩展名、数量、占比
3. **PDF 页面类型** — 文档类型汇总 + 各 PDF 明细表
4. **长度分布** — 分位数卡片 + 区间柱状图（CSS）
5. **重复检测** — 精确/近似重复数量与示例
6. **敏感信息** — 按类型统计 + 脱敏命中列表

样式：内联 CSS，无需外部依赖，可直接在浏览器打开。

## 字段说明

### `document_type` 判定

取页面类型的众数（mode）。若最高票数并列，返回 `mixed`。

### `similarity` 计算

`similarity = 1 - (hamming_distance / 64)`，范围 [0, 1]。

### 脱敏规则

| 类型 | 规则 | 示例 |
|------|------|------|
| phone | 保留前3后4 | `138****5678` |
| email | 保留@前2字符和域名 | `ab***@example.com` |
| id_card | 保留前3后4 | `110***********1234` |
