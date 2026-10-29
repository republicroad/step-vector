# 最佳实践：手写 ConfigMap 维护 Vector 配置（Helm 装软件、配置不进模板）

> 背景：本目录早期采用 **Helm inline customConfig** 形态（配置本体进 Helm 渲染管线，见 git 历史中的旧 `values.yaml`）；生产同源方案在 ACK 上演进为「**手写 ConfigMap 清单外置**」形态并实测定案（坑位编号沿用生产排障手册）。
> 场景：用 Helm 安装第三方采集器（Vector 等）并**长期管理其配置**时的形态决策与操作纪律。结论：**渲染与保真分家——Helm 管装，配置本体手写 ConfigMap 清单直 apply。**

## 1. 原则一句话与两形态对照

判据：**内容要参数化分发 → 交给 Helm；内容要逐字保真（自带 `{{ }}` 模板语法/VRL/正则的应用配置）→ 手写清单直 apply，不进渲染管线。**

| 维度 | inline customConfig（演进前形态） | 手写 CM 清单外置（现形态） |
|---|---|---|
| 配置载体 | Helm values 的 `customConfig` 字段 | 独立 ConfigMap 多文档清单（`data` 键 = 配置文件） |
| 渲染 | Helm 渲染管线（配置经 chart 模板序列化） | 无（清单即资源，`kubectl apply -f` 逐字落地） |
| 配置含 `{{ }}` 模板语法 | 与 Go template 撞车，需转义壳 | **原生直写，零转义** |
| VRL 语义错误 | 渲染期查不出，运行期 CrashLoop | 部署前 `vector validate` 可查 |
| 变更生效 | `helm upgrade`（chart 层变更混在一起） | `apply -f` + `rollout restart`（配置变更独立走） |
| 回滚 | `helm rollback`（混工作负载历史） | git revert 清单 + 重新 apply（配置独立历史） |

**边界（诚实版）**：inline 并非处处错——配置**无自有模板语法冲突、结构简单、变更低频**时（如 redis 的 maxmemory、log level），进 values 完全可接受，独立清单反而是管理负担。分水岭在「配置内容是否会被 Helm/应用两层模板语义污染」。

## 2. inline 形态（本目录演进前）的三个实测级风险

| # | 风险 | 演进前 values.yaml 的具体位置 | 实测依据（ACK + containerd 生产） |
|---|---|---|---|
| 1 | **Secret subPath 挂载**：单文件挂进 chart 的 config 挂载点内部 | 旧 `extraVolumeMounts`：`mountPath: /etc/vector/oss-secrets.json` + `subPath` | 坑 #4：9/9 节点实测 `failed to create shim task ... not a directory`，Pod 起不来；必须**目录挂载**到新增路径 |
| 2 | **未锁 chart/镜像版本**：`helm upgrade` 不带 `--version`，values 不写 image tag | 快速开始命令与 values 均未固定 | 坑 #1：chart ≥0.52 要求 K8s ≥1.28（ACK v1.24 被拒）；坑 #5：镜像需国内加速前缀；坑 #7：`routes`(复数)/`route`(单数) 等语法随版本漂移——「行为取决于拉到哪一版」是最大不确定性 |
| 3 | **`{{ }}` 双模板冲突**：`key_prefix` 内 `{{ cluster }}`/`{{ partition_year }}` 位于 customConfig 内 | 旧 key_prefix 两处 | 坑 #2：chart 对 customConfig 做模板渲染时 `{{ cluster }}` 被当作 Go 函数 → `function "cluster" not defined`；是否触发取决于 chart 版本的序列化实现——不锁版本等于赌注 |

另有一处**模板牵连**风险（坑 #3/#13）：chart 会由配置内容推导 Service 端口，缺字段时渲染出空端口 Service 被 K8s 拒绝——inline 形态下「配置」与「工作负载」边界模糊正是此类问题的温床。

## 3. 手写 CM 外置形态：八条操作纪律

1. **chart 只管装**：工作负载（DS/SA/Service）由 chart 渲染；配置本体 = 独立 ConfigMap 多文档清单，`kubectl apply -f` 直建（`existingConfigMaps` 挂载模式）
2. **多文档清单 + 字典序合并**：单文件多文档（`---` 分隔），数据键按文件名排序加载（`10-common.yaml` 公共段 → `20-oss.yaml` sink 段，后者可覆盖前者同名键）；启动参数 `--config-dir /etc/vector/`
3. **零转义**：`{{ }}`（Vector 模板）与 VRL 在数据段（块标量）中原样直写
4. **静态 CM 名不自动生效**：`apply -f` 后必须 `kubectl rollout restart daemonset/vector`（或上 Reloader 注解自动化）；最常漏的一步
5. **变更前校验**：`vector validate`——三种方法：① 提取数据段后本地校验；② 对运行中 Pod 的 `/etc/vector/` 目录级校验；③ 清单含 `${VAR}` 时本地须带 dummy env
6. **版本锁定**：chart 显式 `--version`（如 0.51.0）+ 镜像 tag 固定（含国内加速前缀）；升级前 `helm template` 渲染三查（image / serviceAccount / 挂载与启动参数）
7. **Secret 目录挂载**：K8s Secret 挂到**新增目录**（如 `/etc/oss-secrets/`），sink 内 `SECRET[...]` 引用；**严禁 subPath 单文件挂进 chart 已有挂载点内部**（坑 #4）；AK/SK 永不经 env（env 可被能读 `/proc/<pid>/environ` 的用户读取）
8. **env 实参（可选演进）**：非敏感实参（bucket/region/endpoint/cluster 名）以 `${VAR}` 写入配置 + overlay env 注入；**Vector ≥0.57 默认关闭配置文件 env 插值**（官方变更），须注入 `VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true`（坑 #15）；开启后插值对全文（含注释）生效——注释不得残留未定义的 `${...}` 字面序列

## 4. 日常变更流程与回滚

```bash
# 配置变更（CM 数据段）：
vim  vector-cm.yaml                         # 改对应文档数据段
vector validate …                           # 校验（方法见纪律 5；含 ${VAR} 时带 dummy env）
kubectl apply -f vector-cm.yaml -n vector   # CM 就位（幂等；本身不触发滚动）
kubectl -n vector rollout restart daemonset/vector   # 手动滚动（checkpoint 续采，秒级空窗）
# 回滚 = git revert 清单 → 重新 apply + restart；helm rollback 不含配置
```

## 5. 坑位对照表（生产实测编号）

| 坑 | 一句话 | 对应纪律 |
|---|---|---|
| #1 | chart ≥0.52 要求 K8s ≥1.28，老集群被拒 | 纪律 6 锁 `--version 0.51.0` |
| #2 | customConfig 内 `{{ }}` 被 Helm 当 Go 函数解析 | 形态外置（纪律 1-3） |
| #3/#13 | api.address 牵连 Service 端口推导 / 空端口 Service 被拒 | inline 模式固有；外置后边界清晰 |
| #4 | Secret subPath 挂 config 挂载点内部 → `not a directory` | 纪律 7 目录挂载 |
| #5 | 节点直连 docker.io 超时 | 纪律 6 镜像加速前缀 |
| #7 | VRL/字段语法随版本漂移（`routes`→`route` 等） | 纪律 6 锁镜像 + validate |
| #12 | VRL 语义错误渲染期查不出 → CrashLoop | 纪律 5 validate 前置 |
| #15 | ≥0.57 默认关闭 env 插值；开启后注释中的 `${...}` 也被展开 | 纪律 8 开关 + 注释卫生 |

## 6. 两形态选型速查

| 场景 | 推荐形态 |
|---|---|
| 本地试验 / 学习 / demo | inline customConfig（单文件好分发，git 历史可查本目录演进前样例） |
| 配置简单、无模板语法冲突、变更低频 | inline 可接受（诚实边界，不必教条外置） |
| 配置含 `{{ }}`/VRL/脚本、生产长期运行、多环境多集群 | **手写 CM 清单外置**（本篇） |
| 实参数量多、多机房 | 外置 + `${VAR}` env 注入（overlay 承载机房差异） |
| 服务/清单规模持续增长 | 外置 + GitOps（Argo CD/Flux，清单可被控制器安全同步） |

选型列为社区经验口径，按团队技能与规模校准；「抽象复用」类收益（如 CDK8s）对清单量小的团队为负。

## 7. 参考实现

- 生产同源仓：`deploy/manifests/`（手写多文档 CM 清单实例：公共段 + 双机房通用 sink，实参 ${VAR} 化）、`docs/config-management.md`（三形态演进全记录）、`operations/deploy-ack.md`（部署手册与坑位总表）、`curated-compaction/`（同款纪律的 CronJob 部署单元）
- 本仓 `source/vector2oss/`：OSS sink 参数的先行验证（batch/buffer/acks/parquet）；`docs/VECTOR_PARQUET_BEST_PRACTICES.md`：Parquet 输出专题
