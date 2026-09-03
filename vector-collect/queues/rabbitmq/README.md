# Vector 采集 RabbitMQ 日志

对应 Better Stack config [`rabbitmq`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(management API 循环) ──> rabbitmq ──> logs/rabbitmq.log (RABBITMQ_LOGS)
                                                   │
                                        vector: file source
                                                   │
                                  正则解析 (时间/级别/erlang pid)
                                                   │
                                  ./output/rabbitmq-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\rabbitmq.ndjson -Tail 5
```

## 要点

- 官方镜像默认日志到 stdout；`RABBITMQ_LOGS=/var/log/rabbitmq/rabbitmq.log` 改为写文件（演示用途）
- RabbitMQ 日志格式为 Erlang 风格：ISO8601 时间 + `[级别]` + 可选 `<erlang pid>` + 消息；部分系统行没有 pid，正则已兼容
- `client` 通过 management API (15672) 循环声明/删除队列，产生连接、channel、数据库事件日志
- 级别：debug/info/warning/error；生产环境建议 `log.file.level = info`

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/rabbitmq/$SOURCE_TOKEN"
```
