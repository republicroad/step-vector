# Vector 采集 Kubernetes Pod 日志

对应 Better Stack config [`kubernetes`](https://telemetry.betterstack.com/docs/logs/vector/#available-configs)。

## 两种用法

### 1. 本地模拟（compose，无集群）

```
log-gen ──> pod-logs 卷 (/var/log/pods/<ns>_<pod>_<uid>/<container>/0.log, CRI 格式)
                          │
               vector: file source + VRL 复刻 kubernetes_logs 逻辑
                (CRI 头剥离 + 路径提取 pod/namespace/container + JSON 展开)
                          │
              ./output/kubernetes-YYYYMMND.ndjson + console
```

```bash
podman compose up -d
podman compose logs -f vector
Get-Content output\kubernetes.ndjson -Tail 5
```

模拟器生成两个 pod（`default/demo-pod`、`prod/api-pod`）的 CRI 格式日志（`时间 stdout F JSON`）。

> **为什么不用 `kubernetes_logs` source 模拟？** 该 source 强依赖 Kubernetes API server（启动配置检查 + pod 元数据门控，拿不到 API 一个事件都不放行），集群外无法运行。本演示用 `file` source + VRL 复刻其两个核心步骤——CRI 头剥离与 kubelet 路径元数据提取——日志格式与元数据字段（`kubernetes.pod_namespace/pod_name/container_name`）与真集群采集完全一致。**真集群请直接用下面的 DaemonSet。**

### 2. 真实集群（推荐，原生 `kubernetes_logs`）

```bash
kubectl apply -f k8s/daemonset.yaml
kubectl -n vector logs -f daemonset/vector
```

清单含 ServiceAccount + ClusterRole（pods/namespaces 只读）+ DaemonSet（hostPath `/var/log`、`VECTOR_SELF_NODE_NAME` 通过 downward API 注入），labels/annotations 等增强元数据完整。sink 默认 console，按需打开配置里注释的 `better_stack`。

## 要点

- kubelet 把容器日志落盘为 `/var/log/pods/<ns>_<pod>_<uid>/<container>/0.log`，CRI 运行时格式为 `时间 stdout/stderr F|P 载荷`（F=完整行，P=被截断的部分行）
- `kubernetes_logs` 在真集群中自动完成：文件发现、CRI 头剥离、路径元数据、partial 行合并（`auto_partial_merge`）、API 元数据增强（labels/annotations/owner）
- 本地模拟 transform 与 DaemonSet 的 `normalize` 输出结构对齐，切换成本低
- DaemonSet 是 K8s 日志采集的标准形态——每个节点一个 Vector，读宿主机 `/var/log`

## 切 Better Stack

`vector.yaml`（或 DaemonSet 的 ConfigMap）取消注释 `better_stack` sink 并设置 `SOURCE_TOKEN` / `INGESTING_HOST`；或：

```bash
curl -o vector.yaml "https://telemetry.betterstack.com/vector-yaml/kubernetes/$SOURCE_TOKEN"
```
