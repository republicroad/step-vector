# Vector 采集 PostgreSQL 日志

对应 Better Stack config [`postgresql`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(psql 循环) ──> postgres ──> logs/postgresql.log (logging_collector)
                                        │
                             vector: file source
                                        │
                          正则解析 + 多行合并(语句换行)
                                        │
                        ./output/postgresql-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\postgresql.ndjson -Tail 5
```

## 要点

- `logging_collector=on` + `log_directory` 把 stderr 日志改写文件；`log_statement=all` + `log_min_duration_statement=0` 让每条 SQL 都进日志（生产按需放宽）
- 单条记录可能因 SQL 多行而跨多行，source 端 `multiline.mode: halt_before` 以 `2026-09-03 ` 日期开头为界合并
- 正则兼容两种行格式：无会话上下文（`[75] LOG:`）与带会话（`[75] demo@demo LOG:`），后者拆出 `user` / `database`
- Linux 裸机部署时日志通常在 `/var/log/postgresql/`，注意目录属主为 postgres 用户（容器演示里 Windows bind mount 无此问题）

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/postgresql/$SOURCE_TOKEN"
```
