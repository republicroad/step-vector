# Vector 采集 Elasticsearch 日志 + 指标

对应 Better Stack config [`elasticsearch_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [elasticsearch](../elasticsearch/) 日志采集基础上增加指标采集。

## 拓扑

```
                     ┌─ logs/docker-cluster.log ── file source ──> 解析 ─────┐
client ──> es:9200 ──┤                                                     ├─> ./output/*.ndjson
                     └─ es-exporter (:9114/metrics) ── prometheus_scrape ───┘
```

## 运行

```bash
podman compose up -d
# ES 启动约 1-2 分钟
podman compose logs -f vector
Get-Content output\elasticsearch-metrics.ndjson -Tail 5
```

## 要点

- ES 需 `ES_LOG_STYLE=file`（compose 已设）才会把服务日志写入 `logs/docker-cluster.log`
- Vector 无原生 ES 指标 source：`justwatch/elasticsearch_exporter`（`--es.all` 采集全部节点）把 `_nodes/stats` 暴露为 Prometheus 格式，Vector `prometheus_scrape` 拉取
- 典型指标：`elasticsearch_process_cpu_percent`、`elasticsearch_jvm_memory_used_bytes`、`elasticsearch_indices_docs`、`elasticsearch_thread_pool_queue_count`
- 指标带 `tags`（本演示加 `service`/`namespace`）
- 日志部分要点同 [`../elasticsearch/#要点`](../elasticsearch/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink，取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/elasticsearch_with_metrics/$SOURCE_TOKEN"
```
