# Vector 日志采集 → RustFS → DuckDB 查询

> 背景：Vector 写本地 S3 兼容存储 RustFS（JSON + Parquet 双输出）+ DuckDB 查询的完整示例。
> 场景与结论：compose 含 bucket-init 自动建桶；path 寻址与固定凭证为重点。

使用 [Vector](https://vector.dev) 采集本地磁盘日志，写入 [RustFS](https://docs.rustfs.com/)（自建 S3 兼容存储），通过 [DuckDB](https://duckdb.org) 直接查询 S3 数据。

## 架构概览

```text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  python-log-gen │────▶│     Vector      │────▶│     RustFS      │◀────│     DuckDB      │
│  (日志生成器)    │     │  (日志采集)      │     │  (S3 存储)       │     │  (数据分析)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │                       │                       │
        └────── app-logs ───────┘                       │                       │
              (共享卷)                            rustfs-data (持久化卷)        │
                                    ┌─────────────────┴─────────────────┐
                                    ▼                                   ▼
                            log-data (JSON)                    log-data (Parquet)
```

## 目录结构

```text
vector2rustfs/
├── compose.yaml           # 容器编排（rustfs + vector + duckdb + python-log-gen）
├── vector.yaml            # Vector 配置（JSON + Parquet 双输出）
├── vector-test.yaml       # Vector 测试配置（demo_logs 数据源）
├── gen-log.py             # Python 日志生成器（JSON 行，RFC3339 timestamp）
├── secrets/
│   └── rustfs-secrets.json  # RustFS 凭证
├── duckdb/
│   └── queries.sql        # DuckDB 查询示例
├── .gitignore
└── README.md
```

## 快速开始

```bash
# 1. 启动所有服务（RustFS + 建桶 + 日志生成 + Vector）
podman compose up -d

# 2. 查看 Vector 日志
podman compose logs -f vector

# 3. 验证 RustFS 中的数据
#    RustFS Console: http://localhost:9001（rustfsadmin/rustfsadmin）
#    或使用 aws-cli：
aws --endpoint-url http://localhost:9000 s3 ls s3://log-data/ --recursive
```

## 服务说明

| 服务 | 端口 | 说明 |
|------|------|------|
| rustfs | 9000 (S3 API) / 9001 (Console) | RustFS 对象存储 |
| bucket-init | - | 一次性初始化，创建所需 bucket |
| python-log-gen | - | 日志生成器，~5 行/秒 |
| vector | - | Vector 日志采集 agent |
| duckdb | - | DuckDB 查询（`--profile query`） |

## RustFS 配置

### 默认凭证

| 项目 | 值 |
|------|-----|
| Access Key | `rustfsadmin` |
| Secret Key | `rustfsadmin` |
| S3 Endpoint | `http://localhost:9000` |
| Console | `http://localhost:9001` |
| Region | `us-east-1` |

### Bucket 列表

| Bucket | 用途 |
|--------|------|
| `log-data` | 存储 JSON 和 Parquet 日志 |
| `log-test` | 测试用 bucket |

### 自定义凭证

修改 `compose.yaml` 中的环境变量：

```yaml
rustfs:
  environment:
    RUSTFS_ROOT_USER: your-admin
    RUSTFS_ROOT_PASSWORD: your-password
```

同步更新 `secrets/rustfs-secrets.json`：

```json
{
  "access_key_id": "your-admin",
  "secret_access_key": "your-password"
}
```

## Vector 配置说明

### 双输出配置

Vector 同时输出 JSON 和 Parquet 两种格式到同一个 bucket：

| Sink | Bucket | 格式 | 压缩 | 路径前缀 |
|------|--------|------|------|----------|
| `rustfs_s3_json` | `log-data` | gzip JSON lines | gzip | `log_json/year=.../month=.../day=.../hour=.../minute=.../` |
| `rustfs_s3_parquet` | `log-data` | Parquet | snappy | `log_parquet/year=.../month=.../day=.../hour=.../` |

### 与 OSS 配置的主要差异

| 配置项 | 阿里云 OSS | RustFS |
|--------|-----------|--------|
| `endpoint` | `https://oss-cn-shenzhen.aliyuncs.com` | `http://rustfs:9000` |
| `region` | `cn-shenzhen` | `us-east-1`（默认） |
| `force_path_style` | `false`（OSS 仅支持 vhost） | `true`（RustFS 支持 path-style） |
| `bucket` | 已有 bucket | 需先创建（bucket-init 自动完成） |

### key_prefix 分区

生产配置使用 Hive 风格分区（year/month/day/hour）：

```yaml
# JSON 输出
key_prefix: "log_json/year={{ partition_year }}/month={{ partition_month }}/day={{ partition_day }}/hour={{ partition_hour }}/minute={{ partition_minute }}/"

# Parquet 输出
key_prefix: "log_parquet/year={{ partition_year }}/month={{ partition_month }}/day={{ partition_day }}/hour={{ partition_hour }}/"
```

落地路径示例：

```text
log-data/
├── log_json/
│   └── year=2026/
│       └── month=08/
│           └── day=21/
│               └── hour=10/
│                   ├── minute=00/
│                   │   └── 1724145000+uuid.json.gz
│                   └── minute=01/
└── log_parquet/
    └── year=2026/
        └── month=08/
            └── day=21/
                └── hour=10/
                    └── 1724145000+uuid.parquet
```

### Parquet 配置

```yaml
batch_encoding:
  codec: parquet
  schema_mode: auto_infer        # 开发环境：自动推断 schema
  compression:
    algorithm: snappy            # 推荐 snappy 或 zstd
```

## 使用 DuckDB 查询 RustFS 数据

### 方式一：本地 DuckDB

```bash
# 首次配置：安装 httpfs 扩展并创建持久化 secret
duckdb -c "INSTALL httpfs; CREATE PERSISTENT SECRET rustfs (TYPE s3, PROVIDER config, KEY_ID 'rustfsadmin', SECRET 'rustfsadmin', ENDPOINT 'localhost:9000', REGION 'us-east-1', URL_STYLE 'path', USE_SSL false);"

# 查询
duckdb -f duckdb/queries.sql
```

### 方式二：DuckDB 容器（推荐）

```bash
# 使用预装扩展的容器查询（首次下载 httpfs 约 52 秒，缓存后 <1 秒）
echo "" | podman compose --profile query run --rm duckdb
```

容器特性：
- 扩展缓存到 `duckdb-ext` 卷，重启不丢失
- 桥接网络，通过服务名 `rustfs` 访问
- 自动创建 S3 Secret

### 代理配置说明

DuckDB v1.5.3+ 自动读取 `HTTP_PROXY` 环境变量，无需手动 `SET`。

compose.yaml 中通过环境变量配置：

```yaml
duckdb:
  environment:
    no_proxy: "rustfs,localhost,127.0.0.1"  # 绕过本地 S3 访问
    NO_PROXY: "rustfs,localhost,127.0.0.1"
```

### 查看已存储的 Secret

```sql
SELECT name, type FROM duckdb_secrets();
-- rustfs | s3
```

### 常用 SQL

```sql
-- 列出所有日志文件
SELECT * FROM glob('s3://log-data/**');

-- 查询 JSON 日志
SELECT * FROM read_json('s3://log-data/log_json/**/*.json.gz');

-- 查询 Parquet 日志（自动合并不同 schema 的文件）
SELECT * FROM read_parquet('s3://log-data/log_parquet/**/*.parquet');

-- 统计 JSON 日志数量
SELECT count(*) FROM read_json('s3://log-data/log_json/**/*.json.gz');

-- 按小时统计文件数
SELECT
    regexp_extract(file, 'year=([^/]+)', 1) as log_year,
    regexp_extract(file, 'month=([^/]+)', 1) as log_month,
    regexp_extract(file, 'day=([^/]+)', 1) as log_day,
    regexp_extract(file, 'hour=([^/]+)', 1) as hour,
    count(*) as files
FROM glob('s3://log-data/log_json/**/*')
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

-- 查询 Parquet 分区数据（利用分区裁剪）
SELECT * FROM read_parquet('s3://log-data/log_parquet/year=2026/month=08/**/*.parquet');
```

### DuckDB 与 S3 的关键点

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `URL_STYLE` | `path` | RustFS 使用 path-style 寻址 |
| `USE_SSL` | `false` | 本地不使用 SSL |
| `REGION` | `us-east-1` | RustFS 默认区域 |
| `PERSISTENT SECRET` | `rustfs` | 保存到 `~/.duckdb/stored_secrets/` |

### Secret 存储位置

```text
~/.duckdb/stored_secrets/
├── rustfs secret         # RustFS S3 连接凭证
└── ...                   # 其他已存储的 secret
```

## 常见运维命令

```bash
# 启动
podman compose up -d

# 查看日志
podman compose logs -f vector
podman compose logs -f rustfs

# 重启 Vector（断点保留）
podman compose restart vector

# 热重载配置（不重启容器）
podman kill -s HUP vector

# 停止（不删卷）
podman compose down

# 停止并删除卷（清除断点和数据）
podman compose down -v

# 查看卷
podman volume ls

# 查看 RustFS bucket
aws --endpoint-url http://localhost:9000 s3 ls
```

## 故障排查

### Vector 连接 RustFS 失败

```bash
# 检查 RustFS 是否健康
curl http://localhost:9000/health

# 检查 bucket 是否存在
aws --endpoint-url http://localhost:9000 s3 ls
```

### 权限错误

确认 `secrets/rustfs-secrets.json` 中的凭证与 `compose.yaml` 中 `RUSTFS_ROOT_USER` / `RUSTFS_ROOT_PASSWORD` 一致。

### 断点重置

```bash
podman compose down -v
podman volume rm vector-file-to-rustfs_vector-data
podman compose up -d
```

## 与 vector2oss 的对比

| 特性 | vector2oss | vector2rustfs |
|------|-----------|---------------|
| 存储服务 | 阿里云 OSS | 自建 RustFS |
| 部署方式 | 仅 Vector + 日志生成 | 含 RustFS 服务 |
| 建桶 | 手动/已有 | 自动（bucket-init） |
| 网络 | 公网/内网 | 容器内网 |
| 成本 | 按量计费 | 自建免费 |
| 输出格式 | 单格式 | JSON + Parquet 双输出 |
| 分区格式 | date/HH/MM | year/month/day/hour/minute |
| 适用场景 | 生产环境 | 开发/测试/私有化部署 |
