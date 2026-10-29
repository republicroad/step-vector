# Vector K8s 日志采集 → 阿里云 OSS（手写 ConfigMap 形态）

> 背景：使用 [Vector](https://vector.dev) 以 DaemonSet 节点级采集模式收集容器 stdout/stderr，校验通用事件字段（`user/ts/event`）后写入阿里云 OSS（`aws_s3` sink，Hive 分区 JSON gzip）；覆盖 Helm / ConfigMap / DaemonSet 三层的安装、部署与配置变更流程。
> 场景与结论：适用于 ACK/containerd 生产与实验集群；形态为 **Helm 装软件、配置不进模板**——Helm 只渲染工作负载，Vector 配置本体是手写 ConfigMap 清单（`vector-cm.yaml`），`kubectl apply -f` 逐字落地；坑位对照见 [CM_BEST_PRACTICES.md](CM_BEST_PRACTICES.md)。

## 架构

```text
┌───────────── 节点 ──────────────┐
│  Pod stdout/stderr              │
│    ↓ CRI 写入                   │
│  /var/log/pods/.../0.log        │
│    ↓                            │
│  Vector DaemonSet Pod           │
│    kubernetes_logs source       │
│    → parse (JSON + 字段校验)    │
│    → partition (年/月/日/时)    │
│    → route (valid / bad)        │
└───────┬──────────┬──────────────┘
        ↓          ↓
  track/…       track_bad/…     ← OSS(Hive 分区 JSON gzip)
  有效事件       违约隔离
        ↓
  非事件行 → stderr(dead_letter)  ← 不进 OSS
```

## 三个概念卡（先读这个）

### Helm —— 管「装」

- 把工作负载（DaemonSet/ServiceAccount）从 chart 模板 + values **渲染**成真实资源
- **只管装与升级工作负载；Vector 配置不在这里**（见 ConfigMap 卡）
- 版本必须锁定：`--version 0.51.0`（chart ≥0.52 要求 K8s ≥1.28，老集群被拒）+ 镜像 tag 固定 + 国内加速前缀（节点直连 docker.io 超时）

### ConfigMap —— 管「配置本体」

- `vector-cm.yaml` 手写多文档清单：`vector-common`（数据键 `10-common.yaml`）+ `vector-oss`（数据键 `20-oss.yaml`）
- `--config-dir /etc/vector/` 按**文件名字典序**加载合并（10- 在前 20- 在后，同名键后者覆盖）
- **静态 CM 名不自动生效**：`apply -f` 后必须 `rollout restart`（最常漏的一步）
- **零转义**：`{{ }}`（Vector 运行时模板）与 VRL 在数据段原样直写，不经任何渲染

### DaemonSet —— 管「跑在哪」

- 每节点一个副本，全节点覆盖；污点容忍缺失 = 该节点**静默无 agent**
- hostPath `/var/lib/vector` 存 checkpoint + 磁盘 buffer：Pod 重建断点续采不丢不重
- `kubernetes_logs` 依赖集群级只读 RBAC（pods/namespaces/nodes 的 get/list/watch），未授权 = 零事件

## 目录结构

```text
source/k8s/
├── vector-cm.yaml               # 手写 ConfigMap 多文档清单（配置本体；apply -f 管理）
├── values.yaml                  # chart 层基线（existingConfigMaps 模式 + 版本锁定 + Secret 目录挂载）
├── values.cluster-a.yaml        # 集群 overlay（env 实参：bucket/region/endpoint/cluster 名 + 插值开关）
├── CM_BEST_PRACTICES.md         # ★ 最佳实践：两形态对照 + 八条纪律 + 坑位对照
└── README.md                    # 本文档
```

## 安装（首次，三步）

```bash
# 1) 配置就位：两 CM 一次全建（清单零实参，直接用仓库文件）
kubectl apply -f vector-cm.yaml -n vector --create-namespace

# 2) 凭证就位：OSS AK/SK 走 Secret 目录挂载（真值文件放仓库外，严禁入仓）
kubectl -n vector create secret generic vector-oss-secrets \
  --from-file=oss-secrets.json=<仓库外真值文件>

# 3) 安装工作负载（版本锁定 + overlay 注入 env 实参）
helm repo add vector https://helm.vector.dev && helm repo update
helm upgrade --install vector vector/vector --version 0.51.0 \
  -n vector --create-namespace \
  -f values.yaml -f values.cluster-a.yaml

# 验证：全节点 Running + Healthcheck passed + OSS 出对象
kubectl -n vector get pods -l app.kubernetes.io/name=vector -o wide
kubectl -n vector logs -l app.kubernetes.io/name=vector --tail=50   # Healthcheck passed, 无 ERROR
```

事件样例（三行分别命中三条路由）：

```text
{"user":"u1","event":"page_view","event_version":2,"ts":"2026-10-29T08:00:00.000Z"}            # 有效 → track/event_version=2/
{"event":"page_view","event_version":2,"ts":"2026-10-29T08:00:00.000Z"}                        # 缺 user，有特征 → track_bad/
{"user":"u1","ts":"2026-10-29T08:00:00.000Z"}                                                  # 缺 event_version → 兜底补 1 → track/event_version=1/
```

## 配置变更管理（两条路径，先判断改的是哪层）

| 改什么 | 命令序列 | 滚动方式 |
|---|---|---|
| **应用配置**（CM 数据段：parse/route/sink 逻辑） | 改 `vector-cm.yaml` → `vector validate` → `apply -f` → **手动** `rollout restart` | 手动（静态 CM 名不自动生效） |
| **实参**（bucket/region/endpoint/cluster 名） | 改 `values.cluster-a.yaml` → `helm upgrade … -f values.yaml -f values.cluster-a.yaml` | **自动**（env 在 Pod 模板里） |
| 两层都改 | 先 apply（CM 先就位）→ 再 helm upgrade | helm upgrade 那次滚动同时带上新 CM |

```bash
# 应用配置变更：
vector validate …                              # 变更前必做；含 ${VAR} 时本地带 dummy env
PROD_BUCKET=d PROD_REGION=d OSS_ENDPOINT=https://d.aliyuncs.com vector validate <提取的数据段>
kubectl apply -f vector-cm.yaml -n vector
kubectl -n vector rollout restart daemonset/vector
# 回滚 = git revert 本仓清单 → 重新 apply + restart；helm rollback 不含配置
```

变更纪律（生产实测坑位，详表见 [CM_BEST_PRACTICES.md](CM_BEST_PRACTICES.md) §5）：

- **Vector ≥0.57 默认关闭配置文件 env 插值**——`${VAR}` 依赖 overlay 注入的插值开关；开启后**全文（含注释）都会展开**，配置文件里不得残留未定义的 `${...}` 字面序列（否则加载期 exit 78）
- 校验必须在与运行一致的 env 下做（本地带 dummy env，或对运行中 Pod 做 `/etc/vector/` 目录级校验）
- Secret 用**目录挂载**，严禁 subPath 单文件挂进 chart 挂载点内部（`not a directory` 实测）

## 采集模式选型（为何 DaemonSet）

| 场景 | 推荐 |
|------|------|
| 通用日志采集（绝大多数情况） | **DaemonSet 节点级** ✅ 本方案 |
| 多租户埋点（租户信息在日志内容里） | DaemonSet |
| 容器内文件日志且改不了应用 | DaemonSet + sidecar tail（emptyDir 转发 stdout） |
| 按租户/服务强隔离的独立管道 | Sidecar 注入（每 Pod 一个 Vector，成本线性增长） |

DaemonSet 零侵入：业务 Pod 不用改镜像/声明卷；运行时无关（只读 `/var/log/pods`）；与 ACK 自带 logtail 共享只读挂载互不冲突（logtail→SLS 热查询、Vector→OSS 冷湖，可并行）。

## 与生产同源方案的差异声明

本目录是生产方案的**去业务化实验副本**，对齐其结构与纪律，刻意保留的差异：

| 项 | 本目录 | 生产同源方案 |
|---|---|---|
| 校验字段 | `user/ts/event`（通用字段） | `event/ts/tenant_id`（业务契约） |
| bucket | `vector-demo`（实验桶） | 生产桶 |
| 输出 | 单 JSON gzip | 单 JSON gzip（结构同） |
| partition | 年/月/日/时（无 minute，已对齐） | 同 |
| 实参注入 | overlay env（`${VAR}` + 插值开关） | 同（cm_inject_env 形态） |

## 故障排查

| 现象 | 排查 |
|------|------|
| 零事件（buffer/checkpoint 全空） | RBAC 未授权（日志 `watch list error with 403`）；授权后无需重装 |
| Pod CrashLoop（exit 78） | 配置加载失败：validate 看报错；含 `${VAR}` 时确认 overlay 注入了插值开关与三实参 |
| OSS 无对象但事件正常 | batch 600s 未到（最多 ~10 分钟延迟）；或 sink 写出失败（日志 grep `track_oss` + `error`） |
| `NoSuchBucket` | region 与 Bucket 不一致，或 endpoint 错误 |
| `403 Forbidden` | AK 权限不足，需 `oss:PutObject` |
| 镜像拉取超时 | 节点直连 docker.io 不通，确认镜像加速前缀 |

## 关联文档

- [CM_BEST_PRACTICES.md](CM_BEST_PRACTICES.md)：两形态对照、八条纪律、坑位对照表（本篇的决策依据）
- [../../docs/vector-parquet-best-practices.md](../../docs/vector-parquet-best-practices.md)：Parquet 输出专题（本目录未启用）
- 生产同源方案：`track-pipeline` 仓（手写 CM 清单实例、${VAR} 化与坑位总表的权威源）
