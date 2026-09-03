# Vector 采集 HAProxy 日志

对应 Better Stack config [`haproxy`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
traffic(curl 循环) ──> haproxy ──syslog(UDP)──> vector: syslog source :1514
                                                     │
                                          正则解析 HTTP 请求字段
                                                     │
                                      ./output/haproxy-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\haproxy.ndjson -Tail 5
```

## 要点

- `haproxy.cfg` 中 `log vector:1514 local0` 把请求日志以 syslog (RFC3164) 直接发到 compose 网络内的 Vector，无需日志文件中转
- `syslog` source 自动解析 RFC3164/5424 头部：`hostname` / `appname` / `facility` / `severity` / `timestamp`
- 剩余的 haproxy HTTP 日志体用 `parse_regex` 拆出 `client_ip_port / request_date / event / backend / server / status / bytes_read`
- `http-request return` 让 haproxy 自己充当响应端，演示无需额外后端服务
- 生产环境若 haproxy 写 `/var/log/haproxy.log`（rsyslog 落盘），把 source 换回 `file` 即可，与 Better Stack 官方配置一致

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/haproxy/$SOURCE_TOKEN"
```
