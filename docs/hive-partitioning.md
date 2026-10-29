# Hive Partitioning 测试文档

> 背景：DuckDB 对 Hive 风格分区（key=value 目录）的自动检测与分区裁剪实测记录。
> 场景与结论：设计对象存储日志的分区层级时参考；实测 auto 检测无需显式 hive_partitioning=true。

## 概述

Hive Partitioning 是一种数据组织方式，将数据按目录结构分区存储。DuckDB 自动检测 `key=value` 格式的目录，并将分区列添加到查询结果中。

## 目录结构

```text
s3://log-data/log_json/
├── year=2026/
│   └── month=08/
│       └── day=20/
│           ├── hour=06/
│           │   ├── minute=42/
│           │   │   └── *.log.gz
│           │   └── minute=46/
│           │       └── *.log.gz
│           └── hour=07/
│               └── ...
```

## 自动检测机制

DuckDB 默认 `hive_partitioning=auto-detected`：
- 路径包含 `key=value` 目录 → 自动启用
- 路径不包含 → 不启用
- **无需手动设置 `hive_partitioning=true`**

## 测试步骤

### 1. 验证自动检测

```sql
-- 查看分区列是否自动添加
DESCRIBE SELECT * FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={'timestamp': 'VARCHAR', 'level': 'VARCHAR'}
) LIMIT 1;

-- 预期结果包含：year, month, day, hour, minute 列
```

### 2. 使用分区列查询

```sql
-- 按分区列过滤
SELECT timestamp, level, year, month, day, hour
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={'timestamp': 'VARCHAR', 'level': 'VARCHAR'}
)
WHERE year = '2026' AND month = '08' AND day = '20' AND hour = '07'
LIMIT 10;
```

### 3. 按分区列聚合

```sql
-- 按小时统计日志数量
SELECT year, month, day, hour, count(*) as count
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={'timestamp': 'VARCHAR', 'level': 'VARCHAR'}
)
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;
```

### 4. 验证分区裁剪

```sql
-- EXPLAIN 查询查看扫描文件数
EXPLAIN SELECT count(*)
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={'timestamp': 'VARCHAR', 'level': 'VARCHAR'}
)
WHERE year = '2026' AND month = '08' AND day = '20' AND hour = '07';

-- 预期：Scanning Files 显示部分文件（非全部）
```

## 测试结果示例

| 测试项 | 预期结果 |
|--------|----------|
| 自动检测 | DESCRIBE 显示 year, month, day, hour, minute 列 |
| 分区过滤 | 只返回匹配条件的行 |
| 分区聚合 | 按分区列分组统计 |
| 分区裁剪 | EXPLAIN 显示 Scanning Files < 总文件数 |

## 注意事项

1. **不要设置 `hive_partitioning=true`**：默认自动检测，设置后反而可能影响其他格式文件
2. **分区列类型**：
   - `year`, `month`, `day`, `hour`, `minute` → VARCHAR
   - 如果目录名是日期格式（如 `date=2026-08-20`）→ 自动解析为 DATE 类型
3. **分区键命名**：使用 snake_case（如 `year`, `month`），避免 camelCase

## 常见问题

### Q: 为什么查询结果没有分区列？
A: 检查路径是否包含 `key=value` 格式目录。例如：
- ✅ `s3://bucket/data/year=2026/month=08/`
- ❌ `s3://bucket/data/2026/08/`

### Q: 如何禁用自动检测？
A: 设置 `hive_partitioning=false`：
```sql
SELECT * FROM read_json('s3://.../*.json', hive_partitioning=false);
```

### Q: 分区列支持哪些数据类型？
A: 
- 字符串格式 `key=value` → VARCHAR
- 日期格式 `date=2026-08-20` → DATE
- 数字格式 `id=123` → INTEGER
