# Vector K8s 日志采集 → 阿里云 OSS

使用 [Vector](https://vector.dev) 以 **DaemonSet 节点级采集** 模式，在 K8s 集群中收集所有容器的标准输出（stdout/stderr），写入阿里云 OSS（`aws_s3` sink，OSS 兼容 S3 API）。支持 JSON + Parquet 双输出。

## 目录结构

```
source/k8s/
├── values.yaml              # Vector Helm chart 基线配置
├── values.cluster-a.yaml    # 集群 overlay 示例（每个集群一份）
└── README.md                # 本文档
```

## 架构

```
┌───────────── 节点 ──────────────┐
│                                 │
│  ┌──────────┐  ┌──────────┐    │
│  │ Pod A    │  │ Pod B    │    │
│  │ stdout   │  │ stdout   │    │
│  └────┬─────┘  └────┬─────┘    │
│       │              │          │
│       ▼              ▼          │
│  /var/log/pods/.../0.log  ← CRI 写入（containerd 格式）
│       │                         │
│       ▼                         │
│  ┌──────────────────────────┐   │
│  │ Vector DaemonSet Pod     │   │
│  │  kubernetes_logs source  │   │
│  │  → parse (JSON)          │   │
│  │  → partition (时间分区)  │   │
│  │  → route (有效/无效分流) │   │
│  └────┬──────────┬──────────┘   │
│       │          │              │
└───────┼──────────┼──────────────┘
        │          │
        ▼          ▼
   aliyun_oss   aliyun_oss_parquet    ← 不同地域 Bucket 用 overlay 覆盖
   (JSON gzip)  (Parquet snappy)

                    ┌─────────────────┐
                    │ 额外：logtail   │ ← ACK 自带，可选开启
                    │ SLS 热查询      │    用于秒级风控判定
                    └─────────────────┘
```

## 快速开始

```bash
# 1. 添加 Helm repo
helm repo add vector https://helm.vector.dev
helm repo update

# 2. 创建密钥 Secret（复用 vector2oss 的 oss-secrets.json）
kubectl -n vector create secret generic vector-oss-secrets \
  --from-file=oss-secrets.json=../../vector2oss/secrets/oss-secrets.json

# 3. 安装（以 cluster-a 为例）
helm upgrade --install vector vector/vector \
  -n vector --create-namespace \
  -f values.yaml -f values.cluster-a.yaml

# 4. 验证
kubectl -n vector logs -l app.kubernetes.io/name=vector -f
# 在某个业务 Pod 里 echo 一条 JSON 日志：
kubectl exec -it <pod> -- sh -c \
  'echo "{\"trace_id\":\"test-001\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"ip\":\"1.2.3.4\",\"tenant_id\":\"t1\",\"service_id\":\"s1\",\"msg\":\"hello\"}" >> /dev/stdout'
# OSS 控制台确认 log_json/year=.../ 路径下出现对象
```

## 两种采集模式对比

### 节点级采集（DaemonSet，本方案）

| 维度 | 说明 |
|------|------|
| 部署 | 每节点一个 Vector Pod，挂载宿主 `/var/log` |
| 采集范围 | 该节点上**所有容器**的 stdout/stderr |
| 运行时感知 | 不需要；CRI 自动把 stdout 写到 `/var/log/pods`，Vector 直接读文件 |
| 元数据 | 通过 K8s API watch Pod，自动富化 `kubernetes.pod_name/namespace/container_name/...` |
| RBAC | 需要 ClusterRole：`pods`、`namespaces` 的 get/list/watch |
| 资源开销 | 每节点一个 Vector 进程，200m CPU / 256Mi 内存 |
| 适用 | **通用日志采集**、全局可观测性、埋点数据收集 |

**优点**：
- 运维简单：装一次 DaemonSet，所有节点、所有 Pod 都被采集，业务 Pod 不用改任何配置
- 无侵入：业务 Pod 不需要安装 sidecar、不需要声明 volume、不需要改镜像
- 运行时无关：Docker / containerd / CRI-O 均可，只读 `/var/log/pods`

**缺点**：
- 粒度粗：一个节点的所有容器日志混在一起，想只采集某个容器必须按 label/container_name 过滤
- 无法读取容器内文件（非 stdout）：日志必须写到 stdout，或 sidecar tail 转发

### Pod 级采集（Sidecar 注入）

| 维度 | 说明 |
|------|------|
| 部署 | 每个业务 Pod 旁边注入一个 Vector sidecar 容器 |
| 采集范围 | 该 Pod 内指定容器的日志/文件 |
| 元数据 | 直接通过 Pod spec 注入环境变量，更精确 |
| RBAC | 不需要（sidecar 在 Pod 内，读共享卷即可） |
| 资源开销 | 每个 Pod 多一个 Vector 进程，总资源消耗随 Pod 数线性增长 |
| 适用 | 容器内文件日志、需要按租户/服务强隔离的场景 |

**优点**：
- 粒度细：每个 Pod 独立配置，可按租户/服务/团队做独立管道
- 能读容器内文件：emptyDir 共享卷 + tail，绕开 stdout 限制

**缺点**：
- 运维成本高：需要 mutating webhook（如 MutatingAdmissionPolicy）或手动注入 sidecar
- 资源膨胀：100 个 Pod = 100 个 Vector sidecar，内存/CPU 开销不可忽略
- 版本升级：每个 sidecar 都要跟着升，或用 webhook 统一注入

### 选型建议

| 场景 | 推荐模式 |
|------|---------|
| 通用日志采集（99% 的情况） | **DaemonSet 节点级** ✅ |
| 多租户 SaaS 埋点 | DaemonSet（租户信息打在日志内容里） |
| 容器内文件日志，改不了应用 | DaemonSet + sidecar tail（emptyDir 转发到 stdout） |
| 需要按租户/服务独立管道 | Sidecar 注入 |
| 容器内数据库 WAL、监控采集 | Sidecar 注入 |

**本方案选择 DaemonSet 节点级**，因为：
1. 埋点数据（trace_id / tenant_id / service_id）已写在 JSON 内容中，不需要容器级隔离
2. 运维简单，一次部署覆盖全集群
3. 与 ACK 自带的 logtail 互不冲突（都读 `/var/log/pods`，共享只读挂载）

## 关键配置说明

### kubernetes_logs source

Vector 官方 K8s 采集源，专为 CRI（containerd）设计：

- 读 `/var/log/pods/` 下的 CRI 日志文件
- `auto_partial_merge: true` — CRI 分片行（`P` 标记）自动合并为完整 JSON 行
- `glob_minimum_cooldown_ms: 1000` — 新 Pod 日志文件发现间隔
- `max_line_bytes: 262144` — 防超长行被截断丢弃
- 自动排除 Vector 自身日志（`VECTOR_SELF_NODE_NAME` 由 chart 注入）

### JSON 解析与埋点识别

```vrl
# 有效性判断：带齐 trace_id/ts/tenant_id/service_id → 埋点
# 缺字段或非 JSON → 走 dead_letter 兜底
if !starts_with(.message, "{") { .valid = false }
else { parsed, err = parse_json(.message); ... }
```

- `merge!(., parsed)`：字段提升到顶层（parquet schema 推断需要）
- `.message = raw_line`：恢复原始 JSON 行（`raw_message` 编码输出原样）
- `parse_timestamp(.ts, "%+")`：RFC3339 → Vector 事件时间戳，分区用它

### OSS sink

OSS 兼容 S3 API，Vector 用 `aws_s3` sink 对接：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `endpoint` | `oss-{region}-internal.aliyuncs.com` | ACK 同地域走内网，流量免费 |
| `region` | Bucket 所在地域 | 必须一致，否则 `NoSuchBucket` |
| `force_path_style` | `false` | OSS 仅支持虚拟托管寻址 |
| `key_prefix` | `k8s/{{ cluster }}/log_json/...` | 按集群 + 分钟级 Hive 分区 |
| `compression` | `gzip` | JSON sink 使用 gzip |
| `encoding.codec` | `raw_message` | 对象内容 = 原始 JSON 行 |

### 内网 vs 公网 endpoint

| 场景 | endpoint | 说明 |
|------|----------|------|
| ACK 节点与 Bucket **同地域** | `oss-cn-shenzhen-internal.aliyuncs.com` | 内网免费，推荐 |
| ACK 节点与 Bucket **跨地域** | `oss-cn-shenzhen.aliyuncs.com` | 公网，外网流量计费 |
| 自建 K8s（IDC） | `oss-cn-shenzhen.aliyuncs.com` | 公网 |

### Parquet 输出

写法同 [vector2oss/README.md](../../vector2oss/README.md) 已验证配置：

```yaml
encoding:
  codec: json            # 占位，batch_encoding 接管
batch_encoding:
  codec: parquet
  schema_mode: auto_infer
  compression:
    algorithm: snappy
```

- Parquet 按小时聚合（无 minute 层），减少小文件
- 下游 Athena/EMR/DuckDB 分析可直接列裁剪（按 tenant_id / service_id 过滤）

## 多集群部署

```bash
# 集群 overlay 文件命名：values.<cluster-name>.yaml
# 每个集群只改三样：集群名、地域、endpoint

# cluster-a（华东-深圳）
helm upgrade --install vector vector/vector \
  -n vector --create-namespace \
  -f values.yaml -f values.cluster-a.yaml

# cluster-b（华北-北京）
cp values.cluster-a.yaml values.cluster-b.yaml
# 编辑 values.cluster-b.yaml:
#   VECTOR_CLUSTER_NAME=cluster-b
#   region=cn-beijing
#   endpoint=oss-cn-beijing-internal.aliyuncs.com
helm upgrade --install vector vector/vector \
  -n vector --create-namespace \
  -f values.yaml -f values.cluster-b.yaml
```

多集群写同一个 Bucket 时，`key_prefix` 里的 `{{ cluster }}` 层自动按集群分目录，下游按 `cluster` 谓词裁剪。

## 与 logtail / SLS 的关系

ACK 默认装了 `alibaba-log-controller`（logtail），它也在读 `/var/log/pods`：

| 组件 | 输出 | 用途 | 共存 |
|------|------|------|------|
| **Vector** (DaemonSet) | OSS | 冷数据湖：回测、特征、审计 | ✅ 本方案 |
| **logtail** (ACK 自带) | SLS | 热查询：秒级风控、告警、在线分析 | ✅ 可选开启 |

两者共享只读 `/var/log`，互不冲突。不需要 SLS 时关掉采集 CRD 即可。

### 何时开启 logtail

如果需要**秒级风控判定**（滑动窗口、序列模式匹配），Vector → OSS 路径延迟约 15~60s，不够快。此时开启 logtail → SLS：

1. SLS 建 logstore + 索引（index TTL 3~7 天控成本）
2. Flink 消费 SLS Consumer Group（延迟 1~3s）
3. 规则引擎命中 → Redis 黑名单 → 网关拦截

两条路并行：
- **SLS 热路径**：秒级风控、在线告警
- **OSS 冷路径**：分钟级回测、特征回填、长期归档

## data_dir 持久化

chart 默认用 `persistence.hostPath.enabled: true`，checkpoint 落节点盘 `/var/lib/vector`：

- Pod 重建 → 从 checkpoint 续读，不重读旧日志
- 节点磁盘满 → 风险低（日志是只读的，checkpoint 文件很小）
- 清空断点（重新全量读）：删除节点上 `/var/lib/vector/checkpoints/` 目录

## 常见运维

```bash
# 查看 Vector 日志
kubectl -n vector logs -l app.kubernetes.io/name=vector -f

# 验证 OSS 写入
# 在业务 Pod 里手动打一条测试日志：
kubectl exec -it <pod> -- sh -c \
  'echo "{\"trace_id\":\"debug-$(date +%s)\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"ip\":\"1.2.3.4\",\"tenant_id\":\"t1\",\"service_id\":\"s1\",\"msg\":\"test\"}" >> /dev/stdout'

# 热重载配置（不重启 Pod）
kubectl -n vector rollout restart daemonset/vector

# 查看 checkpoint 状态
kubectl -n vector exec -it <vector-pod> -- ls -la /vector-data-dir/checkpoints/
```

## 故障排查

| 现象 | 排查 |
|------|------|
| 无日志进 OSS | 检查 `kubectl -n vector logs` 是否有 `kubernetes_logs` 读取日志的 trace |
| `NoSuchBucket` | `region` 与 Bucket 不一致，或 endpoint 错误 |
| `403 Forbidden` | RAM AccessKey 权限不足，需 `oss:PutObject` |
| 超长日志行被丢 | 调大 `max_line_bytes`（默认 32KB → 已改为 256KB） |
| 兜底日志太多 | 业务 JSON 日志缺字段，联系业务补全 `trace_id/ts/tenant_id/service_id` |
