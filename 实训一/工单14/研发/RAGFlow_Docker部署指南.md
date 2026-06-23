# RAGFlow Docker 部署指南

> **版本**：RAGFlow v0.23.1  
> **适用环境**：Docker Compose（推荐）、Helm Chart（Kubernetes）  
> **文档生成时间**：2026年6月

---

## 目录

- [一、系统要求](#一系统要求)
- [二、快速部署（3 步启动）](#二快速部署3-步启动)
- [三、环境变量配置详解](#三环境变量配置详解)
- [四、服务架构与端口规划](#四服务架构与端口规划)
- [五、基础服务配置](#五基础服务配置)
  - [5.1 Elasticsearch（文档存储引擎）](#51-elasticsearch文档存储引擎)
  - [5.2 MySQL（元数据存储）](#52-mysql元数据存储)
  - [5.3 Redis（缓存与消息队列）](#53-redis缓存与消息队列)
  - [5.4 MinIO（对象存储）](#54-minio对象存储)
- [六、LLM 模型配置](#六llm-模型配置)
  - [6.1 支持的 LLM 厂商](#61-支持的-llm-厂商)
  - [6.2 Embedding 模型配置](#62-embedding-模型配置)
  - [6.3 Rerank 模型配置](#63-rerank-模型配置)
- [七、GPU 加速配置](#七gpu-加速配置)
- [八、文档存储引擎切换](#八文档存储引擎切换)
- [九、常见问题与排查](#九常见问题与排查)

---

## 一、系统要求

| 组件 | 最低要求 | 推荐配置 |
|------|---------|---------|
| **CPU** | ≥ 4 核 | ≥ 8 核 |
| **内存** | ≥ 16 GB | ≥ 32 GB |
| **磁盘** | ≥ 50 GB | ≥ 100 GB（SSD 推荐） |
| **Docker** | ≥ 24.0.0 | 最新稳定版 |
| **Docker Compose** | ≥ v2.26.1 | 最新稳定版 |
| **操作系统** | Linux / macOS / Windows(WSL2) | Linux |
| **GPU（可选）** | NVIDIA GPU + CUDA | 提升文档解析和向量化速度 |

**系统参数调整**（必须）：

```bash
# Elasticsearch 要求，否则 ES 无法启动
sudo sysctl -w vm.max_map_count=262144

# 永久生效
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

> **注意**：Docker 镜像为 x86 架构，ARM64 架构（如 Apple M 系列）需要从源码编译。

---

## 二、快速部署（3 步启动）

### 步骤 1：克隆仓库

```bash
git clone https://github.com/infiniflow/ragflow.git
cd ragflow/docker
```

### 步骤 2：配置环境变量

```bash
# 编辑 .env 文件（可选，使用默认配置即可启动）
nano .env
```

### 步骤 3：启动所有服务

```bash
# CPU 模式（默认）
docker compose -f docker-compose.yml up -d

# GPU 模式（需要 NVIDIA GPU + nvidia-container-toolkit）
# 先在 .env 中设置 DEVICE=gpu
docker compose --profile ragflow-gpu -f docker-compose.yml up -d
```

### 访问系统

- **Web UI**：`http://<服务器IP>`（端口 80）
- **API 接口**：`http://<服务器IP>:9380`
- **管理后台**：`http://<服务器IP>:9381`

### 查看启动日志

```bash
# RAGFlow 主服务日志
docker logs -f docker-ragflow-cpu-1

# 查看所有容器状态
docker compose ps
```

---

## 三、环境变量配置详解

`docker/.env` 文件控制所有部署参数：

### 核心配置

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| `RAGFLOW_IMAGE` | `infiniflow/ragflow:v0.23.1` | RAGFlow Docker 镜像版本 |
| `DEVICE` | `cpu` | 运行设备：`cpu` 或 `gpu` |
| `DOC_ENGINE` | `elasticsearch` | 文档存储引擎 |
| `MEM_LIMIT` | `8073741824`（8GB） | 单个容器内存上限 |
| `TZ` | `Asia/Shanghai` | 时区设置 |
| `COMPOSE_PROFILES` | （空） | Docker Compose 额外配置文件 |

### 端口配置

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| `SVR_WEB_HTTP_PORT` | `80` | Web UI HTTP 端口 |
| `SVR_WEB_HTTPS_PORT` | `443` | Web UI HTTPS 端口 |
| `SVR_HTTP_PORT` | `9380` | API 服务端口 |
| `ADMIN_SVR_HTTP_PORT` | `9381` | 管理 API 端口 |
| `SVR_MCP_PORT` | `9382` | MCP Server 端口 |
| `SVR_ES_PORT` | `1200` | Elasticsearch 映射端口 |
| `SVR_MYSQL_PORT` | `5455` | MySQL 映射端口 |
| `MINIO_PORT` | `9003` | MinIO API 端口 |
| `MINIO_CONSOLE_PORT` | `9004` | MinIO 控制台端口 |
| `SVR_REDIS_PORT` | `6379` | Redis 端口 |

### 密码配置

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| `MYSQL_PASSWORD` | `infini_rag_flow` | MySQL root 密码 |
| `ES_PASSWORD` | `infini_rag_flow` | Elasticsearch 密码 |
| `MINIO_USER` | `rag_flow` | MinIO 用户名 |
| `MINIO_PASSWORD` | `infini_rag_flow` | MinIO 密码 |
| `REDIS_PASSWORD` | `infini_rag_flow` | Redis 密码 |

> **安全提示**：生产环境务必修改所有默认密码。

### 功能开关

| 变量名 | 默认值 | 说明 |
|-------|--------|------|
| `REGISTER_ENABLED` | `1` | 是否允许注册新用户 |
| `USE_DOCLING` | `false` | 是否启用 IBM Docling 解析器 |
| `COMPOSE_PROFILES` | （空） | 可添加 `tei-cpu` 或 `tei-gpu` 启用本地 Embedding |

---

## 四、服务架构与端口规划

```
┌─────────────────────────────────────────────────────────────────┐
│                     RAGFlow Docker 服务架构                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌───────────┐                                                  │
│  │  Nginx    │ :80 (Web UI) / :443 (HTTPS)                     │
│  │  (前端)   │                                                  │
│  └─────┬─────┘                                                  │
│        │                                                        │
│        ├── /api/v1/* ──────▶ ┌─────────────┐  :9380            │
│        │                     │ RAGFlow API │                    │
│        │                     │  Server     │                    │
│        │                     └──────┬──────┘                    │
│        │                            │                            │
│        │                            ▼                            │
│        │                     ┌─────────────┐                    │
│        │                     │Task Executor│ × N               │
│        │                     │(任务执行器)  │                    │
│        │                     └──────┬──────┘                    │
│        │                            │                            │
│  /api/v1/admin ──▶ ┌──────────────┐ │                           │
│                    │ Admin Server │ │  :9381                    │
│                    └──────────────┘ │                           │
│                                     │                           │
│  ┌──────────────────────────────────┼────────────────────┐     │
│  │              依赖服务层                                │     │
│  │                                                        │     │
│  │  ┌──────────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ │     │
│  │  │ES 8.11.3 │ │MySQL │ │Redis │ │MinIO │ │  TEI   │ │     │
│  │  │:1200→9200│ │:5455 │ │:6379 │ │:9003 │ │:6380   │ │     │
│  │  └──────────┘ └──────┘ └──────┘ └──────┘ └────────┘ │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

| 服务 | 容器内端口 | 映射端口 | 说明 |
|------|----------|---------|------|
| Nginx | 80/443 | 80/443 | 前端静态文件 + 反向代理 |
| RAGFlow API | 9380 | 9380 | 后端 API 服务 |
| Admin Server | 9381 | 9381 | 管理 API |
| MCP Server | 9382 | 9382 | MCP 协议服务 |
| Elasticsearch | 9200 | 1200 | 文档搜索与向量存储 |
| MySQL | 3306 | 5455 | 元数据存储 |
| Redis | 6379 | 6379 | 缓存 + 任务队列 |
| MinIO | 9000/9001 | 9003/9004 | 文件对象存储 |
| TEI | 80 | 6380 | 文本 Embedding 推理 |

---

## 五、基础服务配置

### 5.1 Elasticsearch（文档存储引擎）

```yaml
# docker-compose-base.yml 中的配置
es01:
  image: elasticsearch:8.11.3
  ports:
    - 1200:9200        # 映射到宿主机 1200 端口
  environment:
    - discovery.type=single-node       # 单节点模式
    - xpack.security.enabled=true      # 启用安全认证
    - ES_JAVA_OPTS=-Xms4g -Xmx4g      # JVM 堆内存（建议 4GB+）
  mem_limit: 8073741824                # 容器内存上限 8GB
  volumes:
    - esdata01:/usr/share/elasticsearch/data
```

**关键调优**：
- 内存建议分配 **4-8 GB** 给 ES JVM
- 确保 `vm.max_map_count >= 262144`
- 数据持久化到 `esdata01` 卷

### 5.2 MySQL（元数据存储）

```yaml
mysql:
  image: mysql:8.0.39
  ports:
    - 5455:3306
  environment:
    - MYSQL_ROOT_PASSWORD=${MYSQL_PASSWORD:-infini_rag_flow}
  volumes:
    - mysql_data:/var/lib/mysql
    - ./init.sql:/docker-entrypoint-initdb.d/init.sql
```

**初始化 SQL**（`docker/init.sql`）：

```sql
CREATE DATABASE IF NOT EXISTS rag_flow;
```

### 5.3 Redis（缓存与消息队列）

```yaml
redis:
  image: valkey/valkey:8
  ports:
    - 6379:6379
  command: >
    --requirepass ${REDIS_PASSWORD:-infini_rag_flow}
  volumes:
    - redis_data:/data
```

**Redis 的核心职责**：
- **任务队列**：使用 Redis Stream（XADD/XREADGROUP）管理文档解析任务
- **缓存**：LLM 响应缓存（`get_llm_cache`/`set_llm_cache`）
- **进度追踪**：任务状态存储与查询

### 5.4 MinIO（对象存储）

```yaml
minio:
  image: minio/minio:latest
  ports:
    - 9003:9000     # API 端口
    - 9004:9001     # 控制台端口
  environment:
    - MINIO_ROOT_USER=${MINIO_USER:-rag_flow}
    - MINIO_ROOT_PASSWORD=${MINIO_PASSWORD:-infini_rag_flow}
  volumes:
    - minio_data:/data
  command: server /data --console-address ":9001"
```

**MinIO 管理**：
- 控制台地址：`http://<服务器IP>:9004`
- 用户名/密码：见 `.env` 中的 `MINIO_USER` / `MINIO_PASSWORD`
- 存储内容：上传的文档文件、解析生成的图片

---

## 六、LLM 模型配置

### 6.1 支持的 LLM 厂商

RAGFlow 支持 **30+ 家 LLM 厂商**，通过 `service_conf.yaml.template` 配置：

```yaml
# docker/service_conf.yaml.template
user_default_llm:
  factory: 'OpenAI'              # LLM 厂商
  api_key: 'your-api-key'        # API 密钥
  base_url: 'https://api.openai.com/v1'  # API 地址
```

**主流厂商配置示例**：

| 厂商 | factory 值 | base_url |
|------|-----------|----------|
| OpenAI | `OpenAI` | `https://api.openai.com/v1` |
| 通义千问 | `Tongyi-Qianwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DeepSeek | `DeepSeek` | `https://api.deepseek.com/v1` |
| 智谱 AI | `ZHIPU-AI` | `https://open.bigmodel.cn/api/paas/v4` |
| 月之暗面 | `Moonshot` | `https://api.moonshot.cn/v1` |
| Anthropic | `Anthropic` | `https://api.anthropic.com/` |
| SiliconFlow | `SILICONFLOW` | `https://api.siliconflow.cn/v1` |
| Ollama（本地） | `Ollama` | `http://host.docker.internal:11434/v1` |
| Xinference（本地） | `Xinference` | `http://host.docker.internal:9997/v1` |
| vLLM（本地） | `OpenAI`（兼容） | `http://host.docker.internal:8000/v1` |

**默认模型配置**：

```yaml
user_default_llm:
  default_models:
    chat_model:
      name: 'gpt-4o'              # 对话模型
      factory: 'OpenAI'
      api_key: 'your-key'
      base_url: 'https://api.openai.com/v1'
    embedding_model:               # 向量化模型
      api_key: 'your-key'
      base_url: 'http://tei:80'    # 使用本地 TEI 服务
    rerank_model: 'bge-reranker-v2'  # 重排序模型
    image2text_model: ''            # 图像描述模型（可选）
    asr_model:                      # 语音识别模型（可选）
      model: 'whisper-large-v3'
```

### 6.2 Embedding 模型配置

#### 方式一：使用内置 TEI 服务（推荐）

在 `docker/.env` 中启用 TEI 服务：

```bash
# 选择其一：
COMPOSE_PROFILES=${COMPOSE_PROFILES},tei-cpu    # CPU 模式
COMPOSE_PROFILES=${COMPOSE_PROFILES},tei-gpu    # GPU 模式
```

可用的 Embedding 模型（`.env` 中 `TEI_EMBEDDING_MODEL_NAME`）：

| 模型 | 所需内存/显存 | 特点 |
|------|-------------|------|
| `Qwen/Qwen3-Embedding-0.6B`（默认） | ~25 GB | 中英文均衡，推荐 |
| `BAAI/bge-m3` | ~21 GB | 多语言，检索效果好 |
| `BAAI/bge-small-en-v1.5` | ~1.2 GB | 轻量英文，资源紧张时使用 |

#### 方式二：使用第三方 API

```yaml
embedding_model:
  api_key: 'your-key'
  base_url: 'https://api.siliconflow.cn/v1'  # SiliconFlow
  name: 'BAAI/bge-m3'
```

#### 方式三：本地部署（Ollama / Xinference）

```yaml
embedding_model:
  api_key: 'ollama'
  base_url: 'http://host.docker.internal:11434/v1'
  name: 'nomic-embed-text'
```

### 6.3 Rerank 模型配置

Rerank（重排序）模型用于提升检索结果的相关性排序：

```yaml
default_models:
  rerank_model: 'bge-reranker-v2-m3'  # BAAI 的 Rerank 模型
```

可通过 TEI 服务或第三方 API 提供 Rerank 能力。

---

## 七、GPU 加速配置

### 前提条件

1. 安装 NVIDIA GPU 驱动
2. 安装 `nvidia-container-toolkit`

```bash
# 安装 nvidia-container-toolkit
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 启用 GPU

```bash
# 1. 修改 docker/.env
DEVICE=gpu

# 2. 使用 GPU profile 启动
docker compose --profile ragflow-gpu -f docker-compose.yml up -d

# 3. 同时启用 GPU 加速的 TEI Embedding（可选）
# 在 .env 中添加：
# COMPOSE_PROFILES=ragflow-gpu,tei-gpu
```

**GPU 加速范围**：
- **RAGFlow 容器**：DeepDoc 文档解析（OCR、布局分析、表格识别）加速
- **TEI 容器**：Embedding 向量生成加速

---

## 八、文档存储引擎切换

RAGFlow 支持多种文档存储引擎，通过 `docker/.env` 的 `DOC_ENGINE` 变量切换：

| 引擎 | DOC_ENGINE 值 | 说明 |
|------|--------------|------|
| **Elasticsearch** | `elasticsearch`（默认） | 全文搜索 + 向量搜索 |
| **Infinity** | `infinity` | InfiniFlow 自研引擎 |
| **OpenSearch** | `opensearch` | AWS 开源搜索 |
| **OceanBase** | `oceanbase` | 蚂蚁分布式数据库 |
| **SeekDB** | `seekdb` | OceanBase 轻量版 |

### 切换到 Infinity

```bash
# 1. 修改 .env
DOC_ENGINE=infinity

# 2. 停止并清理现有数据
docker compose down -v

# 3. 重新启动
docker compose -f docker-compose.yml up -d
```

> **注意**：切换引擎会**清除所有现有数据**，需要重新上传和解析文档。

---

## 九、常见问题与排查

### Q1：Elasticsearch 启动失败

```bash
# 检查日志
docker logs docker-es01-1

# 常见原因：vm.max_map_count 太小
sudo sysctl -w vm.max_map_count=262144
```

### Q2：容器内存不足

```bash
# 在 .env 中调整单容器内存限制（默认 8GB）
MEM_LIMIT=12884901888   # 12GB

# 或增加系统总内存
```

### Q3：MinIO 无法连接

```bash
# 确认 MinIO 端口未被占用
netstat -tlnp | grep 9003

# 检查 MinIO 日志
docker logs docker-minio-1
```

### Q4：Redis 连接被拒绝

```bash
# 确认 Redis 密码正确（service_conf.yaml 中的密码与 .env 一致）
docker logs docker-redis-1

# 测试连接
docker exec -it docker-redis-1 redis-cli -a infini_rag_flow ping
```

### Q5：前端无法访问

```bash
# 检查 Nginx 容器状态
docker ps | grep nginx

# 检查端口映射
docker port docker-ragflow-cpu-1

# 检查防火墙
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### Q6：文档解析超时

```bash
# 增加任务超时时间（在 service_conf.yaml 中）
# 或减小 task_page_size 以缩短单任务处理时间

# 检查 Task Executor 日志
docker logs -f docker-ragflow-cpu-1 | grep "task_executor"
```

### Q7：如何完全重置

```bash
# 停止所有容器并删除数据卷
docker compose down -v

# 删除所有镜像（可选）
docker compose down --rmi all

# 重新启动
docker compose -f docker-compose.yml up -d
```

---

## 附录：Docker Compose 文件结构

```
ragflow/docker/
├── docker-compose.yml           # 主编排文件（含 CPU/GPU profile）
├── docker-compose-base.yml      # 基础服务定义（ES/MySQL/Redis/MinIO）
├── .env                         # 环境变量配置
├── service_conf.yaml.template   # 后端服务配置模板
├── entrypoint.sh                # 容器启动脚本
├── init.sql                     # MySQL 初始化 SQL
├── nginx/
│   ├── nginx.conf               # Nginx 主配置
│   ├── ragflow.conf             # 前端路由配置
│   ├── proxy.conf               # 反向代理配置
│   └── ragflow.https.conf       # HTTPS 配置
└── launch_backend_service.sh    # 开发模式启动脚本
```

---

> **参考资源**：
> - RAGFlow GitHub：https://github.com/infiniflow/ragflow
> - RAGFlow 文档：https://ragflow.io/docs
> - Elasticsearch 文档：https://www.elastic.co/guide/en/elasticsearch/reference/current/
