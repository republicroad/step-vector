#!/usr/bin/env python3
"""模拟 UFW 防火墙日志：内核 netfilter 的 [UFW BLOCK]/[UFW ALLOW] 事件"""
import os
import random
import time
from datetime import datetime, timezone

LOG_PATH = os.environ.get("LOG_PATH", "/logs/ufw.log")
INTERVAL = float(os.environ.get("INTERVAL", "2"))

HOSTS = ["ubuntu", "web-01"]
BLOCK_IPS = ["203.0.113.5", "203.0.113.66", "192.0.2.99", "198.51.100.23"]
ALLOW_IPS = ["198.51.100.7", "192.0.2.15"]
DST_IP = "10.0.0.2"
TCP_DPORTS = [22, 80, 443, 3306, 6379, 23]
UDP_DPORTS = [53, 123, 161]


def syslog_ts() -> str:
    now = datetime.now(timezone.utc)
    day = f" {now.day}" if now.day < 10 else str(now.day)
    return now.strftime("%b") + f" {day} {now.strftime('%H:%M:%S')}"


def gen_line() -> str:
    host = random.choice(HOSTS)
    action = "BLOCK" if random.random() < 0.8 else "ALLOW"
    src = random.choice(BLOCK_IPS if action == "BLOCK" else ALLOW_IPS)
    if action == "BLOCK":
        # 80% 打向 23/3306/6379 等敏感端口，模拟扫描与爆破
        dport = random.choice([23, 3306, 6379, 8080, random.randint(10000, 65000)])
    else:
        dport = random.choice([22, 80, 443])
    proto = random.choice(["TCP", "UDP"]) if action == "ALLOW" else "TCP"
    base = (
        f"{syslog_ts()} {host} kernel:[{random.uniform(1e5, 9e5):.6f}] [UFW {action}] "
        f"IN=eth0 OUT= MAC=02:42:ac:11:00:02:aa:bb:cc:dd:ee:ff:08:00 "
        f"SRC={src} DST={DST_IP} LEN=40 TOS=0x00 PREC=0x00 TTL={random.randint(48, 255)} "
        f"ID={random.randint(1, 65535)} "
    )
    if proto == "TCP":
        base += (
            f"DF PROTO=TCP SPT={random.randint(40000, 60000)} DPT={dport} "
            f"WINDOW=1024 RES=0x00 {'SYN ' if action == 'BLOCK' else 'ACK '}"
        )
    else:
        base += f"PROTO=UDP SPT={random.randint(40000, 60000)} DPT={dport} LEN=28"
    return base


def main() -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    print(f"[gen-log] writing UFW events to {LOG_PATH} every {INTERVAL}s", flush=True)
    while True:
        with open(LOG_PATH, "a") as f:
            line = gen_line()
            f.write(line + "\n")
            print(line, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
