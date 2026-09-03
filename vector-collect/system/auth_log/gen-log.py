#!/usr/bin/env python3
"""模拟 /var/log/auth.log：sshd 登录(成功/失败)、sudo 提权、cron、systemd-logind 事件"""
import os
import random
import time
from datetime import datetime, timezone

LOG_PATH = os.environ.get("LOG_PATH", "/logs/auth.log")
INTERVAL = float(os.environ.get("INTERVAL", "2"))

HOSTS = ["ubuntu", "web-01", "debian-12"]
USERS = ["root", "admin", "alice", "deploy", "bob"]
ATTACK_IPS = ["203.0.113.5", "203.0.113.66", "198.51.100.23"]
GOOD_IPS = ["198.51.100.7", "192.0.2.15"]
CRON_CMDS = [
    "command -v debian-sa1 > /dev/null && debian-sa1 1 1",
    "test -x /usr/sbin/anacron || run-parts /etc/cron.daily",
    "cd / && run-parts --report /etc/cron.hourly",
]


def syslog_ts() -> str:
    now = datetime.now(timezone.utc)
    day = f" {now.day}" if now.day < 10 else str(now.day)
    return now.strftime("%b") + f" {day} {now.strftime('%H:%M:%S')}"


def gen_line() -> str:
    host = random.choice(HOSTS)
    kind = random.random()
    pid = random.randint(1000, 9999)
    if kind < 0.35:  # sshd 登录失败(暴力破解模拟)
        user = random.choice(USERS)
        prefix = "invalid user " if random.random() < 0.6 else ""
        ip = random.choice(ATTACK_IPS)
        return (
            f"{syslog_ts()} {host} sshd[{pid}]: Failed password for {prefix}{user} "
            f"from {ip} port {random.randint(40000, 60000)} ssh2"
        )
    if kind < 0.55:  # sshd 登录成功
        ip = random.choice(GOOD_IPS)
        return (
            f"{syslog_ts()} {host} sshd[{pid}]: Accepted password for "
            f"{random.choice(USERS)} from {ip} port {random.randint(40000, 60000)} ssh2"
        )
    if kind < 0.7:  # 会话打开/关闭
        user = random.choice(USERS)
        action = random.choice(["opened", "closed"])
        return (
            f"{syslog_ts()} {host} sshd[{pid}]: pam_unix(sshd:session): session {action} "
            f"for user {user} by (uid=0)"
        )
    if kind < 0.85:  # sudo 提权
        user = random.choice(["alice", "deploy", "bob"])
        return (
            f"{syslog_ts()} {host} sudo:   {user} : TTY=pts/0 ; PWD=/home/{user} ; "
            f"USER=root ; COMMAND=/usr/bin/apt update"
        )
    if kind < 0.95:  # cron
        return f"{syslog_ts()} {host} CRON[{pid}]: (root) CMD ({random.choice(CRON_CMDS)})"
    # systemd-logind
    user = random.choice(USERS)
    return f"{syslog_ts()} {host} systemd-logind[{random.randint(100, 999)}]: New session 42 of user {user}."


def main() -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    print(f"[gen-log] writing auth events to {LOG_PATH} every {INTERVAL}s", flush=True)
    while True:
        with open(LOG_PATH, "a") as f:
            line = gen_line()
            f.write(line + "\n")
            print(line, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
