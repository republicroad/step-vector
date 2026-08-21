import datetime
import json
import random
import time

LOGFILE = "/logs/app.log"

LEVELS = ["INFO", "INFO", "WARN", "ERROR"]

# 东八区（北京时间）：固定 +08:00 偏移，无夏令时；zoneinfo 需系统 tzdata，
# 固定偏移写法在任意环境下都可用，isoformat() 会输出 +08:00
UTC8 = datetime.timezone(datetime.timedelta(hours=8), name="UTC+8")

# ===== 晚到日志模拟配置 =====
# LATE_RATIO：晚到日志比例（0~1）
# LATE_MAX_BACKFILL_SECONDS：时间戳最大回填时长（秒），事件时间将早于处理时间
# 晚到日志用于验证「事件时间分区」：处理时间为当前，但目录按回填后的旧时间分割
LATE_RATIO = 0.3
LATE_MAX_BACKFILL_SECONDS = 12 * 3600


def rfc3339(ts: datetime.datetime) -> str:
    # RFC3339：2026-08-14T14:50:15.893+08:00（东八区）
    # isoformat() 对带时区的 datetime 直接输出偏移量（+08:00 与 Z 在 RFC3339 中等价），
    # 不做任何手动字符串替换
    return ts.isoformat(timespec="milliseconds")


def main() -> None:
    while True:
        now = datetime.datetime.now(UTC8)

        # 晚到模拟：部分日志时间戳回填到过去（写入时刻为当前，事件时间为旧时间）
        if random.random() < LATE_RATIO:
            ts = now - datetime.timedelta(
                seconds=random.uniform(0, LATE_MAX_BACKFILL_SECONDS)
            )
            tag = " [late]"
        else:
            ts = now
            tag = ""

        rec = {
            "timestamp": rfc3339(ts),
            "level": random.choice(LEVELS),
            "message": "test log" + tag,
            "order_id": random.randint(10000, 99999),
        }
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        time.sleep(0.2)  # 约 5 行/秒


if __name__ == "__main__":
    main()
