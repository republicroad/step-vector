# DuckDB 对象存储（S3/OSS/RustFS）配置指南

> 背景：DuckDB 经 httpfs 扩展读取 S3/OSS/RustFS 的 Secret 配置方式与查询指南。
> 场景与结论：分析侧连接对象存储时照抄；SCOPE 多凭证分域与虚拟托管寻址为重点。

## 前置准备

```sql
-- DuckDB 会自动加载 httpfs 扩展，也可手动安装
INSTALL httpfs;
LOAD httpfs;
```

---

## 一、AWS S3

### 1.1 Secret 配置

```sql
-- 方式一：手动配置
CREATE OR REPLACE SECRET aws_s3 (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'AKIAIOSFODNN7EXAMPLE',
    SECRET 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
    REGION 'us-east-1'
);

-- 方式二：自动获取凭证（环境变量、~/.aws/credentials 等）
CREATE OR REPLACE SECRET aws_s3_auto (
    TYPE s3,
    PROVIDER credential_chain
);

-- 方式三：指定 AWS Profile
CREATE OR REPLACE SECRET aws_s3_profile (
    TYPE s3,
    PROVIDER credential_chain,
    CHAIN config,
    PROFILE 'my-profile'
);

-- 方式四：带 SCOPE 限定（不同路径用不同凭证）
CREATE OR REPLACE SECRET aws_s3_prod (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'AKIAIOSF_PROD_KEY',
    SECRET 'ProdSecretKey',
    REGION 'us-west-2',
    SCOPE 's3://prod-bucket/warehouse/'
);

CREATE OR REPLACE SECRET aws_s3_dev (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'AKIAIOSF_DEV_KEY',
    SECRET 'DevSecretKey',
    REGION 'us-east-1',
    SCOPE 's3://dev-bucket/'
);
```

### 1.2 查询示例

```sql
-- 读取单个文件
SELECT * FROM 's3://my-bucket/data.parquet';

-- 通配符匹配多个文件
SELECT * FROM 's3://my-bucket/data/*.parquet';

-- 写入文件
COPY (SELECT * FROM my_table) TO 's3://my-bucket/output.parquet';

-- 写入为 CSV
COPY (SELECT * FROM my_table) TO 's3://my-bucket/output.csv' (HEADER, DELIMITER ',');
```

### 1.3 临时凭证（STS）

```sql
CREATE OR REPLACE SECRET aws_s3_sts (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'ASIAIOSFODNN7EXAMPLE',
    SECRET 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
    SESSION_TOKEN 'FwoGZXIvYXdzEBY...',
    REGION 'us-east-1'
);
```

### 1.4 KMS 加密

```sql
CREATE OR REPLACE SECRET aws_s3_kms (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'AKIAIOSFODNN7EXAMPLE',
    SECRET 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
    REGION 'us-east-1',
    KMS_KEY_ID 'arn:aws:kms:us-east-1:123456789012:key/12345678-1234-1234-1234-123456789012'
);
```

---

## 二、阿里云 OSS

### 2.1 Endpoint 格式

| 区域 | Endpoint |
|------|----------|
| 杭州 | `oss-cn-hangzhou.aliyuncs.com` |
| 上海 | `oss-cn-shanghai.aliyuncs.com` |
| 北京 | `oss-cn-beijing.aliyuncs.com` |
| 深圳 | `oss-cn-shenzhen.aliyuncs.com` |
| 成都 | `oss-cn-chengdu.aliyuncs.com` |
| 中国香港 | `oss-cn-hongkong.aliyuncs.com` |
| 新加坡 | `oss-ap-southeast-1.aliyuncs.com` |
| 美国（弗吉尼亚） | `oss-us-east-1.aliyuncs.com` |

### 2.2 Secret 配置

```sql
-- 基础配置（杭州区域）
CREATE OR REPLACE SECRET oss_hangzhou (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5txxxxxxxxxxxx',
    SECRET 'xxxxxxxxxxxxxxxxxxxxxxxx',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    REGION 'cn-hangzhou',
    URL_STYLE 'vhost',
    USE_SSL true
);

-- 上海区域
CREATE OR REPLACE SECRET oss_shanghai (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5txxxxxxxxxxxx',
    SECRET 'xxxxxxxxxxxxxxxxxxxxxxxx',
    ENDPOINT 'oss-cn-shanghai.aliyuncs.com',
    REGION 'cn-shanghai',
    URL_STYLE 'vhost',
    USE_SSL true
);

-- 带 SCOPE 限定（不同 bucket 使用不同凭证）
CREATE OR REPLACE SECRET oss_prod (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5tProdKey',
    SECRET 'ProdSecret',
    ENDPOINT 'oss-cn-beijing.aliyuncs.com',
    REGION 'cn-beijing',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://prod-bucket/'
);

CREATE OR REPLACE SECRET oss_dev (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5tDevKey',
    SECRET 'DevSecret',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    REGION 'cn-hangzhou',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://dev-bucket/'
);
```

### 2.3 查询示例

```sql
-- 读取文件
SELECT * FROM 's3://my-oss-bucket/data.parquet';

-- 通配符匹配
SELECT count(*) FROM 's3://my-oss-bucket/logs/*.parquet';

-- 写入
COPY (SELECT * FROM my_table) TO 's3://my-oss-bucket/output.parquet';
```

### 2.4 旧版 SET 方式（仍可用）

```sql
SET s3_access_key_id = 'LTAI5txxxxxxxxxxxx';
SET s3_secret_access_key = 'xxxxxxxxxxxxxxxxxxxxxxxx';
SET s3_endpoint = 'oss-cn-hangzhou.aliyuncs.com';
SET s3_url_style = 'vhost';

SELECT * FROM 's3://my-bucket/data.parquet';
```

### 2.5 注意事项

| 项目 | 说明 |
|------|------|
| `ENDPOINT` | **必须设置**，格式为 `oss-cn-{region}.aliyuncs.com` |
| `URL_STYLE` | **必须为 `vhost`**，OSS 不支持 path-style |
| `USE_SSL` | 建议 `true`（HTTPS） |
| `SCOPE` | 可选，用于限定 Secret 适用的 bucket 路径前缀 |

---

## 三、RustFS（自建 S3 兼容存储）

### 3.1 RustFS 默认端口

| 端口 | 用途 |
|------|------|
| 9000 | S3 API |
| 9001 | Web Console |

### 3.2 Secret 配置

```sql
-- 本地单节点
CREATE OR REPLACE SECRET rustfs_local (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT 'localhost:9000',
    REGION 'us-east-1',
    URL_STYLE 'path',
    USE_SSL false
);

-- 自定义端口
CREATE OR REPLACE SECRET rustfs_custom (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT '192.168.1.100:9000',
    REGION 'us-east-1',
    URL_STYLE 'path',
    USE_SSL false
);

-- 启用 virtual-hosted 模式的 RustFS（配置了 RUSTFS_SERVER_DOMAINS）
CREATE OR REPLACE SECRET rustfs_vhost (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT 'rustfs.yourdomain.com',
    REGION 'us-east-1',
    URL_STYLE 'vhost',
    USE_SSL true
);

-- 带 SCOPE 限定（不同 bucket 用不同凭证）
CREATE OR REPLACE SECRET rustfs_data (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT 'localhost:9000',
    REGION 'us-east-1',
    URL_STYLE 'path',
    USE_SSL false,
    SCOPE 's3://data-bucket/'
);

CREATE OR REPLACE SECRET rustfs_logs (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT 'localhost:9000',
    REGION 'us-east-1',
    URL_STYLE 'path',
    USE_SSL false,
    SCOPE 's3://logs-bucket/'
);
```

### 3.3 查询示例

```sql
-- 读取
SELECT * FROM 's3://my-bucket/data.parquet';

-- 通配符
SELECT * FROM 's3://my-bucket/data/*.parquet';

-- 写入
COPY (SELECT * FROM my_table) TO 's3://my-bucket/output.parquet';
```

### 3.4 RustFS Docker 部署参考

```bash
# 单节点启动
docker run -d \
  --name rustfs \
  -p 9000:9000 \
  -p 9001:9001 \
  -e RUSTFS_ROOT_USER=rustfsadmin \
  -e RUSTFS_ROOT_PASSWORD=rustfsadmin \
  -v /data/rustfs:/data \
  rustfs/rustfs server /data
```

---

## 四、SCOPE 机制说明

SCOPE 用于限定一个 Secret 适用的 S3 路径前缀。当有多个 Secret 时，DuckDB 根据查询路径自动匹配：

```sql
-- Secret A：匹配 s3://prod-bucket/ 下所有路径
CREATE OR REPLACE SECRET secret_a (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'key_a',
    SECRET 'secret_a',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://prod-bucket/'
);

-- Secret B：匹配 s3://dev-bucket/ 下所有路径
CREATE OR REPLACE SECRET secret_b (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'key_b',
    SECRET 'secret_b',
    ENDPOINT 'oss-cn-shanghai.aliyuncs.com',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://dev-bucket/'
);

-- Secret C：无 SCOPE，作为 fallback 匹配所有路径
CREATE OR REPLACE SECRET secret_default (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'default_key',
    SECRET 'default_secret',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    URL_STYLE 'vhost',
    USE_SSL true
);

-- 查询时自动匹配：
-- s3://prod-bucket/... → 使用 secret_a
-- s3://dev-bucket/...  → 使用 secret_b
-- s3://other/...       → 使用 secret_default
SELECT * FROM 's3://prod-bucket/data.parquet';
```

---

## 五、参数速查表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `ENDPOINT` | STRING | `s3.amazonaws.com` | 自定义 S3 端点（OSS/RustFS 必填） |
| `KEY_ID` | STRING | - | Access Key ID |
| `SECRET` | STRING | - | Secret Access Key |
| `REGION` | STRING | `us-east-1` | 认证区域 |
| `SESSION_TOKEN` | STRING | - | STS 临时凭证 Token |
| `URL_STYLE` | STRING | `vhost`（S3）/ `path`（RustFS） | URL 风格：`vhost` 或 `path` |
| `USE_SSL` | BOOLEAN | `true` | 是否使用 HTTPS |
| `URL_COMPATIBILITY_MODE` | BOOLEAN | `true` | URL 特殊字符兼容模式 |
| `SCOPE` | STRING | - | 限定 Secret 适用的路径前缀 |
| `KMS_KEY_ID` | STRING | - | S3 服务端加密 KMS Key |
| `REQUESTER_PAYS` | BOOLEAN | `false` | Requester Pays 模式 |

---

## 六、常见问题排查

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| `Connection error for HTTP HEAD` | 未设置 ENDPOINT | 显式设置 `ENDPOINT` |
| `403 Forbidden` | 凭证错误或权限不足 | 检查 KEY_ID/SECRET，确认 Bucket 权限 |
| `worker process exited` | 内存不足 | `SET memory_limit = '2GB';` |
| OSS 连接失败 | 使用了 path-style | `URL_STYLE` 设为 `vhost` |
| RustFS 连接失败 | SSL 配置错误 | 本地环境设 `USE_SSL false` |
| 临时凭证过期 | STS Token 过期 | 重新获取凭证并更新 Secret |

### 调试技巧

```sql
-- 限制内存避免 OOM
SET memory_limit = '2GB';

-- 单线程排查问题
SET threads = 1;

-- 先用 LIMIT 测试连接
SELECT * FROM 's3://bucket/file.parquet' LIMIT 10;

-- 查看已创建的 Secret
SELECT * FROM duckdb_secrets();
```

---

## 七、完整示例脚本

### 阿里云 OSS + SCOPE

```sql
LOAD httpfs;

CREATE OR REPLACE SECRET oss_prod (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5tProdKey',
    SECRET 'ProdSecret',
    ENDPOINT 'oss-cn-beijing.aliyuncs.com',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://prod-data/'
);

CREATE OR REPLACE SECRET oss_dev (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'LTAI5tDevKey',
    SECRET 'DevSecret',
    ENDPOINT 'oss-cn-hangzhou.aliyuncs.com',
    URL_STYLE 'vhost',
    USE_SSL true,
    SCOPE 's3://dev-data/'
);

-- 生产环境查询
SELECT count(*) FROM 's3://prod-data/events/2024/*.parquet';

-- 开发环境查询
SELECT * FROM 's3://dev-data/samples/test.parquet' LIMIT 100;

-- 跨 bucket 写入
COPY (SELECT * FROM 's3://dev-data/samples/test.parquet')
  TO 's3://prod-data/archive/test_copy.parquet';
```

### RustFS 本地环境

```sql
LOAD httpfs;

CREATE OR REPLACE SECRET rustfs (
    TYPE s3,
    PROVIDER config,
    KEY_ID 'rustfsadmin',
    SECRET 'rustfsadmin',
    ENDPOINT 'localhost:9000',
    URL_STYLE 'path',
    USE_SSL false
);

SELECT * FROM 's3://lakehouse/events.parquet';

COPY (SELECT * FROM my_table) TO 's3://lakehouse/output.parquet';
```


## 查询对象存储

```bash
select * from read_json('s3://<bucket-name>/logs/date=2026-08-14/HH=15/MM=33/1786696937-630030a1-7240-464f-a424-51537de6c8df.log.gz');
```

---

## 八、Hive 分区下推过滤（Partition Pruning）

### 8.1 原理

Parquet 文件使用 Hive 风格分区目录结构（如 `year=2026/month=08/day=21/hour=10/`），DuckDB 可以在查询时跳过不相关的目录，只扫描匹配的文件。

### 8.2 DuckDB 自动检测（v1.5.3+）

**DuckDB v1.5.3+ 自动检测 hive partitioning，无需显式设置 `hive_partitioning=true`。**

```sql
-- 自动检测分区列（推荐）
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet')
WHERE year = '2026' AND month = '08' AND day = '21';

-- 显式设置（兼容旧版本）
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day = '21';
```

### 8.3 测试结果对比

| 查询方式 | 扫描文件数 | 分区过滤 |
|----------|------------|----------|
| 无 hive_partitioning 设置 | 87/1198 | ✅ 自动检测 |
| hive_partitioning=true | 86/1191 | ✅ 显式设置 |

**结论：两者性能几乎相同，DuckDB 自动优化。**

### 8.4 查询示例

#### 基础过滤

```sql
-- 按年月日过滤
SELECT count(*) 
FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day = '21';

-- 按小时过滤（更精确）
SELECT count(*) 
FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day = '21' AND hour = '10';
```

#### 范围过滤

```sql
-- 月份范围
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month >= '08' AND month <= '12';

-- 日期范围
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day BETWEEN '15' AND '21';
```

#### 多条件组合

```sql
-- 多个过滤条件
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' 
  AND month = '08' 
  AND day BETWEEN '15' AND '21'
  AND hour IN ('09', '10', '11', '12');
```

### 8.5 验证分区裁剪

```sql
-- 查看 EXPLAIN 计划，确认文件扫描数量
EXPLAIN SELECT count(*) 
FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day = '21' AND hour = '10';

-- 输出示例：
-- READ_PARQUET
--    File Filters: (day = 21)(hour = '10')
--    Scanning Files: 86/1191
--    ~86,000 rows
```

### 8.6 注意事项

| 事项 | 说明 |
|------|------|
| 分区列类型 | 字符串类型，比较时用单引号 `'2026'` |
| 自动检测 | DuckDB v1.5.3+ 内置支持 |
| 性能 | 分区过滤在文件扫描前执行，跳过整个目录 |
| 兼容性 | 显式设置 `hive_partitioning=true` 更安全 |

### 8.7 推荐写法

```sql
-- 生产环境（推荐）
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet', hive_partitioning=true)
WHERE year = '2026' AND month = '08' AND day = '21';

-- 开发环境（简化）
SELECT * FROM read_parquet('s3://bucket/logs/**/*.parquet')
WHERE year = '2026' AND month = '08' AND day = '21';
```
