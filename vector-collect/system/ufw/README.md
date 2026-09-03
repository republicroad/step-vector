# Vector 采集 UFW 防火墙日志

对应 Better Stack config [`ufw`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 拓扑

```
log-gen(模拟 [UFW BLOCK]/[UFW ALLOW]) ──> logs/ufw.log
                                                 │
                                      vector: file source
                                                 │
                        syslog 头解析 + iptables 字段正则 (SRC/DST/PROTO/DPT)
                                                 │
                                  ./output/ufw-YYYYMMND.ndjson + console
```

## 运行

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\ufw.ndjson -Tail 5
```

## 要点

- UFW 的拦截记录由内核 netfilter 打出（`[UFW BLOCK]` / `[UFW ALLOW]`），最终落在 syslog 或独立 `/var/log/ufw.log`；容器里无法产生，用 `gen-log.py` 模拟（80% BLOCK，重点打 23/3306/6379 等敏感端口，模拟扫描与爆破）
- 两段式解析：syslog 头（时间/主机）→ `[UFW 动作]` + iptables k=v 字段，产出 `event`（`firewall_block`/`firewall_allow`）、`src_ip`、`dst_ip`、`proto`、`dst_port`
- 演示 `slice!(.message, n)` 剥离已消费前缀再二次解析的技巧；`action` 小写化便于聚合统计
- **生产环境**：确认 `/etc/ufw/ufw.conf` 中 `LOGLEVEL` 与 rsyslog 规则把 kernel 日志写入 `/var/log/ufw.log`，`include` 指向该文件即可

## 切 Better Stack

`vector.yaml` 取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/ufw/$SOURCE_TOKEN"
```
