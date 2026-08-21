.headers on
.mode column

-- ============================================================
-- 测试组 1: 文件查询（glob）
-- ============================================================

-- 1.1 日志文件列表（前 20 个文件）
SELECT
    file,
    regexp_extract(file, 'year=([^/]+)', 1) as year,
    regexp_extract(file, 'month=([^/]+)', 1) as month,
    regexp_extract(file, 'day=([^/]+)', 1) as day,
    regexp_extract(file, 'hour=([^/]+)', 1) as hour,
    regexp_extract(file, 'minute=([^/]+)', 1) as minute
FROM glob('s3://log-data/log_json/**/*')
ORDER BY file
LIMIT 20;

-- 1.2 按日期统计文件数
SELECT
    regexp_extract(file, 'year=([^/]+)', 1) as year,
    regexp_extract(file, 'month=([^/]+)', 1) as month,
    regexp_extract(file, 'day=([^/]+)', 1) as day,
    count(*) as files
FROM glob('s3://log-data/log_json/**/*')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ============================================================
-- 测试组 2: 文件内容查询（read_json）
-- ============================================================

-- 2.1 日志内容（前 10 条）
SELECT
    timestamp,
    level,
    message,
    order_id
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={
        'timestamp': 'VARCHAR',
        'level': 'VARCHAR',
        'message': 'VARCHAR',
        'order_id': 'INTEGER'
    }
)
LIMIT 10;

-- 2.2 按日志级别统计
SELECT
    level as log_level,
    count(*) as count
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={
        'timestamp': 'VARCHAR',
        'level': 'VARCHAR',
        'message': 'VARCHAR',
        'order_id': 'INTEGER'
    }
)
GROUP BY 1
ORDER BY 2 DESC;

-- 2.3 最新日志（按时间倒序，前 10 条）
SELECT
    timestamp,
    level,
    message,
    order_id
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={
        'timestamp': 'VARCHAR',
        'level': 'VARCHAR',
        'message': 'VARCHAR',
        'order_id': 'INTEGER'
    }
)
ORDER BY timestamp DESC
LIMIT 10;

-- 2.4 错误日志（最近 20 条）
SELECT
    timestamp,
    message,
    order_id
FROM read_json('s3://log-data/log_json/**/*.log.gz',
    format='newline_delimited',
    columns={
        'timestamp': 'VARCHAR',
        'level': 'VARCHAR',
        'message': 'VARCHAR',
        'order_id': 'INTEGER'
    }
)
WHERE level = 'ERROR'
ORDER BY timestamp DESC
LIMIT 20;

-- 2.5 按日期统计日志条数
SELECT
    regexp_extract(file, 'year=([^/]+)', 1) as year,
    regexp_extract(file, 'month=([^/]+)', 1) as month,
    regexp_extract(file, 'day=([^/]+)', 1) as day,
    count(*) as total_events
FROM glob('s3://log-data/log_json/**/*.log.gz')
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- ============================================================
-- 测试组 3: Parquet 查询
-- ============================================================

-- 3.1 使用分区列过滤
SELECT
    timestamp,
    level,
    year,
    month,
    day,
    hour
FROM read_parquet('s3://log-data/log_parquet/**/*.parquet')
WHERE year = '2026' AND month = '08' AND day = '20' AND hour = '07'
LIMIT 10;

-- 3.2 按分区列统计
SELECT
    year,
    month,
    day,
    hour,
    count(*) as count
FROM read_parquet('s3://log-data/log_parquet/**/*.parquet')
GROUP BY 1, 2, 3, 4
ORDER BY 1, 2, 3, 4;
