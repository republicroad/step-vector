# Vector 采集 Apache httpd 日志

对应 Better Stack config [`apache`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
traffic(curl 循环) ──> httpd ──> logs/{access_log,error_log}
                                      │
                            vector: file source
                                      │
                  parse_apache_log!(combined) / 正则(error)
                                      │
                      ./output/apache-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\apache.ndjson -Tail 5
```

## 要点

- `httpd.conf` 为最小化配置（只加载必需模块），关键是 `CustomLog logs/access_log combined`——官方镜像默认把日志软链到 stdout，这里显式写文件供 Vector tail
- `parse_apache_log!(.message, "combined")` 为 Vector 内置 Apache 解析函数，自动拆 `host/identity/user/timestamp/message/method/path/status/bytes/referrer/agent`
- `error_log` 行首时间格式为 `%a %b %d %H:%M:%S.%f %Y`（如 `Wed Sep 03 10:00:00.123456 2026`），用 `parse_timestamp` 转换
- `[module:level]` 拆成 `module`（如 core）与 `level`（如 error）两个字段

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/apache/$SOURCE_TOKEN"
```
