# Vector 采集 nginx 日志

对应 Better Stack config [`nginx`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
traffic(curl 循环) ──> nginx ──> /var/log/nginx/{access,error}.log
                                       │
                              vector: file source
                                       │
                    parse_nginx_log!(combined) / 正则(error)
                                       │
                        ./output/nginx-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector      # console sink 实时查看
Get-Content output\nginx.ndjson -Tail 5
```

## 要点

- 官方 nginx 镜像把 `/var/log/nginx/*.log` 做成指向 `/dev/stdout` 的软链；这里用 `./logs` bind mount 覆盖该目录，nginx 会创建真实文件，Vector 才能 tail
- `parse_nginx_log!(.message, "combined")` 是 Vector 内置的 nginx 访问日志解析函数（另有 `"common"` / `"error"` 格式），自动拆出 `host/method/path/status/bytes/referer/agent`
- `error.log` 用 `parse_regex` 提取 level/pid/连接 id；time 转为 timestamp 类型
- `traffic` 服务每 2 秒发 3 个请求（200/404/带 referer 的自定义 UA），保证持续有日志

## 切 Better Stack

`vector.yaml` 中取消注释 `better_stack` sink，设置 `SOURCE_TOKEN` / `INGESTING_HOST` 后重启；或直接用官方配置：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/nginx/$SOURCE_TOKEN"
```
