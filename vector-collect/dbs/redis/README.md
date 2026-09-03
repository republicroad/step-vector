# Vector 采集 Redis 日志

对应 Better Stack config [`redis`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(redis-cli 循环) ──> redis ──> logs/redis.log (--logfile)
                                         │
                              vector: file source
                                         │
                          正则解析 (pid/role/level/时间)
                                         │
                          ./output/redis-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\redis.ndjson -Tail 5
```

## 要点

- `--logfile /var/log/redis/redis.log` 让 Redis 写文件（默认 stdout）；Redis 自身日志以连接/持久化/复制事件为主，`client` 的读写会让日志里出现连接建立记录
- Redis 日志级别用符号表示：`*` notice、`#` warning、`-` error，transform 里转成可读字符串
- 时间格式特殊（`03 Sep 2026 10:00:00.123`），用 `parse_timestamp(format: "%d %b %Y %H:%M:%S%.3f")`
- `role` 字段：M=master、S=slave、C=RDB 写入子进程、X=AOF/模块子进程

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/redis/$SOURCE_TOKEN"
```
