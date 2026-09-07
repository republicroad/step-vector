#!/usr/bin/env python3
"""
模拟 SLS 日志生成器：生成符合 SLS Kafka 协议格式的 JSON 日志，发送到 Kafka topic
用于本地测试 vector-sls-test.yaml 配置

环境变量：
- KAFKA_BOOTSTRAP: Kafka bootstrap servers (默认 localhost:9092)
- KAFKA_TOPIC: 目标 topic (默认 app-logs)
- LATE_RATIO: 晚到日志比例 (默认 0.3)
- LATE_MAX_BACKFILL_SECONDS: 最大回填秒数 (默认 12h)
"""

import os
import json
import random
import time
import datetime
from kafka import KafkaProducer

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "app-logs")
LATE_RATIO = float(os.environ.get("LATE_RATIO", "0.3"))
LATE_MAX_BACKFILL_SECONDS = int(os.environ.get("LATE_MAX_BACKFILL_SECONDS", "43200"))

# 业务字段模拟（贴近真实 SLS Kafka 消费的多字段日志 value 结构）
# 注：真实 SLS 消费的消息体没有 __topic__/__source__/__timestamp__ 等保留字段，
#     SLS 写入时间以 Kafka 消息的 .offset/.partition 等元数据 + 日志自身字段为准
# 东八区（北京时间）：固定 +08:00 偏移，无夏令时，任意环境可用
UTC8 = datetime.timezone(datetime.timedelta(hours=8), name="UTC+8")

LEVELS = ["INFO", "INFO", "INFO", "WARN", "ERROR"]


def beijing_naive(ts: datetime.datetime) -> str:
    """模拟存量项目的裸格式时间：2026-09-07 17:09:55,994（北京时间，无时区后缀）。

    Vector 的 parse_sls transform 会把该裸格式按北京时间解释，
    并为事件规范化生成 ts 字段（RFC3339），生产者无需输出 ts。
    """
    ms = ts.microsecond // 1000
    return ts.strftime("%Y-%m-%d %H:%M:%S") + f",{ms:03d}"


def connect() -> KafkaProducer:
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP,
                value_serializer=lambda v: v.encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
                linger_ms=200,
                acks="all",
            )
            if producer.partitions_for(TOPIC):
                print(f"connected to {BOOTSTRAP}, topic {TOPIC} ready", flush=True)
                return producer
            print(f"topic {TOPIC} not ready yet, retrying...", flush=True)
        except Exception as e:
            print(f"kafka not ready ({e}), retrying in 2s...", flush=True)
        time.sleep(2)


def main() -> None:
    producer = connect()
    print(f"Starting SLS log generator -> topic: {TOPIC}, late_ratio={LATE_RATIO}", flush=True)
    
    while True:
        now = datetime.datetime.now(UTC8)
        
        # 晚到模拟：部分日志时间戳回填到过去
        if random.random() < LATE_RATIO:
            ts = now - datetime.timedelta(
                seconds=random.uniform(0, LATE_MAX_BACKFILL_SECONDS)
            )
            late_tag = " [late]"
        else:
            ts = now
            late_tag = ""
        
        rec = {
            # 业务字段（多字段日志 → SLS Kafka 消费 value 为 JSON 编码内容）
            # 注意：ts (RFC3339) 不由生产者输出，由 Vector transform 规范化生成
            "timestamp": beijing_naive(ts),
            "level": random.choice(LEVELS),
            "message": f"test log{late_tag}",
            "order_id": random.randint(10000, 99999),
            "service": "test-service",
        }
        
        # key 可选：用于分区分发
        key = str(random.randint(10000, 99999))
        producer.send(TOPIC, key=key, value=json.dumps(rec)).add_errback(
            lambda e: print(f"send failed: {e}", flush=True)
        )
        
        time.sleep(0.5)  # 约 2 条/秒


if __name__ == "__main__":
    main()