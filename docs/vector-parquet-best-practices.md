# Vector Parquet 最佳实践

> 背景：Vector batch_encoding Parquet 输出的 schema 模式、压缩算法与批次配置实践。
> 场景与结论：列式落地（Athena/EMR/DuckDB）选型参考；schema_mode 与压缩取舍见正文实测。

## 概述

Vector 的 `aws_s3` sink 支持直接输出 Parquet 格式，无需额外 ETL 流程。本文档总结配置最佳实践。

## 基础配置

```yaml
sinks:
  s3_parquet:
    type: aws_s3
    inputs: [partition]
    bucket: your-bucket
    region: us-east-1
    endpoint: http://rustfs:9000
    force_path_style: true

    # 分区路径
    key_prefix: "logs/year=%Y/month=%m/day=%d/hour=%H/"
    timezone: Asia/Shanghai
    filename_time_format: "%s"
    filename_append_uuid: true

    # Parquet 编码
    encoding:
      codec: json                    # placeholder，batch_encoding 会接管
    batch_encoding:
      codec: parquet
      schema_mode: auto_infer        # 或 strict
      compression:
        algorithm: snappy            # 推荐 snappy 或 zstd

    # 批量设置
    batch:
      timeout_secs: 30
      max_bytes: 10485760            # 10MB
      max_events: 10000              # 每个文件约 10K 行

    # 认证
    auth:
      access_key_id: your-key
      secret_access_key: your-secret
```

## 关键参数说明

### batch_encoding

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `codec` | 编码格式 | `parquet` |
| `schema_mode` | Schema 处理模式 | `auto_infer`（开发）/ `strict`（生产） |
| `compression.algorithm` | 列级压缩 | `snappy` 或 `zstd` |
| `compression.level` | 压缩级别（zstd/gzip） | `1-6` |

### batch

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `timeout_secs` | 批次超时（秒） | `30` |
| `max_bytes` | 最大批次大小 | `10485760`（10MB） |
| `max_events` | 最大事件数 | `10000` |

### 分区路径

```yaml
# 推荐：小时级分区（Parquet）
key_prefix: "logs/year=%Y/month=%m/day=%d/hour=%H/"

# 备选：分钟级分区（JSON，调试用）
key_prefix: "logs/year=%Y/month=%m/day=%d/hour=%H/minute=%M/"
```

## Schema 模式对比

| 模式 | Schema 来源 | 缺失字段 | 多余字段 | 适用场景 |
|------|-------------|----------|----------|----------|
| `auto_infer` | 每批自动推断 | N/A | N/A | 开发/测试 |
| `relaxed` | 需要 schema_file | 设为 null | 静默丢弃 | 灵活场景 |
| `strict` | 需要 schema_file | 设为 null | **报错** | 生产环境 |

## Schema 示例

### 基础 Schema（`logs.schema`）

```parquet
message schema {
  optional int64 timestamp (TIMESTAMP_MICROS);
  optional binary level (STRING);
  optional binary message (STRING);
  optional int32 order_id;
}
```

### 完整 Schema（含嵌套）

```parquet
message schema {
  optional int64 timestamp (TIMESTAMP_MICROS);
  optional binary level (STRING);
  optional binary message (STRING);
  optional int32 order_id;
  
  optional group metadata {
    optional binary host (STRING);
    optional binary source (STRING);
  }
}
```

### 使用 Schema 文件

```yaml
batch_encoding:
  codec: parquet
  schema_mode: strict
  schema_file: /etc/vector/schemas/logs.schema
  compression:
    algorithm: snappy
```

## 压缩算法对比

| 算法 | 压缩比 | 速度 | CPU 使用 | 推荐场景 |
|------|--------|------|----------|----------|
| `snappy` | 中等 | 快 | 低 | 默认选择 |
| `zstd` | 高 | 中等 | 中等 | 存储敏感 |
| `gzip` | 高 | 慢 | 高 | 兼容性优先 |
| `lz4` | 低 | 极快 | 极低 | 性能优先 |
| `none` | 无 | N/A | N/A | 不压缩 |

## 最佳实践总结

### 1. 批量大小

```yaml
# 日志量小（< 1GB/天）
batch:
  timeout_secs: 60
  max_events: 5000

# 日志量中等（1-10GB/天）
batch:
  timeout_secs: 30
  max_events: 10000

# 日志量大（> 10GB/天）
batch:
  timeout_secs: 15
  max_events: 50000
```

### 2. 分区策略

```yaml
# Parquet：小时级分区（推荐）
key_prefix: "logs/year=%Y/month=%m/day=%d/hour=%H/"

# JSON：分钟级分区（调试用）
key_prefix: "logs/year=%Y/month=%m/day=%d/hour=%H/minute=%M/"
```

### 3. Schema 管理

```yaml
# 开发环境
schema_mode: auto_infer

# 生产环境
schema_mode: strict
schema_file: /etc/vector/schemas/logs.schema
```

### 4. 压缩选择

```yaml
# 默认（推荐）
compression:
  algorithm: snappy

# 存储优化
compression:
  algorithm: zstd
  level: 6
```

## 常见问题

### Q: Parquet 文件太大？
A: 减少 `max_events`，如从 `100000` 改为 `10000`。

### Q: Schema 不匹配？
A: 检查 `schema_mode`，使用 `auto_infer` 或更新 `schema_file`。

### Q: 查询性能差？
A: 确保分区路径包含时间字段（year/month/day/hour），支持分区裁剪。

### Q: 压缩不生效？
A: Parquet 使用内部列级压缩，忽略顶层 `compression` 设置。

## Schema 变更行为详解

### auto_infer 模式

#### 增加字段

新字段会自动写入，且可以查询到。

| 批次 | 事件字段 | Parquet Schema |
|------|----------|----------------|
| 批次 1 | `timestamp, level, message` | 3 列 |
| 批次 2 | `timestamp, level, message, user_id` | 4 列 |
| 批次 3 | `timestamp, level, message, user_id, request_id` | 5 列 |

```sql
-- 查询所有字段（包括新增）
SELECT * FROM 's3://logs/**/*.parquet';

| timestamp           | level | message     | user_id | request_id |
|---------------------|-------|-------------|---------|------------|
| 2025-01-15 10:00:00 | INFO  | "Login..."  | 12345   | NULL       |
| 2025-01-15 10:01:00 | INFO  | "Request..."| 67890   | abc-123    |
```

#### 减少字段

新批次中缺失的字段会自动设为 `NULL`。

| 批次 | 事件字段 | Parquet Schema |
|------|----------|----------------|
| 批次 1 | `timestamp, level, message, user_id` | 4 列 |
| 批次 2 | `timestamp, level, message` | 3 列 |

```sql
SELECT * FROM 's3://logs/**/*.parquet';

| timestamp           | level | message     | user_id |
|---------------------|-------|-------------|---------|
| 2025-01-15 10:00:00 | INFO  | "Login..."  | 12345   |
| 2025-01-15 10:01:00 | INFO  | "Request..."| NULL    |  -- user_id 缺失，设为 NULL
```

#### auto_infer 行为总结

| 场景 | 结果 |
|------|------|
| 新字段 | 自动写入 |
| 减少字段 | 旧字段值为 `NULL` |
| 改名字段 | 两个独立列 |

### strict + schema_file 模式

#### 增加字段（日志中出现新字段）

新字段会导致错误，当前批次写入失败。

```yaml
batch_encoding:
  codec: parquet
  schema_mode: strict
  schema_file: /etc/vector/schemas/logs.schema
```

| 场景 | 结果 |
|------|------|
| 日志字段 = Schema | 正常写入 |
| 日志缺少 Schema 字段 | 设为 `NULL` |
| 日志多出字段 | **报错**，批次写入失败 |

错误日志：
```text
Strict schema mode: event contains field 'user_id' not in schema
```

Vector 会**丢弃整个批次**，不会部分写入。

#### 解决方案

| 方案 | 说明 |
|------|------|
| 更新 schema_file | 添加新字段，重启 Vector |
| 改用 relaxed | 静默丢弃新字段 |
| 改用 auto_infer | 自动推断（测试环境） |

#### 生产建议

1. **版本化 schema**：`logs-v1.schema` → `logs-v2.schema`
2. **字段命名规范**：预留扩展字段 `extra_*`
3. **监控告警**：监听 Vector 错误日志

```yaml
# 预留扩展字段
optional group extra {
  optional binary field_1 (STRING);
  optional binary field_2 (STRING);
}
```

## 跨文件 Schema 合并（联合查询）

### 原理

Parquet 文件的 schema 存储在每个文件的 footer 中。DuckDB 查询时会自动合并不同 schema 的文件，缺失字段填充 `NULL`。

### 示例

**旧文件 schema：**
```parquet
message schema {
  optional int64 timestamp;
  optional binary level;
  optional binary message;
}
```

**新文件 schema：**
```parquet
message schema {
  optional int64 timestamp;
  optional binary level;
  optional binary message;
  optional binary user_id;    -- 新增
}
```

### 查询结果

```sql
SELECT * FROM 's3://logs/**/*.parquet';

| timestamp           | level | message     | user_id |
|---------------------|-------|-------------|---------|
| 2025-01-15 10:00:00 | INFO  | "Login..."  | NULL    |  -- 旧文件，无 user_id
| 2025-01-15 10:01:00 | INFO  | "Request..."| 67890   |  -- 新文件，有 user_id
```

### 注意事项

| 特性 | 说明 |
|------|------|
| Schema 存储位置 | 每个 Parquet 文件的 footer |
| 查询时合并 | DuckDB 自动合并所有文件的 schema |
| 缺失字段 | 填充 `NULL` |
| 列类型 | 必须一致，否则报错 |

### 限制

- 列**名称**可以不同（合并为独立列）
- 列**类型**必须兼容（否则查询报错）
- 列的 **重复/可选属性** 应一致

### 查询建议

```sql
-- 查询所有字段
SELECT * FROM 's3://logs/**/*.parquet';

-- 只查询共同字段（避免 NULL）
SELECT timestamp, level, message FROM 's3://logs/**/*.parquet';

-- 按文件过滤（利用分区裁剪）
SELECT * FROM 's3://logs/year=2025/month=01/**/*.parquet';
```

## 三种模式完整对比

| 模式 | Schema 来源 | 增加字段 | 减少字段 | 多余字段 | 适用场景 |
|------|-------------|----------|----------|----------|----------|
| `auto_infer` | 每批自动推断 | 自动写入 | 设为 NULL | N/A | 开发/测试（推荐） |
| `relaxed` | 需要 schema_file | 设为 NULL | 设为 NULL | 静默丢弃 | 灵活场景 |
| `strict` | 需要 schema_file | 设为 NULL | 设为 NULL | **报错** | 生产环境 |

## 跨文件合并能力

| 场景 | 结果 |
|------|------|
| 新增字段 | 自动合并，旧文件填充 NULL |
| 删除字段 | 自动合并，新文件填充 NULL |
| 类型变更 | 查询报错 |
| 重命名字段 | 合并为两列 |
