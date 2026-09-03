# Vector 采集 RabbitMQ 日志 + 指标

对应 Better Stack config [`rabbitmq_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [rabbitmq](../rabbitmq/) 日志采集基础上增加指标采集。

## 拓扑

```
                     ┌─ logs/rabbitmq.log ── file source ──> 解析 ───────────┐
client ──> rabbitmq ─┤                                                     ├─> ./output/*.ndjson
                     └─ :15692/metrics ── prometheus_scrape ──> tag_metrics ┘
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\rabbitmq-metrics.ndjson -Tail 5
```

## 要点

- RabbitMQ 3.8+ 内置 `rabbitmq_prometheus` 插件（默认启用），`:15692/metrics` 直接暴露，无需 exporter
- 典型指标：`rabbitmq_queue_messages_ready`、`rabbitmq_channel_consumers`、`rabbitmq_process_open_fds`、`rabbitmq_connections_opened_total`
- 指标带 `tags`（本演示加 `service`/`namespace`）
- 日志部分要点同 [`../rabbitmq/#要点`](../rabbitmq/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink，取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/rabbitmq_with_metrics/$SOURCE_TOKEN"
```
