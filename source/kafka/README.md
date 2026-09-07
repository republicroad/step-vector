# Vector 消费 Kafka → 阿里云 OSS

使用 [Vector](https://vector.dev) 的 **`kafka` source**（librdkafka 消费者）消费 Kafka topic 中的 JSON 日志，解析后按事件时间 Hive 分区写入阿里云 OSS（`aws_s3` sink，OSS 兼容 S3 API）。支持 JSON + Parquet 双输出。

典型场景：业务服务把埋点/日志发到 Kafka（削峰解耦），Vector 作为消费组一员旁路消费，落 OSS 做冷数据湖（回测、特征、审计），与 [vector2oss](../../vector2oss/README.md) 的 file source 采集互为补充。

## 目录结构

```
source/kafka/
├── vector.yaml                      # 生产配置：kafka source → OSS (JSON + Parquet)
├── vector-test.yaml                 # 测试配置：kafka source → console（离线验证）
├── compose.yaml                     # 生产编排：Kafka + producer + vector(OSS)
├── compose-test.yaml                # 测试编排：Kafka + producer + vector(console)
├── gen-log.py                       # 模拟生产者：JSON 日志发 Kafka（含晚到日志）
├── secrets/
│   ├── oss-secrets-template.json    # OSS 密钥模板
│   └── .gitignore                   # 忽略真实密钥
└── README.md                        # 本文档
```

## 架构

```
┌──────────┐  JSON 行   ┌─────────────────────────────┐
│ 业务服务 │ ─────────▶ │ Kafka topic: app-logs       │
│ producer │  key=oid   │ 3 partitions (KRaft 单节点) │
└──────────┘            └──────────────┬──────────────┘
                                       │ 消费组 vector-oss
                                       │ (offset 存 broker)
                        ┌──────────────▼──────────────┐
                        │ Vector                       │
                        │  kafka source                │
                        │  → parse_ts (JSON + 事件时间)│
                        │  → partition (北京时间分区)  │
                        └──────┬──────────────┬────────┘
                               │              │
                               ▼              ▼
                          aliyun_oss     aliyun_oss_parquet
                          (JSON gzip,    (Parquet snappy,
                           分钟级分区)    小时级分区)
```

## 快速开始

### 1. 离线端到端验证（无需 OSS 密钥）

Kafka + 生产者 + Vector 全部容器内闭环，事件打印到 Vector 的 stdout：

```bash
cd source/kafka

podman compose -f compose-test.yaml up -d

# 观察消费结果：每条事件带 .topic/.partition/.offset/.message_key 与 partition_* 字段
podman compose -f compose-test.yaml logs -f vector

# 验证消费组位移
podman compose -f compose-test.yaml exec kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group vector-test

# 清理
podman compose -f compose-test.yaml down -v
```

### 2. 写入真实 OSS

```bash
cd source/kafka

# 配置密钥（或直接复用 vector2oss 已配好的：cp ../../vector2oss/secrets/oss-secrets.json secrets/）
cp secrets/oss-secrets-template.json secrets/oss-secrets.json
# 编辑 secrets/oss-secrets.json 填入你的 RAM AccessKey

# 启动（Kafka + producer + vector，vector.yaml 按需改 bucket/region/endpoint）
podman compose up -d

# 验证
podman compose logs -f vector
# OSS 控制台确认 kafka/log_json/year=.../ 路径下出现对象
```

### 3. 接入真实 Kafka

把 vector.yaml 的 `bootstrap_servers` 指向真实集群即可，无需 Kafka/producer 两个容器：

```yaml
sources:
  kafka_logs:
    type: kafka
    bootstrap_servers: "broker1:9092,broker2:9092,broker3:9092"
    topics: [app-logs]              # 或 topics: ["^app-.*"] 正则订阅多个 topic
    group_id: vector-oss
    auto_offset_reset: earliest
```

集群开启 SCRAM 认证时追加：

```yaml
    sasl:
      enabled: true
      mechanism: SCRAM-SHA-512      #PLAIN / SCRAM-SHA-256 / SCRAM-SHA-512
      username: your-user
      password: your-password
```

## 关键配置说明

### kafka source

Vector 官方 Kafka 消费源，基于 librdkafka：

| 配置项 | 本示例值 | 说明 |
|--------|---------|------|
| `bootstrap_servers` | `kafka:9092` | 逗号分隔的 broker 列表 |
| `topics` | `[app-logs]` | 数组；以 `^` 开头按正则匹配 |
| `group_id` | `vector-oss` | 消费组 ID，**位移的关键**，见下节 |
| `auto_offset_reset` | `earliest` | 无位移/位移越界时的起点；`latest` 只消费新消息 |
| `session_timeout_ms` | `10000` | 心跳超时，超时触发 rebalance（默认 10s） |
| `commit_interval_ms` | `5000`（默认） | 位移自动提交间隔 |
| `framing` / `decoding` | `bytes`（默认） | 一条 Kafka 消息 = 一个事件，消息体原样进 `.message` |

**事件自动附加的元数据字段**（JSON 输出会原样带上，方便下游排查消息位置）：

| 字段 | 含义 |
|------|------|
| `.topic` | 消息来自的 topic |
| `.partition` | 分区号 |
| `.offset` | 分区内位移 |
| `.message_key` | 消息 key（`key_field` 默认字段名；未设 key 则无此字段） |
| `.headers` | 消息 headers（`headers_key` 默认字段名，无 headers 时为 `{}`） |
| `.source_type` | 固定为 `kafka` |

### 位移语义：与 file source 的 checkpoint 不同

| 维度 | file source（vector2oss） | kafka source（本示例） |
|------|---------------------------|------------------------|
| 进度存储 | 本地 `data_dir/checkpoints/` | **Broker 端 `__consumer_offsets`** |
| 删 data_dir 重启 | 从头重读（checkpoint 丢失） | 不影响，从已提交位移继续 |
| 换 `group_id` | — | 等效新消费组，按 `auto_offset_reset` 起点消费（可做全量重放） |
| 语义 | at-least-once | at-least-once（每 5s 批量提交，崩溃重放最多重复一批） |

`data_dir` 在本示例中仍需挂载，但只承载 sink 的 disk buffer（OSS 短暂不可写时落盘缓冲），不再是消费进度。

### 消费组与水平扩容

- Vector 实例数 ≤ 分区数时，rebalance 自动把分区均摊给各实例（3 分区最多 3 个 Vector 并行消费）
- 实例数 > 分区数时多余实例空闲——**分区数 = 消费并行度上限**，扩容先扩分区
- 单个 Vector 实例重启超过 `session_timeout_ms` 会触发 rebalance，其余实例接管

### key 与顺序保证

Kafka 只保证**分区内有序**。gen-log.py 以 `order_id` 作为消息 key，同一订单的事件恒定进同一分区，分区局部有序 → 单订单维度有序。OSS 侧文件名带 UUID，不依赖全局顺序。

### 晚到日志与事件时间分区

gen-log.py 与 [vector2oss/gen-log.py](../../vector2oss/gen-log.py) 相同，30% 日志时间戳回填最多 12 小时（`[late]` 标记）。`key_prefix` 引用解析后的事件时间，晚到消息落入旧时间目录，而非 Vector 处理时间目录——这是本仓库「事件时间分区」模式在 Kafka 链路上的复刻。

### 与 file source 采集的取舍

| 维度 | file → OSS（vector2oss） | Kafka → OSS（本示例） |
|------|--------------------------|------------------------|
| 耦合 | Vector 直读应用日志文件 | 应用只管发 Kafka，Vector 独立扩缩 |
| 削峰 | 磁盘缓冲 | Broker 持久化，天然抗流量洪峰 |
| 多消费方 | 一份文件被多个采集器各读一遍 | 一份消息多消费组各取所需（OSS / 实时计算 / 告警） |
| 运维 | 只需 Vector | 多一套 Kafka 集群 |
| 适用 | 主机/容器日志 | 业务埋点、需要解耦与重放的数据管道 |

## 常见运维

```bash
# 查看 Vector 日志
podman compose logs -f vector

# 消费组 lag（堆积监控）
podman compose exec kafka /opt/kafka/bin/kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 --describe --group vector-oss

# 手动造一条消息验证全链路
podman compose exec kafka /opt/kafka/bin/kafka-console-producer.sh \
  --bootstrap-server localhost:9092 --topic app-logs

# 控制台消费观察原始消息
podman compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic app-logs --from-beginning

# 重放：改 vector.yaml 的 group_id（如 vector-oss-replay-$(date +%s)）后重启 vector
podman compose up -d --force-recreate vector
```

## 故障排查

| 现象 | 排查 |
|------|------|
| `NoBrokersAvailable` / 连不上 | `bootstrap_servers` 写错；容器网络内要用服务名 `kafka:9092` 而非 `localhost` |
| 连上但不消费 | `advertised_listeners` 配置错误（客户端拿到的 broker 地址不可达）；宿主机访问用 `localhost:9094` |
| 无消息产出 | producer 未就绪或 topic 未建，看 `podman compose logs kafka-init producer` |
| 消费 lag 持续增长 | 分区数不够或单实例吞吐不足：加分区 + 加 Vector 实例；监控可用 `metrics.topic_lag_metric: true` 暴露 `kafka_consumer_lag` 指标 |
| 频繁 rebalance | Vector 处理慢导致心跳超时，调大 `session_timeout_ms`，或检查 sink 阻塞 |
| 消息重复 | at-least-once 语义正常现象（崩溃后重放未提交批次）；下游按 `.topic/.partition/.offset` 幂等去重 |
| 超大消息被丢 | librdkafka 单条上限 `message.max.bytes`（broker）与 `receive.message.max.bytes`（客户端），用 `librdkafka_options` 透传调大 |
| `NoSuchBucket` / 403 | OSS 侧问题，见 [vector2oss/README.md](../../vector2oss/README.md) |
