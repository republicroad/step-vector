# Vector 消费阿里云 SLS (Kafka 协议) → 阿里云 OSS

使用 [Vector](https://vector.dev) 的 **`kafka` source**（librdkafka 消费者）通过 **SLS Kafka 兼容协议**实时消费阿里云日志服务（SLS）的日志，规范化时间字段后按北京时间 Hive 分区写入阿里云 OSS（`aws_s3` sink）。支持 JSON + Parquet 双输出。

> **官方参考**（均为阿里云 SLS 官方文档，链接已逐页核验）：
> - Kafka 兼容协议总览（上传/写入 + "消费需工单"提示 + Vector 上传示例）：https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le
> - 消费 SDK 总览与限制说明（Java/Go/Python/C#/Franz/Sarama 示例入口）：https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html
> - Confluent-Kafka-Go 消费示例（Vector 基于 librdkafka，认证写法同源）：https://sls.aliyun.com/doc/en/oscompatibledemo/confluent_go_kafka_consume.html
> - Kafka 兼容功能说明/兼容限制/消息体字段场景（中文）：https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html
> - 服务入口（Endpoint 列表）：https://www.alibabacloud.com/help/en/sls/developer-reference/service-entrance
> - Vector Kafka source：https://vector.dev/docs/reference/configuration/sources/kafka/
>
> 详细的"配置项 ↔ 官方依据"对应关系见下文 [官方配置来源对照](#官方配置来源对照)。

## 目录结构

```
source/sls/
├── vector-sls.yaml               # 生产配置：SLS → OSS (JSON + Parquet 双输出)
├── vector-sls-test.yaml          # 测试配置：console sink（连真实 SLS 验证）
├── gen-sls-log.py                # 本地 Kafka 模拟生产者（离线验证用）
├── secrets/
│   ├── sls-secrets-template.json # SLS/OSS 密钥模板
│   └── .gitignore                # 忽略真实密钥
└── README.md                     # 本文档
```

## 架构

```
┌──────────┐  写入日志    ┌─────────────────────────────────────────┐
│ 业务应用 │ ──────────▶  │ SLS Project: my-project                 │
│          │              │   Logstore: my-logstore  (= Kafka Topic)│
└──────────┘              └──────────────────┬──────────────────────┘
                                             │ Kafka 兼容协议 (SASL_SSL)
                                             │ bootstrap = project.endpoint:port
                         ┌───────────────────▼────────────────────────┐
                         │ Vector                                       │
                         │  kafka source (PLAIN, username=project,      │
                         │               password=AK#SK, tls=true)      │
                         │  → parse_sls (JSON 解析 + 事件时间 + ts)     │
                         │  → partition (北京时间 Hive 分区)            │
                         └─────────┬──────────────────┬─────────────────┘
                                   │                  │
                                   ▼                  ▼
                              aliyun_oss        aliyun_oss_parquet
                              (JSON gzip,      (Parquet snappy,
                               分钟级分区)       小时级分区)
```

## SLS_ENDPOINT 如何配置与获取

**SLS_ENDPOINT 不是控制台里单独显示的配置，而是三段拼接**：`{Project名称}.{region 的 SLS Endpoint}:{端口}`——Project 名作为域名前缀，这是 SLS Kafka 兼容协议的寻址方式。

| 网络 | 完整值示例 | 端口 |
|------|-----------|------|
| **公网** | `my-project.cn-hangzhou.log.aliyuncs.com:10012` | **10012** |
| **内网/VPC**（同地域 ECS、ACK 等） | `my-project.cn-hangzhou-intranet.log.aliyuncs.com:10011` | **10011** |

获取步骤：

1. **确认 Project 所属地域**：SLS 控制台 → 项目列表，Project 概览页显示所属 Region 与「访问域名」（如 `cn-hangzhou.log.aliyuncs.com` / `cn-hangzhou-intranet.log.aliyuncs.com`）
2. **按地域查官方服务入口表**：https://www.alibabacloud.com/help/en/sls/developer-reference/service-entrance （每个地域有公网/内网两个域名，k8s 等海外规范化地域写法不同，以列表页为准）
3. **加端口**：公网 `10012`，内网 `10011`（约定值，无需在控制台查询）
4. **拼 Project 前缀**：`{project}.{endpoint}:{port}`，如 `my-project.cn-hangzhou.log.aliyuncs.com:10012`

示例环境变量（生产配置 `vector-sls.yaml` 使用）：

```bash
# 公网消费
export SLS_ENDPOINT="my-project.cn-hangzhou.log.aliyuncs.com:10012"
export SLS_LOGSTORE="app-logs"
# 内网消费（同地域 ECS/容器）
export SLS_ENDPOINT="my-project.cn-hangzhou-intranet.log.aliyuncs.com:10011"
```

## 认证：SASL_SSL + PLAIN

SLS Kafka 兼容协议**仅支持 SASL_SSL**（无明文端口），认证细节与标准 Kafka 不同：

| 参数 | 值 | 说明 |
|------|-----|------|
| `sasl.username` | **Project 名称** | 不是 AccessKey ID！ |
| `sasl.password` | **`AccessKeyID#AccessKeySecret`** | AK 与 SK 用 `#` 拼接，不是 SK 单独 |
| `sasl.mechanism` | `PLAIN` | 协议版本 2.2 |
| `tls.enabled` | `true` | 强制加密 |

> **消费开通**：使用 Kafka 消费组实时消费 SLS 数据，需[提交工单](https://smartservice.console.alibabacloud.com/console.htm#/ticket/add)联系阿里云技术支持开通（上传/写入方向无需工单）。

**消费方向限制**（官方文档）：

- 一个消费组最多消费 50 个 Logstore；一个 Logstore 最多被 15 个消费组消费
- **Topic 不支持通配符/正则**，只能直接指定 Logstore 名称
- Kafka 概念映射：Topic=Logstore、Partition=Shard（可分裂/合并/过期）、Offset=Cursor
- 不支持事务，At-least-once；offset 会跳跃，不要基于 offset 做延迟判断
- Kafka 消费组不出现在 SLS「消费组列表」，消费延迟需通过 CloudLens for SLS 查看

> **来源**：[开源兼容总览·限制说明](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)＋[Kafka 兼容协议总览](https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le)（工单提示）

## 官方配置来源对照

本目录所有 SLS 兼容配置均以下列官方页面为准：

| 本文配置项 | 官方依据 |
|------------|----------|
| `bootstrap_servers` 三段式 `{Project}.{Endpoint}:{Port}`（公网 10012 / 内网 intranet 10011） | [Confluent-Kafka-Go 消费示例](https://sls.aliyun.com/doc/en/oscompatibledemo/confluent_go_kafka_consume.html)：`"bootstrap.servers": fmt.Sprintf("%s.%s:%s", project, endpoint, port)` |
| `sasl.username` = Project 名称；`sasl.password` = `AccessKeyID#AccessKeySecret` | [开源兼容总览](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)（JAAS 示例：`username="projectName" password="access-key-id#access-key-secret"`）；[Confluent-Go 示例](https://sls.aliyun.com/doc/en/oscompatibledemo/confluent_go_kafka_consume.html)（`sasl.username: project`、`sasl.password: AK#SK`） |
| `session_timeout_ms: 120000` | [Confluent-Go 消费示例](https://sls.aliyun.com/doc/en/oscompatibledemo/confluent_go_kafka_consume.html)（`session.timeout.ms: 120000`） |
| `tls.enabled: true`（仅支持 SASL_SSL） | [开源兼容总览](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)；[功能说明](https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html) |
| 消费组限额（50 Logstore/组、15 组/Logstore）、不支持通配符、offset 跳跃、At-least-once、协议版本 2.2 | [开源兼容总览](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)「限制说明」；[功能说明](https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html)「兼容限制」 |
| 概念映射：Topic=Logstore、Partition=Shard、Offset=Cursor | [开源兼容总览](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)「概念映射」 |
| 消息体字段三场景（单字段 content / 多字段 JSON / `kafka_*` 导入字段） | [Kafka 消费时字段说明](https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html)（场景 1/2/3 原文） |
| 服务入口（各 region 公网/内网域名） | [Endpoints 服务入口列表](https://www.alibabacloud.com/help/en/sls/developer-reference/service-entrance) |
| 消费延迟查看（CloudLens for SLS，非配额/控制台消费组列表） | [功能说明](https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html)；[查看消费延迟](https://sls.aliyun.com/doc/oscompatibledemo/kafka_consume_monitor.html) |
| 消费方向需工单开通 | [Kafka 兼容协议总览](https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le)末尾说明（"To use a Kafka consumer group... submit a ticket"，2026-06 时点） |
| 上传方向 Vector 配置示例（kafka sink → SLS） | [总览·Example 7: Vector](https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le) |
| 各语言 SDK 消费示例（Java/Python/Franz/Sarama/C#） | [消费 SDK 列表](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)侧边栏；中文版如 [Java 消费与上报](https://sls.aliyun.com/doc/oscompatibledemo/kafka_java.html) |

## 快速开始

### 1. 配置密钥

```bash
cd source/sls

cp secrets/sls-secrets-template.json secrets/sls-secrets.json
# 编辑 secrets/sls-secrets.json：
# - project          SLS Project 名称（同时是 SASL username）
# - access_key_id / access_key_secret
# - sasl_password    手工拼接为 "AccessKeyID#AccessKeySecret"（注意 # 连接）
# - logstore         要消费的 Logstore（= Kafka Topic）
```

> **RAM 权限建议**：读操作需 `AliyunLogReadOnlyAccess`；写 OSS 需 OSS 系列权限。消费组成员（Vector 节点）可水平扩容，但受上述消费组限额约束。

### 2. 端到端验证（连真实 SLS，输出到控制台）

```bash
# 设置 endpoint 与 logstore 后运行
SLS_ENDPOINT="my-project.cn-hangzhou.log.aliyuncs.com:10012" \
SLS_LOGSTORE="app-logs" \
vector --config vector-sls-test.yaml
```

验证点：SASL_SSL 握手成功 → 能消费指定 Logstore → 消息体 JSON 解析（多字段日志）→ 事件时间解析 → `ts` 规范化字段生成 → Kafka 元数据（`.topic`=Logstore、`.partition`=Shard）。

### 3. 写入真实 OSS（生产环境）

```bash
vector --config vector-sls.yaml
# OSS 控制台确认 sls/log_json/year=.../ 出现对象；sls/log_parquet/ 出现 .parquet
```

配置中的 `${SLS_ENDPOINT}` / `${SLS_LOGSTORE}` / `${OSS_BUCKET}` / `${OSS_REGION}` / `${OSS_ENDPOINT}` 通过环境变量注入，或直接填值。

## 关键配置说明

### kafka source（SLS 兼容端点）

| 配置项 | 示例值 | 说明 |
|--------|--------|------|
| `bootstrap_servers` | `my-project.cn-hangzhou.log.aliyuncs.com:10012` | **{Project}.{Endpoint}:{Port}**，公网 10012 / 内网 10011 |
| `topics` | `["app-logs"]` | **= Logstore 名称**；不支持通配符 |
| `group_id` | `vector-sls-oss` | 消费组 ID |
| `auto_offset_reset` | `earliest` | 无位移时从头消费 |
| `session_timeout_ms` | `120000` | 官方消费示例使用 120s |
| `sasl.username` | Project 名称 | SECRET 引用 `sls_credentials.project` |
| `sasl.password` | `AccessKeyID#AccessKeySecret` | SECRET 引用 `sls_credentials.sasl_password` |
| `tls.enabled` | `true` | 强制加密 |

### 消费的消息体结构（官方规范）

SLS 通过 Kafka 兼容协议推送的消息 **value** 结构取决于 Logstore 日志的字段组成：

| 场景 | Logstore 日志形态 | 消费到的 Value |
|------|-------------------|----------------|
| 1 | 只有一个内容字段（如仅 `content`） | 该字段的**原值**（非 JSON） |
| 2 | 多个字段（如 `url` + `method`） | **JSON 编码内容**，如 `{"url":"/","method":"get"}` |
| 3 | 日志含 `kafka_topic`/`kafka_partition`/`kafka_offset`/`key`/`value` 字段 | 按导入 Kafka 数据的 Key/Value 字段映射 |

> **注意**：消息体中**没有** `__topic__`/`__source__`/`__timestamp__` 等 SLS 保留字段——时间以日志自身字段为准（本示例 transform 取事件 `timestamp` 字段）。单字段 content 日志（场景 1）的 value 非 JSON，`parse_sls` 中 parse_json 失败后按原样保留 message 继续流转。
>
> **官方来源**：[Kafka 消费时字段说明（场景 1/2/3）](https://sls.aliyun.com/doc/oscompatibledemo/kafka_overview.html)

### 事件时间语义

| 优先级 | 来源 | 格式 |
|--------|------|------|
| 1 | 事件 `timestamp` 字段 | `2026-09-07 17:09:55,994`（裸格式，**按北京时间解释**）、`.%3f` 点号毫秒变体、RFC3339 |
| 2 | Vector 摄入时间 | 全部解析失败时兜底 + warn 日志 |

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

### Kafka 元数据字段（自动附加）

| 字段 | 含义 |
|------|------|
| `.topic` | 消费的 Logstore 名称 |
| `.partition` | 分区号（对应 SLS Shard） |
| `.offset` | 分区内位移（对应 Cursor；**注意会跳跃，不要用于延迟判断**） |
| `.message_key` | 消息 key（SLS 单字段日志时为字段名，多字段时为空） |
| `.source_type` | 固定为 `kafka` |

### Hive 分区字段（北京时间）

| 字段 | 格式 | 示例 |
|------|------|------|
| `partition_year` | `%Y` | 2026 |
| `partition_month` | `%m` | 09 |
| `partition_day` | `%d` | 07 |
| `partition_hour` | `%H` | 14 |
| `partition_minute` | `%M` | 30 |

## 消费组与水平扩容

- Vector 实例数 ≤ 分区（Shard）数时，rebalance 自动分摊分区
- 实例数 > 分区数时多余实例空闲——**Shard 数 = 并行消费上限**，需先在 SLS 控制 Shard 扩容
- SLS Shard 支持分裂/合并/过期，动态变化会反映为分区变化

## 运维与排查

### 常用命令

```bash
# 前台运行查看日志
vector --config vector-sls.yaml

# SLS 消费延迟：SLS 控制台 → CloudLens for SLS
# （Kafka 兼容消费组不出现在常规「消费组管理」列表中）

# 手动造消息验证全链路：在目标 Logstore 通过 SDK/控制台写入测试日志
```

### 常见故障排查

| 现象 | 排查方向 |
|------|----------|
| `SASL authentication failed` | password 是否为 `AK#SK` 拼接（不是单独 SK）；RAM 用户权限 |
| `SSL handshake failed` / 连接失败 | 端口：公网 10012、内网 10011；`tls.enabled: true` 是否配置；内网需同地域 VPC |
| bootstrap 解析失败 | 域名前缀是否带 **Project 名**（`project.endpoint:port` 三段式） |
| `UnknownTopicOrPartition` | topic 是否写**纯 Logstore 名**（无 project 前缀）；Logstore 与 Project 是否存在 |
| 连上但不消费 / lag 增长 | ① 消费方向是否需要工单开通 ② 是否超过 15 消费组/Logstore 或 50 Logstore/组 ③ Sink 阻塞（OSS 写入慢） |
| 频繁 rebalance | Vector 处理慢→官方示例 `session_timeout_ms: 120000` |
| 消息重复 | At-least-once 正常现象；按 `.topic/.partition/.offset` 幂等去重 |

## 文件清单

| 文件 | 说明 |
|------|------|
| `vector-sls.yaml` | 生产配置：SLS → OSS (JSON gzip + Parquet snappy 双输出) |
| `vector-sls-test.yaml` | 测试配置：console sink，连真实 SLS 验证 |
| `gen-sls-log.py` | 本地 Kafka 模拟生产者（离线端到端验证用，非真实 SLS 链路） |
| `secrets/sls-secrets-template.json` | 密钥模板（project/AK/SK/sasl_password/endpoint） |
| `secrets/.gitignore` | 忽略真实密钥文件 |
| `README.md` | 本文档 |

## 相关资源

- [SLS Kafka 兼容协议文档](https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le)
- [SLS Kafka 消费 SDK 示例（含各语言）](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)
- [SLS 服务入口（Endpoint 列表）](https://www.alibabacloud.com/help/en/sls/developer-reference/service-entrance)
- [Vector Kafka Source 官方文档](https://vector.dev/docs/reference/configuration/sources/kafka/)
- [本仓库 vector2oss](../../vector2oss/README.md) —— File source 采集对比参考
- [本仓库 source/kafka](../kafka/README.md) —— 标准 Kafka 消费对比参考