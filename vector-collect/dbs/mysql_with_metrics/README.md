# Vector 采集 MySQL 日志 + 指标

对应 Better Stack config [`mysql_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [mysql](../mysql/) 日志采集基础上增加 Vector 原生 `mysql_metrics` 指标 source。

## 拓扑

```
                     ┌─ logs/{general,error,slow}.log ── file source ──> 解析 ──────────────┐
client ──> mysql ────┤                                                                    ├─> ./output/*.ndjson
                     └─ mysql-exporter (:9104/metrics) ── prometheus_scrape ──> tag_metrics ┘
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\mysql-metrics.ndjson -Tail 5
```

## 要点

- Vector **没有**原生 MySQL 指标 source，标准做法是 `prom/mysqld-exporter` 把 MySQL status/变量暴露为 Prometheus 格式，Vector 用 `prometheus_scrape` 拉取
- exporter 通过 `.my.cnf` 提供连接凭据（v0.15+ 不再支持 `DATA_SOURCE_NAME` 环境变量）
- 典型指标：`mysql_up`、`mysql_threads_connected`、`mysql_queries_total`、`mysql_slow_queries`、`mysql_buffer_pool_reads_total`
- 指标带 `tags`（本演示加 `service`/`namespace`），Better Stack 中可据此过滤与分组
- 日志部分要点同 [`../mysql/#要点`](../mysql/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink，取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/mysql_with_metrics/$SOURCE_TOKEN"
```
