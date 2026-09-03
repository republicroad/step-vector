# Vector 采集 MySQL 日志

对应 Better Stack config [`mysql`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(mysql 查询循环) ──> mysql ──> logs/{general,error,slow}.log
                                         │
                              vector: file source ×3
                                         │
                     general/slow/error 各自 VRL 正则解析
                                         │
                         ./output/mysql-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\mysql.ndjson -Tail 5
```

## 要点

- MySQL 通过启动参数把三类日志落到 `/var/log/mysql/`：`--general-log`（全部连接/查询）、`--slow-query-log`、`--log-error`
- slow log 是多行记录（`# Time:` / `# User@Host:` / `# Query_time:` / SQL），source 端用 `multiline.mode: halt_before` 以 `# Time:` 为界合并成单事件
- `client` 服务用 mysql 客户端循环执行 `SELECT SLEEP(1)`，同时演示 general log 的 Connect/Query 记录与 slow log 的慢查询（>1s 阈值时才记录；可在 mysql command 中加 `--long-query-time=0.5` 调整）
- 生产环境（Linux 裸机/VM）日志路径通常为 `/var/log/mysql/`，与本配置一致

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/mysql/$SOURCE_TOKEN"
```
