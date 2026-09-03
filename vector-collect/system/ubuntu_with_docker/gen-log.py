#!/usr/bin/env python3
"""模拟 Ubuntu /var/log/syslog：systemd/kernel/sshd/cron 等系统日志"""
import os
import random
import time
from datetime import datetime, timezone

LOG_PATH = os.environ.get("LOG_PATH", "/logs/syslog.log")
INTERVAL = float(os.environ.get("INTERVAL", "2"))

HOSTS = ["ubuntu", "web-01"]
KERNEL_MSGS = [
    "[123456.789012] eth0: Link is Up - 1Gbps/Full",
    "[123457.123456] TCP: request_sock_TCP: Possible SYN flooding on port 80. Sending cookies.",
    "[123458.345678] EXT4-fs (sda1): mounted filesystem with ordered data mode",
]
SYSTEMD_UNITS = [
    "nginx.service",
    "cron.service",
    "docker.service",
    "ssh.service",
    "systemd-journald.service",
]
SSHD_MSGS = [
    "Server listening on 0.0.0.0 port 22.",
    "Received disconnect from 198.51.100.7 port 51234:11: disconnected by user",
    "Connection closed by authenticating user alice 192.0.2.15 port 41234 [preauth]",
]


def syslog_ts() -> str:
    now = datetime.now(timezone.utc)
    day = f" {now.day}" if now.day < 10 else str(now.day)
    return now.strftime("%b") + f" {day} {now.strftime('%H:%M:%S')}"


def gen_line() -> str:
    host = random.choice(HOSTS)
    kind = random.random()
    pid = random.randint(100, 9999)
    if kind < 0.25:
        return f"{syslog_ts()} {host} kernel:{random.choice(KERNEL_MSGS)}"
    if kind < 0.5:
        unit = random.choice(SYSTEMD_UNITS)
        action = random.choice(["Started", "Stopped", "Reloading"])
        if action == "Reloading":
            return f"{syslog_ts()} {host} systemd[1]: Reloading {unit}..."
        return f"{syslog_ts()} {host} systemd[1]: {action} {unit}."
    if kind < 0.75:
        return f"{syslog_ts()} {host} sshd[{pid}]: {random.choice(SSHD_MSGS)}"
    if kind < 0.9:
        return (
            f"{syslog_ts()} {host} systemd-logind[{random.randint(100, 999)}]: "
            f"New session {random.randint(1, 99)} of user alice."
        )
    return f"{syslog_ts()} {host} dhclient[{pid}]: DHCPACK from 10.0.0.1"


def main() -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    print(f"[gen-log] writing syslog events to {LOG_PATH} every {INTERVAL}s", flush=True)
    while True:
        with open(LOG_PATH, "a") as f:
            line = gen_line()
            f.write(line + "\n")
            print(line, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
