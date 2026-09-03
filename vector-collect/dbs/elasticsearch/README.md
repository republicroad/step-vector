# Vector 采集 Elasticsearch 日志

对应 Better Stack config [`elasticsearch`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(REST 写入循环) ──> elasticsearch ──> logs/docker-cluster.log (ES_LOG_STYLE=file)
                                                   │
                                        vector: file source
                                                   │
                              JSON 解析 + 8.x/7.x 文本格式兜底正则
                                                   │
                                  ./output/elasticsearch-YYYYMMND.ndjson + console
```

## 运行

```bash
podman compose up -d
# ES 启动约 1-2 分钟
podman compose logs -f vector
Get-Content output\elasticsearch.ndjson -Tail 5
```

## 要点

- **`ES_LOG_STYLE=file` 是关键**：ES 官方镜像默认 `console`（服务日志只走 stdout，`logs/` 下只有 gc.log），设为 `file` 才会写 `logs/docker-cluster.log` 供 Vector tail
- ES 8 文件日志为文本模式（`[时间][LEVEL][组件][节点] 消息`），transform 先 `parse_json`（兼容 stdout JSON 风格，字段 `@timestamp`/`log.level`/`log.logger`），失败退回文本正则——同一份配置兼容新旧版本与两种日志风格
- 日志文件按集群名命名（docker 默认 `docker-cluster.log`）；GC 日志（`gc.log*`）由 JVM 参数直接写同目录，不含服务日志
- 演示限制 512m 堆 + 单节点 + 关安全，仅为快速启动；生产参数按官方建议调整
- `client` 等 90 秒后循环 `PUT /demo/_doc`，让日志持续出现索引相关事件

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/elasticsearch/$SOURCE_TOKEN"
```
