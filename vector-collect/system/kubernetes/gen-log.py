#!/usr/bin/env python3
"""模拟 kubelet 落盘的 /var/log/pods 结构，生成 CRI 格式容器日志"""
import os
import random
import time
from datetime import datetime, timezone

POD_ROOT = os.environ.get("POD_ROOT", "/var/log/pods")
INTERVAL = float(os.environ.get("INTERVAL", "2"))

# (namespace, pod_name, container, uid 后缀)
PODS = [
    ("default", "demo-pod", "demo", "d8b4c0e2-1111-4222-8333-444455556666"),
    ("prod", "api-pod", "api", "a1b2c3d4-5555-4666-8777-888899990000"),
]

PATHS = ["/api/v1/users", "/api/v1/orders", "/healthz"]
LEVELS = ["info", "info", "info", "warn", "error"]


def cri_line() -> str:
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond:09d}" + "+00:00"
    ns, pod, container, _ = random.choice(PODS)
    payload = (
        '{"level":"%s","pod":"%s","msg":"request handled","path":"%s","status":%d}'
        % (random.choice(LEVELS), pod, random.choice(PATHS), random.choice([200, 200, 404, 500]))
    )
    return f"{ts} stdout F {payload}"


def main() -> None:
    files = []
    for ns, pod, container, uid in PODS:
        d = os.path.join(POD_ROOT, f"{ns}_{pod}_{uid}", container)
        os.makedirs(d, exist_ok=True)
        files.append(os.path.join(d, "0.log"))
    print(f"[gen-log] writing CRI logs to {POD_ROOT} every {INTERVAL}s", flush=True)
    while True:
        line = cri_line()
        for f in files:
            with open(f, "a") as fh:
                fh.write(line + "\n")
        print(line, flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
