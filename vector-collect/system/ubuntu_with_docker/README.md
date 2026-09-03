# Vector 采集 Ubuntu 系统日志 + Docker 容器日志

对应 Better Stack config [`ubuntu?docker=true`](https://telemetry.betterstack.com/vector-yaml/ubuntu/$SOURCE_TOKEN?docker=true)。在 [ubuntu](../ubuntu/) 系统日志基础上叠加 `docker_logs`——即官方配置 `docker=true` 与 `docker=false` 变体的差异所在。

## 拓扑

```
log-gen ──> logs/syslog.log ── file source ──> 解析 ──┬─> ./output/ubuntu-*.ndjson + console
                                                      │
app(容器负载) ── docker_logs source ──────────────────┴─> ./output/ubuntu-docker-*.ndjson (仅 file)
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector          # 只看 syslog 事件
Get-Content output\ubuntu-docker.ndjson -Tail 5   # 容器日志事件
```

## 要点

- 与 `ubuntu?docker=false` 的唯一区别：多一个 `docker_logs` source + 挂载 docker 兼容 socket——对应官方安装脚本中 `?docker=true` 会追加容器日志采集
- **Windows Podman 坑**（详见 [`system/docker/README`](../docker/README.md#要点)）：app 容器已显式 `logging: driver: json-file`（Podman 默认 journald 的兼容 API 读不到日志）、vector 以 `user: "0"` 运行并清空代理变量；Windows 上 podman-compose 会把 socket 路径误转成 `/mnt/c/...`，vector 需按 docker 目录 README 的手动命令启动
- **自反馈循环**：console sink 的输出也是容器日志会被 docker_logs 采回，所以 docker 事件只路由到 file sink——docker_logs + console 组合的经典坑
- 系统日志部分要点同 [`../ubuntu/#要点`](../ubuntu/#要点)

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/ubuntu/$SOURCE_TOKEN?docker=true"
```
