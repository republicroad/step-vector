# Vector 消费阿里云 SLS (Kafka 协议) → 阿里云 OSS

使用 [Vector](https://vector.dev) 的 **`kafka` source**（librdkafka 消费者）通过 **SLS Kafka 协议** 消费阿里云日志服务（SLS）中的日志，解析后按事件时间 Hive 分区写入阿里云 OSS（`aws_s3` sink，OSS 兼容 S3 API）。支持 JSON + Parquet 双输出。

> **参考文档**：
> - SLS Kafka 协议消费：https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le
> - Vector Kafka source：https://vector.dev/docs/reference/configuration/sources/kafka/

## 目录结构

```
source/sls/
├── vector-sls.yaml              # 生产配置：SLS → OSS (JSON + Parquet 双输出)
├── vector-sls-test.yaml         # 测试配置：console sink（连真实 SLS 验证）
├── secrets/
│   ├── sls-secrets-template.json # SLS/OSS 密钥模板
│   └── .gitignore               # 忽略真实密钥
└── README.md                    # 本文档
```

## 架构

```
┌─────────────┐  SLS 日志    ┌────────────────────────────────────┐
│ 业务应用    │ ──────────▶  │ SLS Project / Logstore             │
│ (产生日志)  │  写入 SLS    │ (开启 Kafka 协议消费)              │
└─────────────┘              └──────────────┬─────────────────────┘
                                            │ SLS Kafka 协议
                                            │ (SASL_SSL + PLAIN/SCRAM)
                         ┌──────────────────▼────────────────────┐
                         │ Vector                                   │
                         │  kafka source (SASL_SSL + PLAIN/SCRAM)  │
                         │  → parse_sls (JSON + SLS 字段提取)      │
                         │  → partition (北京时间 Hive 分区)       │
                         └──────────┬───────────────┬──────────────┘
                                    │               │
                                    ▼               ▼
                              aliyun_oss      aliyun_oss_parquet
                              (JSON gzip,    (Parquet snappy,
                               分钟级分区)     小时级分区)
```

## SLS 开启 Kafka 协议消费

### 1. 开启 Kafka 协议消费

1. 登录 [SLS 控制台](https://sls.console.aliyun.com/)
2. 进入目标 Project → 目标 Logstore
3. 点击右上角 **“数据加工”** 或 **“消费与投递”** → **“Kafka 协议消费”**
4. 点击 **“开启 Kafka 协议消费”**
5. 记录生成的 **Endpoint**（格式：`${region}.log.aliyuncs.com:10011`，如 `cn-hangzhou.log.aliyuncs.com:10011`）

### 2. Topic 映射规则

SLS 将 **Project + Logstore** 映射为 Kafka Topic：

```
Topic 格式：${project}_${logstore}
示例：my-project_my-logstore
```

- 多个 Logstore 对应多个 Topic
- 支持正则订阅：`^my-project_.*` 可匹配该 Project 下所有 Logstore

### 3. 认证方式

SLS Kafka 协议支持两种 SASL 机制：

| 机制 | 说明 | 适用场景 |
|------|------|----------|
| **PLAIN** | 用户名=AccessKey ID，密码=AccessKey Secret | 最常用，SLS 默认支持 |
| **SCRAM-SHA-512** | 更安全，需在 SLS 控制台开启 SCRAM 支持 | 高安全要求场景 |

> **注意**：SLS 强制要求 **SASL_SSL**（端口 10011），不支持 PLAINTEXT。

## 快速开始

### 1. 配置密钥

```bash
cd source/sls

# 复制模板并编辑
cp secrets/sls-secrets-template.json secrets/sls-secrets.json
# 编辑 secrets/sls-secrets.json 填入：
# - access_key_id / access_key_secret (RAM 用户 AK/SK)
# - endpoint (如 cn-hangzhou.log.aliyuncs.com:10011)
# - project / logstore / topic
# - oss_bucket / oss_region / oss_endpoint (写 OSS 时需要)
```

> **密钥权限建议**：RAM 用户需具备 `AliyunLogReadOnly` + `AliyunOSSFullAccess` 权限

### 2. 离线端到端验证（连真实 SLS，输出到控制台）

```bash
cd source/sls

# 方式一：直接运行 Vector（需先配置 sls-secrets.json）
vector --config vector-sls-test.yaml

# 方式二：通过 compose 运行（推荐，自动挂载密钥）
# 需先创建 compose-test.yaml（见下文），或直接用 vector 命令
vector --config vector-sls-test.yaml
```

> **验证点**：
> - ✅ SASL_SSL 握手成功
> - ✅ 能消费指定 Project/Logstore 数据
> - ✅ 解析 JSON 并提取 SLS 字段（`__topic__`、`__source__`、`__timestamp__` 等）
> - ✅ 事件时间解析正确（优先 `__timestamp__`，回退 RFC3339）
> - ✅ Hive 分区字段生成正确（北京时间）
> - ✅ Kafka 元数据字段（`.topic`/.partition`/.offset`/.message_key）正确附加

### 3. 写入真实 OSS（生产环境）

```bash
cd source/sls

# 确保 secrets/sls-secrets.json 已配置完整（含 OSS 密钥）
# 启动
vector --config vector-sls.yaml

# 或通过 compose（如有 compose 编排）
# podman compose up -d

# 验证
# OSS 控制台确认 sls/log_json/year=.../ 路径下出现对象
# 或 sls/log_parquet/ 路径下出现 .parquet 文件
```

### 4. 接入生产环境（无需本地 Kafka/Producer）

直接修改 `vector-sls.yaml` 的源配置指向真实 SLS：

```yaml
sources:
  sls_logs:
    type: kafka
    bootstrap_servers: "cn-hangzhou.log.aliyuncs.com:10011"
    topics:
      - "my-project_my-logstore"
    group_id: vector-sls-oss
    auto_offset_reset: earliest
    security_protocol: SASL_SSL
    sasl:
      enabled: true
      mechanism: PLAIN      # 或 SCRAM-SHA-512
      username: SECRET[sls_credentials.access_key_id]
      password: SECRET[sls_credentials.access_key_secret]
```

无需本地 Kafka/Producer 容器，Vector 直连 SLS Kafka 协议端点。

## 关键配置说明

### SLS Kafka Source 关键配置

| 配置项 | 示例值 | 说明 |
|--------|--------|------|
| `bootstrap_servers` | `cn-hangzhou.log.aliyuncs.com:10011` | SLS Kafka 协议 endpoint（地域相关） |
| `topics` | `["my-project_my-logstore"]` | 数组；支持正则 `^my-project_.*` |
| `group_id` | `vector-sls-oss` | 消费组 ID，**位移存 broker 端** |
| `auto_offset_reset` | `earliest` | 无位移时从头消费 |
| `session_timeout_ms` | `30000` | 心跳超时，SLS 建议 ≥ 30s |
| `security_protocol` | `SASL_SSL` | **SLS 强制要求** |
| `sasl.mechanism` | `PLAIN` / `SCRAM-SHA-512` | 认证机制 |
| `sasl.username` | AccessKey ID | RAM 用户 AK |
| `sasl.password` | AccessKey Secret | RAM 用户 SK |

### SLS 保留字段映射表

SLS 通过 Kafka 协议推送的消息体包含以下保留字段（JSON 格式）：

| SLS 字段 | 含义 | Vector 字段映射 |
|----------|------|-----------------|
| `__topic__` | 日志主题（用户自定义，可为空） | `.sls_topic` |
| `__source__` | 日志来源（IP/主机名等） | `.sls_source` |
| `__timestamp__` | 日志时间戳（Unix 秒，SLS 写入时间） | `.sls_timestamp` → 事件无 timestamp 字段时回退为事件时间 |
| `__partition_time__` | 分区时间（Unix 秒） | `.sls_partition_time` |
| `__shard__` | Shard ID | `.sls_shard` |

> **字段提取逻辑**：`parse_sls` transform 中显式提取上述字段，生成 `.sls_topic`、`.sls_source` 等结构化字段，原始字段保留在 JSON 中。

### 事件时间语义

| 优先级 | 来源 | 格式 |
|--------|------|------|
| 1 | 事件 `timestamp` 字段 | `2026-09-07 17:09:55,994`（裸格式，**按北京时间解释**）、`.%3f` 点号毫秒变体、RFC3339 |
| 2 | `__timestamp__` | SLS 写入时间，Unix 秒/毫秒（自动识别） |
| 3 | Vector 摄入时间 | 全部解析失败时兜底 + warn 日志 |

> **裸格式时区处理**：无时区后缀的 timestamp 在 transform 中追加 `+08:00` 后解析（`%Y-%m-%d %H:%M:%S,%3f %:z`），结果确定性不依赖容器时区设置，与 Hive 分区（北京时间）语义一致。

### 时间字段规范：ts (RFC3339)

**最佳实践**：面向全球业务/跨系统消费的日志，时间字段建议原生采用 **RFC 3339** 格式（如 `2026-09-07T17:09:55.994+08:00`）——带时区、跨语言/跨系统无歧义，可直接被 Arrow/Spark/DuckDB 等引擎解析。

**存量兼容**：为兼容已有项目（时间字段为裸格式），transform 会为**每条事件强制生成 `ts` 字段**：

| 字段 | 来源 | 示例 |
|------|------|------|
| `timestamp` | 事件原始字段（可能为裸格式） | `2026-09-07 17:09:55,994` |
| `ts` | **Vector 规范化生成（RFC3339 UTC）** | `2026-09-07T09:09:55.994Z` |

- 新接入的下游/项目统一消费 `ts`，无需关心各来源时间格式的差异
- 存量项目逐步迁移为原生 RFC3339 后，可下线裸格式兼容分支，仅保留事件时间直读

### Hive 分区字段（北京时间）

| 字段 | 格式 | 示例 |
|------|------|------|
| `partition_year` | `%Y` | 2026 |
| `partition_month` | `%m` | 09 |
| `partition_day` | `%d` | 07 |
| `partition_hour` | `%H` | 14 |
| `partition_minute` | `%M` | 30 |

> 时区固定为 `Asia/Shanghai`，用于 `key_prefix` 模板渲染。

### Kafka 元数据字段（自动附加）

| 字段 | 含义 |
|------|------|
| `.topic` | 消费的 SLS topic（即 `${project}_${logstore}`） |
| `.partition` | 分区号 |
| `.offset` | 分区内位移 |
| `.message_key` | 消息 key（SLS 消息通常无 key，字段可能为空） |
| `.headers` | 消息 headers（通常为空对象） |
| `.source_type` | 固定为 `kafka` |

## SLS 特有配置细节

### Topic 映射与订阅策略

```yaml
# 单个 Logstore
topics:
  - "my-project_my-logstore"

# 正则匹配该 Project 下所有 Logstore
topics:
  - "^my-project_.*"

# 多个 Project/Logstore（需同消费组）
topics:
  - "project-a_logstore-1"
  - "project-b_logstore-2"
```

### 消费组与位移语义

| 维度 | 行为 |
|------|------|
| 位移存储 | Broker 端 `__consumer_offsets`（非本地 checkpoint） |
| 删 `data_dir` 重启 | 不影响，从已提交位移继续 |
| 换 `group_id` | 等效新消费组，按 `auto_offset_reset` 起点消费（可做全量重放） |
| 语义 | at-least-once（每 5s 批量提交，崩溃重放最多重复一批） |

### 水平扩容

- Vector 实例数 ≤ 分区数时，rebalance 自动把分区均摊给各实例
- 实例数 > 分区数时多余实例空闲——**分区数 = 消费并行度上限**
- 单个 Vector 实例重启超过 `session_timeout_ms` 会触发 rebalance，其余实例接管

### SLS 分区数 = 消费并行度上限

- SLS Logstore 默认分区数（Shard 数）决定最大并行消费数
- 需更高吞吐 → SLS 控制台扩容 Shard → 再扩容 Vector 实例

## 运维与排查

### 常用命令

```bash
# 查看 Vector 日志
vector --config vector-sls.yaml    # 前台运行查看日志
# 或
podman compose logs -f vector      # 若用 compose 编排

# 消费组 lag 监控（需 SLS 控制台或 Kafka 工具）
# SLS 控制台：日志服务 > 消费组监控

# 手动验证消费位移
# SLS 控制台 > 消费组管理 > 查看位移/lag

# 手动造消息验证全链路（SLS 控制台写入测试日志）
# 或使用 SLS SDK 写入测试数据
```

### 常见故障排查

| 现象 | 排查方向 |
|------|----------|
| `SASL authentication failed` | 1) AK/SK 是否正确 2) 机制是否匹配（PLAIN vs SCRAM） 3) RAM 用户权限是否包含 `AliyunLogReadOnly` |
| `SSL handshake failed` | 1) 端口是否 10011 2) SSL 证书链是否信任（`ssl.ca.location`） 3) 网络是否通（VPC/安全组） |
| `Unknown topic or partition` | Topic 名是否为 `${project}_${logstore}` 确切匹配；SLS 是否开启 Kafka 协议消费 |
| 连上但不消费 / lag 增长 | 1) 分区数不足 → SLS 扩容 Shard 2) Vector 处理慢 → 调大 `session_timeout_ms` 或扩容实例 3) Sink 阻塞（OSS 写入慢） |
| 频繁 rebalance | Vector 处理慢导致心跳超时 → 调大 `session_timeout_ms` 至 60s+ |
| 消息重复 | at-least-once 语义正常现象；下游按 `.topic/.partition/.offset` 幂等去重 |
| 超大消息被丢 | SLS 单条日志上限 1MB；librdkafka 单条上限 `message.max.bytes`，需调大 `receive.message.max.bytes` |

### 网络连通性检查

```bash
# 从 Vector 容器内测试连通性
podman exec <vector-container> nc -zv <endpoint> 10011

# 或用 openssl 验证 SSL 握手
podman exec <vector-container> openssl s_client -connect <endpoint>:10011 -servername <endpoint>
```

## 进阶：切换 SASL 机制为 SCRAM-SHA-512

在 `vector-sls.yaml` 中修改 `sasl` 配置：

```yaml
# 取消注释 SCRAM 配置，注释 PLAIN 配置
security_protocol: SASL_SSL
sasl:
  enabled: true
  mechanism: SCRAM-SHA-512
  username: SECRET[sls_credentials.access_key_id]
  password: SECRET[sls_credentials.access_key_secret]
```

> **前提**：SLS 控制台已为该 Project/Logstore 开启 SCRAM 认证支持。

## 文件清单

| 文件 | 说明 |
|------|------|
| `vector-sls.yaml` | 生产配置：SLS → OSS (JSON gzip + Parquet snappy 双输出) |
| `vector-sls-test.yaml` | 测试配置：console sink，连真实 SLS 验证，无需 OSS 密钥 |
| `secrets/sls-secrets-template.json` | 密钥模板（复制为 sls-secrets.json 填入真实值） |
| `secrets/.gitignore` | 忽略真实密钥文件 |
| `README.md` | 本文档 |

## 相关资源

- [SLS Kafka 协议消费官方文档](https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le)
- [Vector Kafka Source 官方文档](https://vector.dev/docs/reference/configuration/sources/kafka/)
- [Vector AWS S3 Sink 官方文档](https://vector.dev/docs/reference/configuration/sinks/aws_s3/)
- [本仓库 vector2oss](../../vector2oss/README.md) —— File source 采集对比参考
- [本仓库 source/kafka](../kafka/README.md) —— 标准 Kafka 消费对比参考