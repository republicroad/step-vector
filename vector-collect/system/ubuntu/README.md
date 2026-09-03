# Vector 采集 Ubuntu 系统日志

对应 Better Stack config [`ubuntu?docker=false`](https://telemetry.betterstack.com/vector-yaml/ubuntu/$SOURCE_TOKEN?docker=false)（系统日志；需要容器日志看 [`ubuntu_with_docker`](../ubuntu_with_docker/)）。

## 拓扑

```
log-gen(模拟 systemd/kernel/sshd) ──> logs/syslog.log
                                             │
                                  vector: file source
                                             │
                                  syslog 正则解析 (host/program/pid)
                                             │
                                 ./output/ubuntu-YYYYMMND.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\ubuntu.ndjson -Tail 5
```

## 要点

- Better Stack 的 ubuntu 官方配置在真实主机上是 **journald + /var/log/syslog** 两个 source；容器里 journald 不可得，演示用 `gen-log.py` 生成 syslog 格式样例（kernel/systemd/sshd/logind/dhclient）
- syslog 日期为空格补位（`Sep  3`），`replace` 补零后解析（chrono 无 `%e`）；kernel 行没有 `[pid]`，正则可选匹配
- **真机部署**参考 `vector-host.yaml`：`journald` source 读 systemd 日志（`exclude_units` 排除 vector 自身防自反馈）+ file source 读 `/var/log/syslog`，transform 里按 `source_type` 区分归一化
- 需要 docker 容器日志时用 `docker_logs` source，见 [`../ubuntu_with_docker/`](../ubuntu_with_docker/)（对应官方 `?docker=true` 变体）

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/ubuntu/$SOURCE_TOKEN?docker=false"
```
