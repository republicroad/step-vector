# Vector 日志采集 → 阿里云 OSS

使用 [Vector](https://vector.dev) 采集本地磁盘日志（`file` source），写入阿里云 OSS（`aws_s3` sink，OSS 兼容 S3 API）。容器化部署（Docker Compose），断点续传 + 密钥托管。

## 目录结构

```
step-vector/
├── vector.yaml          # Vector 配置（JSON + Parquet 双输出）
├── secrets/
│   ├── oss-secrets-template.json # 密钥模板；运行前复制为 oss-secrets.json 并填入真实密钥
│   └── oss-secrets.json  # 真实密钥（已被 .gitignore 忽略，不会入库）
├── duckdb/
│   └── queries.sql      # DuckDB 查询示例
├── compose.yaml         # 容器编排（python-log-gen 生成日志 + vector 采集）
├── gen-log.py           # Python 日志生成器（JSON 行，RFC3339 timestamp）
├── .gitignore           # 忽略 secrets/oss-secrets.json 等敏感文件
├── docs/
│   └── podman-proxy-fix.md # Podman 容器环境文档
└── README.md
```

## 快速开始

```bash
# 1. 从模板生成密钥文件，并填入你的 RAM AccessKey
mv secrets/oss-secrets-template.json secrets/oss-secrets.json   # 已存在时 mv 会覆盖，注意备份
# 2. 按需修改 vector.yaml（bucket / region / endpoint / 日志路径）
docker compose up -d
```

验证：`docker compose logs -f vector`；OSS 控制台确认对象按 `log_json/year=YYYY/month=MM/day=DD/hour=HH/minute=MM/`（北京时间）落地。

## Vector 配置说明

### 双输出配置

Vector 同时输出 JSON 和 Parquet 两种格式：

| Sink | Bucket | 格式 | 压缩 | 路径前缀 |
|------|--------|------|------|----------|
| `aliyun_oss` | `vector-demo` | gzip JSON lines | gzip | `log_json/year=.../month=.../day=.../hour=.../minute=.../` |
| `aliyun_oss_parquet` | `vector-demo` | Parquet | zstd (level 3) | `log_parquet/year=.../month=.../day=.../hour=.../` |

### Parquet 配置

```yaml
encoding:
  codec: json                    # placeholder，batch_encoding 会接管
batch_encoding:
  codec: parquet
  schema_mode: auto_infer        # 自动推断 schema
  compression:
    algorithm: zstd              # 选型依据见 ../docs/ZSTD_VS_SNAPPY.md
    level: 3                     # Vector 0.58 要求 zstd 必须显式配置 level
```

### 与 RustFS 配置的主要差异

| 配置项 | 阿里云 OSS | RustFS |
|--------|-----------|--------|
| `endpoint` | `https://oss-cn-hangzhou.aliyuncs.com` | `http://rustfs:9000` |
| `region` | `cn-hangzhou` | `us-east-1`（默认） |
| `force_path_style` | `false`（OSS 仅支持 vhost） | `true`（RustFS 支持 path-style） |
| `bucket` | 已有 bucket | 需先创建（bucket-init 自动完成） |

## data_dir 持久化方案

`data_dir` 存放 `file` source 的 **checkpoint**（断点）和可能的 **disk buffer**，必须持久化，否则容器重建后丢失断点、从头重读日志。

### 1. 命名卷（当前方案）

`compose.yaml` 中：

```yaml
volumes:
  - vector-data:/vector-data-dir
volumes:
  vector-data:
```

- 首次创建时 Docker 会从镜像的 `/vector-data-dir` 继承属主/权限，非 root 的 `vector` 用户（uid 1000）可直接读写，无需 `chown`
- `docker compose down` 不会删除卷；容器重建断点仍在
- 清空断点（会重新从头读）：`docker volume rm step-vector_vector-data`

### 2. 外部卷（external）

卷先由运维独立创建、生命周期与 compose 项目解耦，多环境/多项目共享或由 CI 预创建时用：

```yaml
services:
  vector:
    volumes:
      - vector-data:/vector-data-dir

volumes:
  vector-data:
    external: true
    name: my-vector-data
```

```bash
docker volume create my-vector-data
# 外部卷不会被 docker compose down 删除
```

注意：外部卷不会自动继承镜像目录属主。若容器内 `vector` 用户无写权限，先初始化属主：

```bash
docker run --rm \
  -v my-vector-data:/vector-data-dir \
  alpine chown -R 1000:1000 /vector-data-dir
```

### 3. Bind mount 宿主路径

把数据直接落到宿主机指定目录，便于查看/备份（权限随宿主，需自行保证可写）：

```yaml
services:
  vector:
    volumes:
      - /opt/vector-data:/vector-data-dir
```

宿主侧准备：

```bash
mkdir -p /opt/vector-data
chown 1000:1000 /opt/vector-data   # 让容器内 vector 用户可写
```

## 配置技巧

### 断点续传（file source）

- `read_from: beginning`：新文件从头读；已有 checkpoint 的文件按断点续传
- `ignore_checkpoints: false`：不清空已有断点
- `fingerprint.strategy: checksum`：用文件内容前 N 行 CRC 做指纹，跨日志轮转（logrotate 改名/重建）可靠；Windows 上尤其不要用 `device_and_inode`
- 断点存于 `data_dir` 下，格式可移植（Linux/Windows 通用）
- 改完配置重启或 `SIGHUP` 重载，断点不会丢

### 密钥托管（secret file 后端）

密钥不写在 `vector.yaml`，由 `file` 后端从 JSON 文件读取，进程环境里不落地：

```yaml
secret:
  oss_credentials:
    type: file
    path: /etc/vector/oss-secrets.json
```

引用语法：`SECRET[oss_credentials.access_key_id]`。`oss-secrets.json` 格式：

```json
{
  "access_key_id": "LTAI5t...",
  "secret_access_key": "..."
}
```

- 请求的 key 缺失或为空 → Vector 启动报错退出（不会半应用）
- 密钥更新后需重启或 `SIGHUP` 重载
- `secrets/oss-secrets.json` 由 `secrets/oss-secrets-template.json` 复制而来（见「快速开始」），且已被 `.gitignore` 忽略、不入版本库
- 该文件仍是明文，建议收紧文件权限并妥善保管

### 阿里云 OSS（aws_s3 sink）

- `endpoint`：外网 `https://oss-{region}.aliyuncs.com`；同地域 ECS 内网免流量 `https://oss-{region}-internal.aliyuncs.com`
- `region`：Bucket 所在地域 ID（如 `cn-hangzhou`），必须与 Bucket 一致，否则 `NoSuchBucket`
- `force_path_style: false`：OSS 要求虚拟托管寻址（域名 `<bucket>.oss-{region}.aliyuncs.com`）；私有/自建 S3 兼容服务可设 `true`
- 凭证是**阿里云 RAM AccessKey**，不是 AWS 的，勿混用
- `key_prefix` 支持两种时间基准（处理时间 / 事件时间），见下节「分区时间基准」
- `encoding.codec: raw_message`：对象内容 = 原始日志行（换行分隔），消费端（SLS OSS 导入 / Athena / EMR）不用剥 Vector 包裹层，体积更小；若下游分析依赖 timestamp/host 等元数据，改回 `json`（每行包一层 `{"message":...,"timestamp":...,...}`）

### Parquet 列式输出（batch_encoding）

`aliyun_oss_parquet` sink 输出 **Parquet 列式格式**（下游 Athena/EMR/SLS 分析更友好、列压缩更省空间）。关键点：

- **写法**：aws_s3 sink 用 `batch_encoding`（文档 https://vector.dev/docs/reference/configuration/sinks/aws_s3/#batch_encoding ），**不是** `encoding.codec: parquet`：
  ```yaml
  encoding:                # schema 仍强制要求 encoding 存在
    codec: json            # 仅占位，实际输出由 batch_encoding 决定（被旁路）
  batch_encoding:
    codec: parquet
    schema_mode: auto_infer   # 按批自动推断 schema，无需 schema 文件
    compression:
      algorithm: zstd         # gzip | lz4 | none | snappy | zstd
      level: 3                # Vector 0.58 要求 zstd 必须显式配置 level
  ```
- **schema_mode**：`auto_infer` 无需 schema 文件；`relaxed`/`strict` 需 `batch_encoding.schema_file` 指向原生 Parquet schema 文件（缺字段置 null / 多字段报错）
- **压缩旁路**：设了 `batch_encoding` 后，sink 顶层 `compression` 与 `framing` 会被旁路——Parquet 自带列页内压缩（即 `batch_encoding.compression`）
- **已验证**：端到端跑通，OSS 中出现 `*.parquet` 对象，头尾魔数均为 `PAR1`（扩展名由 codec 决定，无需手配）
- 首次启用注意：从 `raw_message` 切到 parquet 时 checkpoint 会续读同一文件，之前已读部分不重放

### 分区时间基准：事件时间 vs 处理时间

`key_prefix` 决定对象目录按什么时间切分，两种基准：

**1. 处理时间（默认，最简单）** —— strftime 用 Vector 处理时间（写入时的时间），配合 `timezone` 字段即可，无需 transform：

```yaml
key_prefix: "logs/date=%Y-%m-%d/HH=%H/MM=%M/"   # 处理时间，分钟级
# 按小时： key_prefix: "logs/date=%Y-%m-%d/HH=%H/"
timezone: Asia/Shanghai
```

**2. 事件时间（推荐，晚到/重放数据归位正确）** —— 应用打点日志为 JSON 行（ndjson），行内 `timestamp` 字段是 RFC3339；先用 remap 解析 JSON 并把 `timestamp` 解析进 `.timestamp`，再按目标时区格式化出分区字段，`key_prefix` 用模板语法 `{{ }}` 引用：

```yaml
# transforms：parse_ts 解析 + partition 生成分区字段（RFC3339 用 "%+"）
transforms:
  parse_ts:
    type: remap
    inputs: [local_logs]
    source: |
      parsed, err = parse_json(.message)
      if err == null {
        ts, ts_err = parse_timestamp(parsed.timestamp, format: "%+")
        if ts_err == null { .timestamp = ts }
      }
  partition:
    type: remap
    inputs: [parse_ts]
    source: |
      .partition_year  = format_timestamp!(.timestamp, format: "%Y", timezone: "Asia/Shanghai")
      .partition_month = format_timestamp!(.timestamp, format: "%m", timezone: "Asia/Shanghai")
      .partition_day   = format_timestamp!(.timestamp, format: "%d", timezone: "Asia/Shanghai")
      .partition_hour  = format_timestamp!(.timestamp, format: "%H", timezone: "Asia/Shanghai")
      .partition_minute = format_timestamp!(.timestamp, format: "%M", timezone: "Asia/Shanghai")

key_prefix: "log_json/year={{ partition_year }}/month={{ partition_month }}/day={{ partition_day }}/hour={{ partition_hour }}/minute={{ partition_minute }}/"
```

对比：处理时间适合日志即时落地、不重放的场景；事件时间适合数据补录/重放/延迟上报，目录按日志自身时间归档，便于按时间范围做增量过滤。

### 近实时增量分析（分钟级分区建议）

分钟级分目录（`key_prefix: "log_json/year=%Y/month=%m/day=%d/hour=%H/minute=%M/"`）有利于近实时日志分析做增量过滤，注意配合以下实践：

- **Hive 友好的分层前缀**：用键值式路径 `log_json/year=%Y/month=%m/day=%d/hour=%H/minute=%M/`，Athena / Databricks / EMR 建分区表时可按 `year/month/day/hour/minute` 谓词下推，增量查询只扫目标分钟目录
- **落地延迟**：调小 `batch.timeout_secs`（如 10–15s）让对象更接近实时；代价是对象更小、PUT 请求更多
- **对象大小**：日志量大时用 `batch.max_events` / `batch.max_bytes` 让每个对象达到 1–10MB 再 flush，避免海量小文件
- **防覆盖**：`filename_append_uuid: true`（默认）避免同一分钟内同名覆盖，文件名时间戳（`filename_time_format`）便于排序
- **下游增量扫描**：按分钟目录前缀 List（`ossutil ls oss://<bucket>/log_json/year=.../month=.../day=.../hour=.../minute=.../`）作为增量边界，配合已处理前缀记录实现增量导入，比整桶 List 高效
- **事件时间分区**：默认 `key_prefix` 的 strftime 用 Vector 处理时间。应用打点日志为 JSON 行，行内 `timestamp` 字段是 RFC3339，先用 remap 的 `parse_json(.message)` + `parse_timestamp(parsed.timestamp, format: "%+")` 解析进 `.timestamp`，再用 VRL 按目标时区格式化出 `partition_year/month/day/hour/minute` 字段，`key_prefix` 用模板语法引用：`key_prefix: "log_json/year={{ partition_year }}/month={{ partition_month }}/day={{ partition_day }}/hour={{ partition_hour }}/minute={{ partition_minute }}/"`——目录按事件时间分割，晚到/重放的数据也落进正确分区
- **晚到日志模拟**：`gen-log.py` 按 `LATE_RATIO`（默认 0.3）比例把时间戳回填到过去（最长 `LATE_MAX_BACKFILL_SECONDS`，默认 24h），message 带 `[late]` 标记。写入时刻是当前，但事件时间在旧分区——验证事件时间分区是否生效：OSS 中应出现过去时间（如前一天）的 `year=.../month=.../day=.../hour=.../minute=.../` 目录，且 `[late]` 行落在对应旧分钟目录
- **生命周期规则**：分钟级目录适合短期热数据，配置规则把 N 天前的对象转归档/冷归档、更久后删除，降低小文件与存储费用
- **时区一致性**：确认 Vector 的 `timezone`（默认 UTC / `local`）与分区时间语义一致，避免目录时间与期望时区差 8 小时
- **成本观察**：PUT 按次计费 + 每对象最小按 64KB 计量，观察每分钟对象数，评估分钟级与小时级的成本差异

### 跨平台一致性技巧（Linux / Windows）

Vector 不展开 `~`，v0.57+ 默认禁用 `${VAR}` 环境变量插值。同一份 `vector.yaml` 双端通用的小技巧：所有路径写**相对路径**，并在容器里设置 `working_dir`：

```yaml
# compose.yaml（相对路径方案，与当前卷方案二选一）
services:
  vector:
    working_dir: /etc/vector
    volumes:
      - ./:/etc/vector
```

此时 `data_dir: ./data`、`path: ./secrets/oss-secrets.json` 相对 `/etc/vector` 解析，Windows 本地跑则相对启动目录解析。缺点：data 走 bind mount，需保证容器用户可写。

## 故障排查与修复记录

### VRL 编译错误（vector 启动失败，exit 78）

`parse_ts` transform 的 VRL 脚本有编译错误时，vector 无法启动、不断重启，`podman logs vector` 里反复出现 `Configuration error. error=Transform "parse_ts": error[E...]`。本次踩过的两个：

**E103：unhandled fallible assignment**

`merge(., parsed)` 会被编译器标记为「可失败的赋值未处理」。`parse_json()` 的返回类型无法静态保证是对象，而 `merge()` 对非对象会运行失败，必须用强制不失败版 `merge!`（配合 `is_object(parsed)` 前置判断）：

```vrl
parsed, err = parse_json(.message)
if err == null && is_object(parsed) {
  . = merge!(., parsed)   # merge! 而非 merge
}
```

**E630：fallible argument**

`log()` 的第一个参数必须是不可失败表达式，但 `string(ts_err)`（对 error 类型转换）和 `"..." + 非字符串` 都是可失败的：

```
error[E630]: fallible argument
  log("...: " + string(ts_err), level: "warn")
```

修复：error 值可直接用 `+` 拼接（VRL 会自动转字符串），去掉 `string()`；或用断言版 `string!(ts_err)`：

```vrl
log("timestamp missing or not RFC3339, using ingestion time: " + ts_err, level: "warn")
```

### OSS sink 报 dispatch failure（healthcheck 失败）

healthcheck 与请求重试都报 `error=dispatch failure`，但配置/证书/密钥均正常 → 网络层问题。根因是 podman 把宿主机代理变量注入容器，AWS SDK 走了容器内不可达的 `127.0.0.1:7890`。完整排查与修复见《[podman-proxy-fix.md](./docs/podman-proxy-fix.md)》。

### 验证 OSS 已写入的通用命令

healthcheck 只验证连通与权限，确认对象真实落地可用 curl 的 `--aws-sigv4` 直接列 bucket（见 podman-proxy-fix.md 末尾，Windows 下可用，避免手写 SigV4 canonical request 的坑）。

## 常见运维命令

```bash
docker compose up -d          # 启动
docker compose logs -f vector # 看日志
docker compose restart vector # 重启（断点保留）
docker kill -s HUP <容器>      # 或 SIGHUP 热重载配置
docker compose down           # 停（不删命名卷）
docker volume ls              # 查看卷
```

## 使用 DuckDB 查询 OSS 数据

### 安装 DuckDB

```bash
# Windows (winget)
winget install DuckDB.DuckDB

# macOS (Homebrew)
brew install duckdb

# Linux
curl https://install.duckdb.org | sh
```

### 创建 OSS Secret

```bash
# 启动 DuckDB
duckdb

# 创建 Secret（替换为你的 AccessKey）
CREATE OR REPLACE SECRET oss (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5txxxxxxxxxxxx',
    SECRET 'xxxxxxxxxxxxxxxxxxxxxxxx',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    REGION 'cn-hangzhou',
    URL_STYLE 'vhost',
    USE_SSL true
);

# 持久化 Secret（可选，重启后自动加载）
CREATE PERSISTENT SECRET oss_persistent FROM duckdb_secrets WHERE name = 'oss';
```

### 查询示例

```bash
# 执行预置查询
duckdb -f duckdb/queries.sql

# 交互式查询
duckdb
```

### 常用 SQL

```sql
-- 列出所有 JSON 日志文件
SELECT * FROM glob('s3://vector-demo/log_json/**');

-- 查询 JSON 日志
SELECT * FROM read_json('s3://vector-demo/log_json/**/*.log.gz');

-- 查询 Parquet 日志
SELECT * FROM read_parquet('s3://vector-demo/log_parquet/**/*.parquet');

-- 按小时统计文件数
SELECT
    regexp_extract(file, 'year=([^/]+)', 1) as year,
    regexp_extract(file, 'month=([^/]+)', 1) as month,
    regexp_extract(file, 'day=([^/]+)', 1) as day,
    regexp_extract(file, 'hour=([^/]+)', 1) as hour,
    count(*) as files
FROM glob('s3://vector-demo/log_json/**/*')
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;

-- Parquet 分区过滤（利用分区裁剪）
SELECT * FROM read_parquet('s3://vector-demo/log_parquet/**/*.parquet')
WHERE year = '2026' AND month = '08' AND day = '21';
```

### DuckDB 与 OSS 的关键点

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `URL_STYLE` | `vhost` | OSS 使用虚拟托管寻址 |
| `USE_SSL` | `true` | OSS 使用 HTTPS |
| `REGION` | `cn-hangzhou` | Bucket 所在地域 |
| `ENDPOINT` | `oss-cn-hangzhou.aliyuncs.com` | OSS 端点 |

## 权限速查

| 场景 | 处理 |
| --- | --- |
| 命名卷 | 自动继承镜像属主，无需处理 |
| 外部卷 | `docker run --rm -v <卷>:/vector-data-dir alpine chown -R 1000:1000 /vector-data-dir` |
| bind mount | 宿主 `chown 1000:1000 /opt/vector-data` |
