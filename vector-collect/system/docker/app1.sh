#!/bin/sh
# app1：输出 JSON 行日志（供 docker_logs source + parse_json 演示）
i=0
while true; do
  i=$((i+1))
  printf '{"level":"info","service":"app1","seq":%s,"msg":"heartbeat"}\n' "$i"
  sleep 3
done
