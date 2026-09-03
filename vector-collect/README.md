# vector-collect — Better Stack Vector 全套采集演示

对应 Better Stack 文档 [Send logs and metrics to Better Stack using Vector → Available configs](https://betterstack.com/docs/logs/vector/#available-configs) 中列出的全部 20+ 个现成配置。每个子目录是一个独立的端到端采集演示：**容器化真实服务产生日志 → Vector 采集/解析 → 本地文件落地**（无需 Better Stack token，离线可跑通），每个 `vector.yaml` 内附注释好的 Better Stack 官方 sink 块，取消注释并填入 `SOURCE_TOKEN` / `INGESTING_HOST` 即可切换为推送 Better Stack。

## 目录对照表

| 分类 | 目录 | 文档 config | Vector source | 解析 |
|------|------|-------------|---------------|------|
| DBs | `dbs/mysql/` | `mysql` | `file` | VRL 正则 |
| DBs | `dbs/mysql_with_metrics/` | `mysql_with_metrics` | `file` + `prometheus_scrape` (mysqld-exporter) | VRL 正则 |
| DBs | `dbs/postgresql/` | `postgresql` | `file` | VRL 正则 |
| DBs | `dbs/postgresql_with_metrics/` | `postgresql_with_metrics` | `file` + `postgresql_metrics`（原生） | VRL 正则 |
| DBs | `dbs/mongodb/` | `mongodb` | `file` | `parse_json`（4.4+ 结构化日志） |
| DBs | `dbs/redis/` | `redis` | `file` | VRL 正则 |
| DBs | `dbs/redis_with_metrics/` | `redis_with_metrics` | `file` + `prometheus_scrape` | VRL 正则 |
| DBs | `dbs/elasticsearch/` | `elasticsearch` | `file` | VRL 正则 |
| DBs | `dbs/elasticsearch_with_metrics/` | `elasticsearch_with_metrics` | `file` + `prometheus_scrape` | VRL 正则 |
| Queues | `queues/rabbitmq/` | `rabbitmq` | `file` | VRL 正则 |
| Queues | `queues/rabbitmq_with_metrics/` | `rabbitmq_with_metrics` | `file` + `prometheus_scrape` | VRL 正则 |
| Webservers | `webservers/apache/` | `apache` | `file` | `parse_apache_log!` |
| Webservers | `webservers/nginx/` | `nginx` | `file` | `parse_nginx_log!` |
| Proxies | `proxies/haproxy/` | `haproxy` | `syslog` (UDP) | syslog 协议解析 |
| Proxies | `proxies/traefik/` | `traefik` | `file` | `parse_json` |
| Proxies | `proxies/traefik_with_metrics/` | `traefik_with_metrics` | `file` + `prometheus_scrape` | `parse_json` |
| System | `system/auth_log/` | `auth_log` | `file`（gen-log.py 生成样例） | VRL 正则 |
| System | `system/docker/` | `docker` | `docker_logs` | — |
| System | `system/kubernetes/` | `kubernetes` | `kubernetes_logs`（+ `k8s/` 真集群清单） | CRI/docker 日志格式 |
| System | `system/ubuntu/` | `ubuntu?docker=false` | `file`（gen-log.py 生成样例） | syslog 正则 |
| System | `system/ubuntu_with_docker/` | `ubuntu?docker=true` | `file` + `docker_logs` | syslog 正则 |
| System | `system/ufw/` | `ufw` | `file`（gen-log.py 生成样例） | UFW 正则 |

> 与文档的差异说明：文档中的官方配置 sink 直接推送 Better Stack；本演示把 sink 换成本地 `file` + `console`（每个 `vector.yaml` 中均保留注释的 `better_stack` sink 块）。`*_with_metrics` 系列优先使用 Vector 原生指标 source（`postgresql_metrics`），无原生支持的（mysql / redis / elasticsearch）通过 exporter、服务自带 `/metrics`（rabbitmq / traefik）用 `prometheus_scrape` 采集。haproxy 官方配置用 `file` source 读 `/var/log/haproxy.log`，容器演示改用 `syslog` source 接收 haproxy 的 syslog 输出（生产上更常见）。

## 每个目录的结构

```
<service>/
├── compose.yaml    # 服务容器（产生日志）+ vector（采集）
├── vector.yaml     # source + transform(解析) + sink(本地 file/console + 注释的 better_stack)
├── gen-log.py      # 仅 system 类（auth_log/ufw/ubuntu/kubernetes 模拟）需要
├── *.conf/ *.yml   # 服务配置（nginx/httpd/haproxy/traefik/rabbitmq）
├── k8s/            # 仅 kubernetes/：真集群 DaemonSet 清单
└── output/         # 采集结果（.gitignore 已忽略），验证用
```

## 快速开始

```bash
cd vector-collect/webservers/nginx

podman compose up -d          # 或 docker compose up -d
podman compose logs -f vector # console sink 实时看解析结果

# 采集结果落地在 ./output/*.ndjson（JSON lines）
Get-Content output\nginx.ndjson -Wait -Tail 20   # PowerShell
tail -f output/nginx.ndjson                      # bash

podman compose down           # 停止（不清 output）
```

## 切换为推送 Better Stack

每个 `vector.yaml` 的 `sinks:` 段内都有注释的 `better_stack` sink，取消注释并：

```bash
export SOURCE_TOKEN="你的 Better Stack source token"
export INGESTING_HOST="你的 source ingesting host，如 in.logtail.com"
```

也可直接用文档的官方安装脚本下载完整配置（需要 token）：

```bash
curl -o /etc/vector/vector.yaml "https://telemetry.betterstack.com/vector-yaml/<config>/$SOURCE_TOKEN"
```

`<config>` 取值见上方对照表的「文档 config」列。

## 通用说明

- **镜像**：`timberio/vector:latest-alpine`；各服务均为官方镜像（注意 mysql/mongodb/elasticsearch 镜像较大，elasticsearch 限制 512m 堆）
- **断点**：`file` source 的 checkpoint 存于命名卷 `vector-data`，`compose down` 不丢；删除卷可重放
- **端口**：所有服务仅容器网络内部访问，不映射宿主机端口（避免冲突），需要的话自行加 `ports:`
- **环境**：Podman 6.x / podman-compose 1.6（Windows），Docker Compose 同样可用
- **时区**：容器统一 `TZ: Asia/Shanghai`
- **代理坑（重要）**：Podman 会把宿主机代理变量注入容器，容器间 HTTP 流量（traffic 打流、`prometheus_scrape`、exporter 抓取）会被代理劫持导致 502/超时。所有涉及容器间 HTTP 的服务（traffic/client/vector/exporter）都已加 `NO_PROXY: "*"`；自己改造时务必保留
