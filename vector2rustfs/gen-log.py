import datetime
import json
import random
import time

LOGFILE = "/logs/app.log"

LEVELS = ["INFO", "INFO", "WARN", "ERROR"]

# 东八区（北京时间）：固定 +08:00 偏移，无夏令时
UTC8 = datetime.timezone(datetime.timedelta(hours=8), name="UTC+8")

# ===== 晚到日志模拟配置 =====
LATE_RATIO = 0.3
LATE_MAX_BACKFILL_SECONDS = 12 * 3600


def rfc3339(ts: datetime.datetime) -> str:
    return ts.isoformat(timespec="milliseconds")


def main() -> None:
    while True:
        now = datetime.datetime.now(UTC8)

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
        time.sleep(0.2)


if __name__ == "__main__":
    main()
