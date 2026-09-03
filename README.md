# Step Vector - 日志采集示例集

使用 [Vector](https://vector.dev) 采集本地磁盘日志，写入各种存储后端的容器化示例集。每个子目录是一个独立的端到端 pipeline，涵盖 source、transform、sink 全链路。

## 目录结构

```
step-vector/
├── README.md                          # 本文件
├── .gitignore
├── docs/                              # 公共文档
│   ├── VECTOR_PARQUET_BEST_PRACTICES.md  # Parquet 最佳实践
│   ├── duckdb-s3.md                   # DuckDB 查询 S3/OSS 指南
│   └── HIVE_PARTITIONING.md           # Hive 分区测试报告
│
├── vector2oss/                        # 阿里云 OSS 示例
│   ├── vector.yaml                    # 生产配置 (JSON + Parquet 双输出)
│   ├── vector-test.yaml               # 测试配置 (demo_logs)
│   ├── compose.yaml                   # 容器编排
│   ├── gen-log.py                     # 日志生成器
│   ├── secrets/                       # 密钥托管
│   ├── duckdb/                        # DuckDB 查询示例
│   └── README.md
│
├── vector2rustfs/                     # RustFS (S3 兼容) 示例
│   ├── vector.yaml                    # 生产配置 (JSON + Parquet 双输出)
│   ├── vector-test.yaml               # 测试配置 (demo_logs)
│   ├── compose.yaml                   # 容器编排 (含 RustFS + bucket-init)
│   ├── gen-log.py                     # 日志生成器
│   ├── secrets/                       # 密钥托管
│   ├── duckdb/                        # DuckDB 查询示例
│   └── README.md
│
├── vector2openobserve/                # TODO: OpenObserve 示例
├── vector2doris/                      # TODO: Apache Doris 示例
├── vector2clickhouse/                 # TODO: ClickHouse 示例
├── vector-collect/                    # Better Stack 全套采集演示（source 侧）
│   ├── dbs/                           #   mysql/postgresql/redis/mongodb/elasticsearch (×2 含指标)
│   ├── queues/                        #   rabbitmq (×2 含指标)
│   ├── webservers/                    #   nginx / apache
│   ├── proxies/                       #   haproxy / traefik (×2 含指标)
│   └── system/                        #   auth_log/docker/kubernetes/ubuntu×2/ufw
└── tmp/                               # 临时实验 (metrics、logging 等)
```

## 已完成的 Sink 示例

| Sink | 目录 | 格式 | 说明 |
|------|------|------|------|
| 阿里云 OSS | `vector2oss/` | JSON + Parquet | S3 兼容 API，Hive 分区 |
| RustFS | `vector2rustfs/` | JSON + Parquet | 本地 S3 兼容存储，Hive 分区 |
| 本地文件 | `vector-collect/**` | JSON lines | 22 个 Better Stack 全套采集演示，见下 |

## 采集示例（vector-collect，source 侧）

对应 Better Stack [Vector 文档 Available configs](https://betterstack.com/docs/logs/vector/#available-configs) 全部配置，每目录为独立端到端演示：容器化真实服务产生日志 → Vector 采集解析 → 本地文件落地（离线可跑）。详见 [`vector-collect/README.md`](vector-collect/README.md)。

| 分类 | 示例 | Vector source |
|------|------|---------------|
| DBs | mysql / mysql_with_metrics | `file` (+`mysql_metrics`) |
| DBs | postgresql / postgresql_with_metrics | `file` (+`postgresql_metrics`) |
| DBs | mongodb | `file` + `parse_json` |
| DBs | redis / redis_with_metrics | `file` (+`prometheus_scrape`) |
| DBs | elasticsearch / elasticsearch_with_metrics | `file` (+`prometheus_scrape`) |
| Queues | rabbitmq / rabbitmq_with_metrics | `file` (+`prometheus_scrape`) |
| Webservers | nginx / apache | `file` + `parse_nginx_log!` / `parse_apache_log!` |
| Proxies | haproxy | `syslog` (UDP) |
| Proxies | traefik / traefik_with_metrics | `file` + `parse_json` (+`prometheus_scrape`) |
| System | auth_log / ufw / ubuntu / ubuntu_with_docker | `file` (+`docker_logs`) |
| System | docker | `docker_logs` |
| System | kubernetes | `kubernetes_logs` (+`k8s/` DaemonSet 清单) |

## 公共模式

所有示例共享以下设计模式：

### 数据源 (Source)

| Source | 用途 | 配置文件 |
|--------|------|----------|
| `file` | 读取本地日志文件 | `vector*.yaml` (生产) |
| `demo_logs` | 内置测试数据生成 | `vector*-test.yaml` |

### 转换 (Transform)

| Transform | 用途 | 说明 |
|-----------|------|------|
| `parse_ts` | JSON 解析 + 事件时间提取 | 解析 ndjson 行，提取 RFC3339 时间戳 |
| `partition` | Hive 分区字段生成 | 按北京时间生成 year/month/day/hour/minute |

### 输出格式

| 格式 | Sink 类型 | 编码 | 压缩 | 说明 |
|------|-----------|------|------|------|
| JSON | `aws_s3` | `raw_message` | gzip | 原始日志行，下游直接消费 |
| Parquet | `aws_s3` | `batch_encoding: parquet` | snappy | 列式格式，Athena/EMR 友好 |

### 分区格式 (Hive 风格)

```
JSON:    year=YYYY/month=MM/day=DD/hour=HH/minute=MM/
Parquet: year=YYYY/month=MM/day=DD/hour=HH/
```

## 快速开始

### 1. 阿里云 OSS 示例

```bash
cd vector2oss

# 配置密钥
cp secrets/oss-secrets-template.json secrets/oss-secrets.json
# 编辑 secrets/oss-secrets.json 填入你的 RAM AccessKey

# 启动
podman compose up -d

# 验证
podman compose logs -f vector

# 查询 (需要本地安装 DuckDB)
duckdb -c "CREATE OR REPLACE SECRET oss (TYPE s3, PROVIDER config, KEY_ID 'YOUR_KEY', SECRET 'YOUR_SECRET', ENDPOINT 'oss-cn-shenzhen.aliyuncs.com', REGION 'cn-shenzhen', URL_STYLE 'vhost', USE_SSL true);"
duckdb -f duckdb/queries.sql
```

### 2. RustFS 示例

```bash
cd vector2rustfs

# 启动 (bucket 由 bucket-init 自动创建)
podman compose up -d

# 验证
podman compose logs -f vector

# 查询
duckdb -c "CREATE OR REPLACE SECRET rustfs (TYPE s3, PROVIDER config, KEY_ID 'rustfsadmin', SECRET 'rustfsadmin', ENDPOINT 'rustfs:9000', REGION 'us-east-1', URL_STYLE 'path', USE_SSL false);"
duckdb -f duckdb/queries.sql
```

## 容器环境

- **运行时**: Podman 6.0.2 + podman-compose 1.6.0
- **Shell**: Windows PowerShell 5.1
- **已知问题**: `echo ""` workaround 用于 `--no-TTY`

## 文档

| 文档 | 说明 |
|------|------|
| [Parquet 最佳实践](docs/VECTOR_PARQUET_BEST_PRACTICES.md) | schema 模式、压缩、批次配置 |
| [DuckDB S3 查询](docs/duckdb-s3.md) | DuckDB 连接 S3/OSS/RustFS |
| [Hive 分区测试](docs/HIVE_PARTITIONING.md) | 分区裁剪测试报告 |

## TODO

### 待添加的 Sink 示例

- [ ] **vector2openobserve/** - 写入 [OpenObserve](https://openobserve.ai/)
  - [ ] HTTP JSON sink
  - [ ] 分区配置
  - [ ] compose.yaml
  - [ ] README.md

- [ ] **vector2doris/** - 写入 [Apache Doris](https://doris.apache.org/)
  - [ ] HTTP Stream Load sink
  - [ ] 分区配置
  - [ ] compose.yaml
  - [ ] README.md

- [ ] **vector2clickhouse/** - 写入 [ClickHouse](https://clickhouse.com/)
  - [ ] HTTP sink
  - [ ] 分区配置
  - [ ] compose.yaml
  - [ ] README.md

### 待添加的 Source 示例

- [x] **syslog** - 读取 syslog 数据（`vector-collect/proxies/haproxy/`）
- [x] **journald** - 读取 systemd journal（`vector-collect/system/ubuntu/vector-host.yaml`）
- [x] **kubernetes_logs** - K8s Pod 日志（`vector-collect/system/kubernetes/`）
- [x] **docker_logs** - 容器日志（`vector-collect/system/docker/`）
- [x] **prometheus_scrape** - 指标抓取（`vector-collect/**/*_with_metrics/`）
- [x] **postgresql_metrics** - PostgreSQL 指标（`vector-collect/dbs/postgresql_with_metrics/`）
- [ ] **kafka** - 消费 Kafka topic
- [ ] **stdin** - 标准输入

### 待添加的 Transform 示例

- [ ] **filter** - 事件过滤
- [ ] **route** - 事件路由到多个 sink
- [ ] **aggregate** - 聚合统计
- [ ] **dedupe** - 去重

### 待完善的文档

- [ ] 各 sink 示例的独立 README
- [ ] 性能调优指南
- [ ] 故障排查手册

## License

MIT
