# Vector 采集 MongoDB 日志

对应 Better Stack config [`mongodb`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
client(mongosh 循环) ──> mongodb ──> logs/mongod.log (--logpath, JSON)
                                          │
                               vector: file source
                                          │
                        parse_json + 字段归一 (severity/component/attributes)
                                          │
                          ./output/mongodb-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\mongodb.ndjson -Tail 5
```

## 要点

- `--logpath` 让 mongod 写文件；MongoDB 4.4+ 日志天然是 JSON 行，`parse_json` 一步到位
- 归一化字段：`s` → `severity`（I/W/E/F/D）、`c` → `component`（NETWORK/STORAGE/COMMAND 等）、`ctx` → `context`、`attr` 整体保留为嵌套对象
- 时间在 `t.$date` 里（RFC3339 带毫秒与时区），`parse_timestamp(format: "%+")` 解析
- `client` 用 mongosh 循环 insert/find，产生 `SlowQuery`/连接类日志；生产可按需调 `--set-parameter logLevel`

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/mongodb/$SOURCE_TOKEN"
```
