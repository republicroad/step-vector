# Vector 采集 PostgreSQL 日志 + 指标

对应 Better Stack config [`postgresql_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [postgresql](../postgresql/) 日志采集基础上增加 Vector 原生 `postgresql_metrics` 指标 source。

## 拓扑

```
                     ┌─ logs/postgresql.log ── file source ──> 解析 ─────────┐
client ──> postgres ─┤                                                      ├─> ./output/*.ndjson
                     └─ postgres:5432 ── postgresql_metrics ──> tag_metrics ┘
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\postgresql-metrics.ndjson -Tail 5
```

## 要点

- `postgresql_metrics` 为 Vector 原生指标 source：采集 `pg_locks_*`、`pg_db_*`（事务/块读写/回滚）、`pg_replication_*` 等指标；`databases: [demo]` 限定采集范围
- 指标带 `tags`（本演示加 `service`/`namespace`）
- 日志部分要点同 [`../postgresql/#要点`](../postgresql/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink，取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/postgresql_with_metrics/$SOURCE_TOKEN"
```
