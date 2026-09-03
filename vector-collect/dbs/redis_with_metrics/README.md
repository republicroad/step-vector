# Vector 采集 Redis 日志 + 指标

对应 Better Stack config [`redis_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [redis](../redis/) 日志采集基础上增加指标采集。

## 拓扑

```
                     ┌─ logs/redis.log ── file source ──> 解析 ─────────────┐
client ──> redis ────┤                                                    ├─> ./output/*.ndjson
                     └─ redis_exporter (:9121/metrics) ─ prometheus_scrape ┘
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\redis-metrics.ndjson -Tail 5
```

## 要点

- Vector **没有**原生 redis 指标 source，标准做法是 `oliver006/redis_exporter` 把 Redis `INFO` 暴露为 Prometheus 格式，Vector 用 `prometheus_scrape` 拉取
- 典型指标：`redis_up`、`redis_connected_clients`、`redis_memory_used_bytes`、`redis_commands_processed_total`、`redis_keyspace_hits/misses`
- 指标带 `tags`（本演示加 `service`/`namespace`）
- 日志部分要点同 [`../redis/#要点`](../redis/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink，取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/redis_with_metrics/$SOURCE_TOKEN"
```
