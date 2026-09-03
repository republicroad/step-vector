# Vector 采集 auth.log (登录/提权审计)

对应 Better Stack config [`auth_log`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
log-gen(模拟 sshd/sudo/cron) ──> logs/auth.log
                                        │
                             vector: file source
                                        │
                  syslog 头解析 + 按事件类型分支解析(auth_failure/success/sudo/cron...)
                                        │
                            ./output/auth-YYYYMMDD.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\auth.ndjson -Tail 5
```

## 要点

- `/var/log/auth.log` 是 Linux 登录审计核心（sshd/sudo/su/cron/systemd-logind）；容器里无法真实产生，用 `gen-log.py` 模拟（35% 暴力破解失败、20% 成功登录、sudo 提权、cron、会话事件）
- 演示 VRL 分支解析模式：先解析 syslog 头（时间/主机/程序/pid），再按消息前缀依次尝试 5 种事件正则，命中后打上 `event` 标签并拆出 `user` / `src_ip` / `command` 等字段
- syslog 时间无年份且日期为空格补位（`Sep  3`），先 `replace` 补零再 `parse_timestamp("%b %d %H:%M:%S")`（chrono 不支持 `%e`）
- **生产环境**：`include` 改为宿主机路径 `/var/log/auth.log`（bind mount 或直接部署 Vector），无需改动解析逻辑

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/auth_log/$SOURCE_TOKEN"
```
