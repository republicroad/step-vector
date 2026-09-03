# Vector 采集 Traefik 日志 + 指标

对应 Better Stack config [`traefik_with_metrics`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。在 [traefik](../traefik/) 日志采集基础上增加 Prometheus 指标。

## 拓扑

```
                     ┌─ logs/{access,traefik}.log ── file source ──> 解析 ──┐
traffic ──> traefik ─┤                                                     ├─> ./output/*.ndjson
                     └─ :8080/metrics ── prometheus_scrape ──> tag_metrics ┘
                └──> whoami
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector          # 日志事件
podman compose logs -f vector 2>&1 | Select-String 'traefik_'   # 指标事件
Get-Content output\traefik-metrics.ndjson -Tail 5
```

## 要点

- Traefik 内置 Prometheus 端点：`--metrics.prometheus=true` 即可在内部 entrypoint `:8080/metrics` 暴露指标，无需 exporter；Vector 用 `prometheus_scrape` 主动拉取
- 日志与指标是两类事件，分别路由到 `local_file` / `local_metrics_file` 两个 sink
- `tag_metrics` transform 给指标加 `tags.service` / `tags.namespace`，对应 Better Stack 配置里 metric sink 的 tag 惯例
- 典型指标：`traefik_entrypoint_requests_total`、`traefik_service_request_duration_seconds_*` 等
- README 其余要点同 [`../traefik/`](../traefik/#要点)

## 切 Better Stack

`vector.yaml` 中注释了 `better_stack` 与 `better_stack_metrics` 两个 sink（对应官方配置中日志/指标分流的 `*_http_metrics_sink` 结构），取消注释并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/traefik_with_metrics/$SOURCE_TOKEN"
```
