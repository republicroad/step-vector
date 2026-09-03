# Vector 采集 Docker 容器日志

对应 Better Stack config [`docker`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
app1(JSON 行) ─┐
               ├─ 容器 stdout/stderr ──> vector: docker_logs source (Docker API)
app2(纯文本) ──┘                                │
                                  JSON 解析(app1) + 容器元数据
                                                │
                                  ./output/docker-YYYYMMND.ndjson
```

## 运行

```bash
podman compose up -d
Get-Content output\docker.ndjson -Tail 5
```

## 要点

- `docker_logs` source 直连 Docker API 读取**全部容器**的 stdout/stderr，无需逐个配文件路径；自动附加元数据：`container_name` / `container_id` / `image` / `labels` / `host` / `stream`
- 容器名以 `vector-collect-docker-app1-1` 等形式出现在 `container_name` 字段
- **自反馈循环**：console sink 的输出本身也是容器日志，会被 docker_logs 再次采回，所以本演示只用 file sink——这是 docker_logs + console 组合的经典坑
- **Podman 注意**（Windows Podman machine 实测踩坑）：
  1. **日志驱动**：Podman 默认 `journald`，其 Docker 兼容日志 API 读不到内容 → compose 已给 app 容器显式 `logging: driver: json-file`（Docker 默认即它，无副作用）
  2. **权限**：socket 属主 root，vector 镜像默认 uid 1000 连不上 → compose 已加 `user: "0"`
  3. **代理注入**：Podman 注入的 `HTTP_PROXY` 会劫持 UDS 请求报 Connection refused → compose 已清空
  4. **路径转换**：Windows 上 podman-compose 会把 socket 路径误转换为 `/mnt/c/var/run/docker.sock` 假路径 → compose 启动的 vector 连不上 socket。变通：compose 只起 app 容器，vector 手动启动（Linux Docker 无此问题）：
     ```powershell
     podman compose up -d app1 app2
     podman run -d --user 0 `
       -e HTTP_PROXY= -e http_proxy= -e HTTPS_PROXY= -e https_proxy= `
       -v ${PWD}\vector.yaml:/etc/vector/vector.yaml:ro `
       -v ${PWD}\output:/var/lib/vector/output `
       -v /var/run/docker.sock:/var/run/docker.sock:ro `
       timberio/vector:latest-alpine
     ```
  5. `exclude_containers` / `include_containers` 按**容器 ID 前缀**匹配（不是名字）；vector 也会自动排除自身（"Excluded self container"）

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/docker/$SOURCE_TOKEN"
```
