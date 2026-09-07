import datetime
import json
import os
import random
import time

from kafka import KafkaProducer

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC = os.environ.get("KAFKA_TOPIC", "app-logs")

LEVELS = ["INFO", "INFO", "WARN", "ERROR"]

# 东八区（北京时间）：固定 +08:00 偏移，无夏令时；zoneinfo 需系统 tzdata，
# 固定偏移写法在任意环境下都可用，isoformat() 会输出 +08:00
UTC8 = datetime.timezone(datetime.timedelta(hours=8), name="UTC+8")

# ===== 晚到日志模拟配置 =====
# LATE_RATIO：晚到日志比例（0~1）
# LATE_MAX_BACKFILL_SECONDS：时间戳最大回填时长（秒），事件时间将早于处理时间
# 晚到日志用于验证「事件时间分区」：处理时间为当前，但 OSS 目录按回填后的旧时间分割
LATE_RATIO = 0.3
LATE_MAX_BACKFILL_SECONDS = 12 * 3600


def rfc3339(ts: datetime.datetime) -> str:
    # RFC3339：2026-08-14T14:50:15.893+08:00（东八区）
    return ts.isoformat(timespec="milliseconds")


def connect() -> KafkaProducer:
    """连接 broker 并等待 topic 可用（kafka-python 惰性建连，需主动拉元数据）。"""
    while True:
        try:
            producer = KafkaProducer(
                bootstrap_servers=BOOTSTRAP,
                value_serializer=lambda v: v.encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8"),
                linger_ms=200,       # 攒 200ms 批量发送，提高吞吐
                acks="all",          # 所有 ISR 副本确认才算发送成功
            )
            # partitions_for 拉取元数据：broker 未就绪时抛 NoBrokersAvailable，
            # topic 未建时返回 None（broker 端 auto-create 也在这里触发）
            if producer.partitions_for(TOPIC):
                print(f"connected to {BOOTSTRAP}, topic {TOPIC} ready", flush=True)
                return producer
            print(f"topic {TOPIC} not ready yet, retrying...", flush=True)
        except Exception as e:
            print(f"kafka not ready ({e}), retrying in 2s...", flush=True)
        time.sleep(2)


def main() -> None:
    producer = connect()
    while True:
        now = datetime.datetime.now(UTC8)

        # 晚到模拟：部分日志时间戳回填到过去（发送时刻为当前，事件时间为旧时间）
        if random.random() < LATE_RATIO:
            ts = now - datetime.timedelta(
                seconds=random.uniform(0, LATE_MAX_BACKFILL_SECONDS)
            )
            tag = " [late]"
        else:
            ts = now
            tag = ""

        order_id = random.randint(10000, 99999)
        rec = {
            "timestamp": rfc3339(ts),
            "level": random.choice(LEVELS),
            "message": "test log" + tag,
            "order_id": order_id,
        }
        # key=order_id：同 key 恒定进同一分区，保证单订单事件在分区内局部有序
        producer.send(TOPIC, key=str(order_id), value=json.dumps(rec)).add_errback(
            lambda e: print(f"send failed: {e}", flush=True)
        )
        time.sleep(0.2)  # 约 5 条/秒


if __name__ == "__main__":
    main()
