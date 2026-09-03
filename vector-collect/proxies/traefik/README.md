# Vector 采集 Traefik 日志

对应 Better Stack config [`traefik`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
traffic(curl 循环) ──> traefik ──> whoami
                       │
                       ├─ logs/access.log  (JSON, --accesslog.format=json)
                       └─ logs/traefik.log (zerolog 文本)
                              │
                     vector: file source ×2
                              │
                  parse_json(access) / 正则(main)
                              │
                  ./output/traefik-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\traefik.ndjson -Tail 5
```

## 要点

- access 日志开启 `--accesslog.format=json` 后是结构化 JSON（`RequestAddr/RequestMethod/RequestPath/DownstreamStatus/Duration/StartUTC` 等），`parse_json` 直接展开
- 主日志为 zerolog 文本格式（`时间 级别 调用位置 消息`），用 `parse_regex` 拆 `level/caller`
- `dynamic.yml` 用文件提供者把所有请求路由到 `whoami`，`traffic` 持续打流量产生日志
- 生产环境 traefik 默认日志到 stdout，可改为 docker_logs source 采集，或如本例固定 `--log.filepath` / `--accesslog.filepath` 落文件

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/traefik/$SOURCE_TOKEN"
```
