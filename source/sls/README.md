# Vector 消费阿里云 SLS (Kafka 协议) → 阿里云 OSS

使用 [Vector](https://vector.dev) 的 **`kafka` source**（librdkafka 消费者）通过 **SLS Kafka 兼容协议**实时消费阿里云日志服务（SLS）的日志，规范化时间字段后按北京时间 Hive 分区写入阿里云 OSS（`aws_s3` sink）。支持 JSON + Parquet 双输出。

> **官方参考**（均为阿里云 SLS 官方文档，链接已逐页核验）：
> - Kafka 兼容协议总览（上传/写入 + Vector 上传示例）：https://www.alibabacloud.com/help/en/sls/use-the-kafka-protocol-to-upload-logs#aaccbd64bf9le
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
├── vector-sls.yaml               # 生产配置(公网)：SLS → OSS (JSON + Parquet 双输出)
├── vector-sls-intranet.yaml      # 生产配置(内网)：同上，endpoint 换 VPC 内网域名
├── vector-sls-test.yaml          # 测试配置：console sink（连真实 SLS 验证）
├── compose.yaml                  # 容器运行：挂载生产配置与密钥
├── compose-test.yaml             # 容器运行测试配置（console 输出排查用）
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

本仓库示例配置（已填入 `vector-sls.yaml` / `vector-sls-intranet.yaml`）：
Project=`my-project`，Logstore=`app-logs`。

```bash
# 公网消费（本机/开发环境，vector-sls.yaml 与 vector-sls-test.yaml）
export SLS_ENDPOINT="my-project.cn-hangzhou.log.aliyuncs.com:10012"
export SLS_LOGSTORE="app-logs"
# 内网消费（同地域 cn-hangzhou ECS/容器，vector-sls-intranet.yaml）
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

> **消费开通**：实测（2026-09）公网 Kafka 消费组实时消费 SLS 无需提交工单，可直接消费。

**消费方向限制**（官方文档）：

- 一个消费组最多消费 50 个 Logstore；一个 Logstore 最多被 15 个消费组消费
- **Topic 不支持通配符/正则**，只能直接指定 Logstore 名称
- Kafka 概念映射：Topic=Logstore、Partition=Shard（可分裂/合并/过期）、Offset=Cursor
- 不支持事务，At-least-once；offset 会跳跃，不要基于 offset 做延迟判断
- Kafka 消费组不出现在 SLS「消费组列表」，消费延迟需通过 CloudLens for SLS 查看

> **来源**：[开源兼容总览·限制说明](https://sls.aliyun.com/doc/en/oscompatibledemo/overview.html)

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
# endpoint/logstore 已填入配置（公网），直接运行
vector --config vector-sls-test.yaml
```

验证点：SASL_SSL 握手成功 → 能消费指定 Logstore → 消息体 JSON 解析（多字段日志）→ 事件时间解析 → `ts` 规范化字段生成 → Kafka 元数据（`.topic`=Logstore、`.partition`=Shard）。

### 3. 写入真实 OSS（生产环境）

```bash
vector --config vector-sls.yaml            # 公网（本机/开发环境）
vector --config vector-sls-intranet.yaml   # 内网（同地域 cn-hangzhou VPC 内）
# OSS 控制台确认 sls/log_json/year=.../ 出现对象；sls/log_parquet/ 出现 .parquet
```

SLS endpoint/logstore 与 OSS bucket(`vector-demo`)/region(`cn-hangzhou`)/endpoint 均已填入配置；SASL 认证（project / AK#SK）与 OSS AK/SK 从 `secrets/sls-secrets.json` 读取。

容器方式运行（挂载哪个配置由 `SLS_CONFIG` 决定，默认公网）：

```bash
podman compose up -d                                                    # 公网（本机/开发环境）
SLS_CONFIG=vector-sls-intranet.yaml podman compose up -d               # 内网（同事地域 cn-hangzhou VPC 内的节点）
# PowerShell: $env:SLS_CONFIG="vector-sls-intranet.yaml"; podman compose up -d
```

> **注意**：`vector-sls-intranet.yaml` 的 endpoint 仅同地域 VPC 可达，**不能在公网环境运行测试**（会连接失败）；公网配置同样只应在公网消费（VPC 内建议优先走内网域名，免公网流量费）。

## 参数注入方式

Vector 有两套"变量"机制，写入位置的选择依据如下：

| 机制 | 语法 | 适用范围 | 状态 |
|------|------|----------|------|
| **模板语言**（事件级） | `{{ field }}` + strftime | 仅文档标注为 template 的字段（`key_prefix` / file sink `path` / ES `bulk.index` 等） | 始终可用 |
| **环境变量插值** | `${VAR}` / `${VAR:-默认}` / `${VAR:?必填报错}`，转义 `$$` | 配置文件任意字符串字段（YAML 解析前替换） | **v0.57+ 默认关闭**，需 `VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true` 或 CLI 参数 `--dangerously-allow-env-var-interpolation`，参考 [Environment Variables](https://vector.dev/docs/reference/environment_variables/) |

本仓库的选择：

- **bucket / region / endpoint / logstore 写死在 YAML**——它们是路由/环境标识而非秘密；写在配置里可读、可 review、`grep` 一眼可见；换场景=改一个值（内网变体独立成文件）
- **AK/SK / project / sasl_password 放 `secrets/sls-secrets.json`**——凭据从不入配置明文；`SECRET[sls_credentials.*]` 引用
- 环境插值若确需启用（多环境/CI），必须在 Vector 侧显式打开注：占位符默认不生效，切勿直接写 `${VAR}`（会被当作字面量字符串）

## 关键配置说明

### kafka source（SLS 兼容端点）

| 配置项 | 示例值 | 说明 |
|--------|--------|------|
| `bootstrap_servers` | `my-project.cn-hangzhou.log.aliyuncs.com:10012` | **{Project}.{Endpoint}:{Port}**，公网 10012 / 内网 10011 |
| `topics` | `["app-logs"]` | **= Logstore 名称**；不支持通配符 |
| `group_id` | `vector-sls-oss` | 消费组 ID |
| `auto_offset_reset` | `latest` | 无位移时从最新开始（避免全量重放）；需回补历史时新建消费组 + earliest |
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

### OSS 写入最佳实践（batch / buffer / acknowledgements）

按当前实测流量（~180 条/s、~2KB/条 ≈ 350KB/s ≈ 30GB/天）与阿里云 OSS 最佳实践（对象 64MB+ 量级、减少小对象与 PUT 请求）调优：

| 参数 | JSON sink | Parquet sink | 说明 |
|------|-----------|--------------|------|
| `batch.timeout_secs` | 300 | 300 | 分区桶 5 分钟无新事件即 flush；对象最多延迟 5 分钟落盘 |
| `batch.max_bytes` | 32MB | 64MB | 分钟桶 ~20MB → 正常每分钟 1 个对象；Parquet 小时桶 ~1.2GB，64MB 上限避免 ~125 个小文件/小时 |
| `batch.max_events` | 100000 | 100000 | 兜底上限（~2KB/条时不会先于 max_bytes 触发） |
| `buffer` | disk 5GiB | disk 5GiB | OSS 故障时事件落盘暂存（data_dir 卷，128MB 块预分配），可扛 ~4h 故障；写满后 `block` 背压暂停消费，不丢数据 |
| `acknowledgements.enabled` | true | true | OSS 写入成功确认后 Kafka 位移才提交，端到端 at-least-once |

要点：

- **分区准确性不受长 batch 影响**：Vector `aws_s3` sink 按 `key_prefix` 模板自动分桶，每个分钟/小时分区独立成批，事件不会跨分区混写
- **容量估算**：5GiB buffer ÷ 350KB/s ≈ 4 小时 OSS 不可用容忍度；流量增大后按需上调 `buffer.max_size`
- **Parquet 已去除冗余 `message` 列**（`parquet_prepare` transform）：Parquet 仅存解析后字段（原始 JSON 行占单条体积 ~60%），文件体积约省 50%；JSON 输出仍为完整原始行
- **Parquet 字段类型治理**：`tenantId`/`line` 强制 string，防止 `auto_infer` 跨文件类型漂移导致 DuckDB 联合查询报错；接入新字段时在 `parquet_prepare` 按同样方式补充
- **压缩**：Parquet 列内 zstd（较 snappy 再省 ~20-30% 存储，存量 snappy 文件仍可正常查询）；JSON 输出 gzip

### OSS 生命周期规则（成本优化，bucket 侧配置）

`sls/*` 前缀为日志分析数据，建议在 OSS 控制台为 bucket `vector-demo` 配置生命周期规则（非 Vector 配置）：

- 30 天：转低频访问（IA）存储
- 90 天：转归档/冷归档（读取需解冻，按查询模式权衡）
- 按合规要求设置到期删除

## 消费组与水平扩容

- Vector 实例数 ≤ 分区（Shard）数时，rebalance 自动分摊分区
- 实例数 > 分区数时多余实例空闲——**Shard 数 = 并行消费上限**，需先在 SLS 控制 Shard 扩容
- SLS Shard 支持分裂/合并/过期，动态变化会反映为分区变化

## 运维与排查

### 常用命令

```bash
# 前台运行查看日志
vector --config vector-sls.yaml

# 实时观测吞吐/错误（Vector API 已启用，端口仅映射到本机回环）
podman exec vector-sls-to-oss_vector_1 vector top --url http://localhost:8686
# 或本机访问 http://127.0.0.1:8686（GraphQL API）

# SLS 消费延迟：SLS 控制台 → CloudLens for SLS
# （Kafka 兼容消费组不出现在常规「消费组管理」列表中）

# 手动造消息验证全链路：在目标 Logstore 通过 SDK/控制台写入测试日志
```

### 容器日志轮转

- compose 已指定 `k8s-file` 日志驱动；但 podman 6.1.x（WSL machine）实测**不生效** `logging.options.max_size`（inspect 中 Config 为空、写满不轮转）
- 已在 podman machine 内写入 rootless 配置 `~/.config/containers/containers.conf`（`log_size_max = 104857600`，100MB），**下次 podman machine 重启后自动生效**（Windows 重启即触发）
- 生效前 ctr.log 无上限，但 Vector info 级日志增长极慢，无实际风险

### 常见故障排查

| 现象 | 排查方向 |
|------|----------|
| `SASL authentication failed` | password 是否为 `AK#SK` 拼接（不是单独 SK）；RAM 用户权限 |
| `SSL handshake failed` / 连接失败 | 端口：公网 10012、内网 10011；`tls.enabled: true` 是否配置；内网需同地域 VPC |
| bootstrap 解析失败 | 域名前缀是否带 **Project 名**（`project.endpoint:port` 三段式） |
| `UnknownTopicOrPartition` | topic 是否写**纯 Logstore 名**（无 project 前缀）；Logstore 与 Project 是否存在 |
| 连上但不消费 / lag 增长 | ① 是否超过 15 消费组/Logstore 或 50 Logstore/组 ② Sink 阻塞（OSS 写入慢） |
| 频繁 rebalance | Vector 处理慢→官方示例 `session_timeout_ms: 120000` |
| Parquet `does not support writing empty structs` | 事件含空对象/空数组字段（如 `headers:{}`）；已在 partition transform 中用 `filter` 清理空容器 |
| 消息重复 | At-least-once 正常现象；按 `.topic/.partition/.offset` 幂等去重 |

### buffer 存储上限与背压行为

disk buffer 到达 `max_size`（当前 5GiB/sink，两 sink 合计最多 10GiB）时，当前配置 `when_full: block` 下**不丢数据、逐级背压**：

1. sink 停止接收 → transform 阻塞 → kafka source 停止从 SLS 拉取，消费暂停（lag 增长，CloudLens for SLS 可观察）
2. 已缓冲事件（≈4h 流量）保留在本地，OSS 恢复后自动排空续传
3. 因启用 `acknowledgements`，未成功写入 OSS 的消息**不提交 offset**——数据仍留在 SLS，受 Logstore TTL 保护（默认 30 天 ≫ buffer 窗口）
4. OSS 恢复 → buffer 排空 → 从上次提交位置自动恢复消费，全程 at-least-once，无需人工干预

**边界情况**：

| 场景 | 行为 |
|------|------|
| 改为 `when_full: drop_newest` | 丢弃新事件、保留旧数据——会丢数据（当前未采用） |
| 物理磁盘先于 `max_size` 耗尽 | buffer 写入 IO 报错 → 事件被丢弃（真丢数据）；`max_size` 必须小于卷可用空间，且两个 sink 合计预留 10GiB |

**容量链路**：OSS 故障 → 前 ~4h 由本地 buffer 平滑吸收 → 之后消费暂停、数据积压在 SLS（最长 Logstore TTL）→ 恢复后追平。

## 文件清单

| 文件 | 说明 |
|------|------|
| `vector-sls.yaml` | 生产配置(公网)：SLS → OSS (JSON gzip + Parquet snappy 双输出) |
| `vector-sls-intranet.yaml` | 生产配置(内网)：同 vector-sls.yaml，endpoint 换 cn-hangzhou-intranet:10011 |
| `vector-sls-test.yaml` | 测试配置：console sink，连真实 SLS 验证 |
| `compose.yaml` | 容器运行：挂载生产配置与密钥，checkpoint 持久化到命名卷 |
| `compose-test.yaml` | 容器运行测试配置（console 输出），`podman compose -f compose-test.yaml up -d` |
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