# 压缩算法对比：zstd vs snappy（Parquet 场景）

## 概述

Parquet 列存文件的列页内压缩算法选择。Vector `batch_encoding.compression.algorithm` 支持 `zstd` / `snappy` / `gzip` / `lz4` / `none`。本仓库 `source/sls` 生产配置已选 **zstd（level 3）**，本文记录选型依据。

## 对比

| 维度 | zstd | snappy |
|------|------|--------|
| 压缩比 | **高**（同数据通常比 snappy 小 20-35%） | 中等（约为 zstd 的 1.2-1.4 倍体积） |
| 压缩速度 | 中（level 3 约为 snappy 的 1/2~1/3 速度） | **快**（针对低 CPU 开销设计） |
| 解压速度 | **快**（与 snappy 同级甚至更快） | 快 |
| CPU 消耗（写） | 较高，随 level 升高 | 低且稳定 |
| 级别可调 | 有（1-22，粒度细，可平衡速度/体积） | 无 |
| 生态兼容 | Parquet/Arrow/DuckDB/Spark/Athena/EMR 全支持 | 全支持（Parquet 历史默认） |

## 读取侧无需任何配置

压缩级别随 Parquet 文件元数据（footer）自描述：

- **解压不需要 level**：zstd 帧自描述，级别只影响写入时的压缩效率
- **自动识别编码**：DuckDB/Spark/Athena/EMR 从 footer 读取每列的 codec，透明解压
- **混存兼容**：同一前缀下 snappy（存量）与 zstd（新增）文件可混合查询，DuckDB 联合读取无感

```sql
-- 无需任何压缩相关参数，直接查询
SELECT * FROM 's3://bucket/sls/log_parquet/**/*.parquet';
```

## 选择逻辑

| 场景 | 推荐 |
|------|------|
| 日志/时序类、写一次读多次、存储成本敏感 | **zstd** |
| 极低延迟写入、CPU 紧张、数据短生命周期 | snappy |
| 冷归档、极致压缩比 | zstd 高级别（9+，写入 CPU 陡增需评估） |

**本仓库选型**（source/sls）：写入侧 batch 5 分钟才 flush 一次，压缩耗时相对 300s 窗口可忽略；读取侧两者解压速度相当。净收益即存储与下游扫描流量省 ~20-30%，故选 zstd level 3。

## Vector 配置

```yaml
batch_encoding:
  codec: parquet
  schema_mode: auto_infer
  compression:
    algorithm: zstd
    level: 3     # Vector 0.58 要求 zstd 必须显式配置 level（无默认值），否则启动报
                 # "missing field `level`"；snappy 无此要求
```

> 顶层 `compression`（如 JSON sink 的 gzip）对 parquet `batch_encoding` 无效，启动时会提示
> "Top level compression setting ignored"，属预期 WARN。

## JSON 输出的压缩

JSON sink（`raw_message` + `newline_delimited`）仍用 `compression: gzip`：gzip 在下游
`read_json` / 常规文本工具链兼容性最好，且 JSON 文件本就用于人工查看/临时取数，压缩速度优先。

## 相关文档

- [Vector Parquet 最佳实践](VECTOR_PARQUET_BEST_PRACTICES.md)
- [Hive Partitioning](HIVE_PARTITIONING.md)
- source/sls README「OSS 写入最佳实践」小节
