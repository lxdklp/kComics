#!/bin/sh

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

# 日志路径
LOG_DIR=$SCRIPT_DIR/logs
LOG_FILE=$SCRIPT_DIR/logs/kcomics.log

# 创建日志目录
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi
: > "$LOG_FILE"

setsid /bin/sh "$SCRIPT_DIR/kcomics.sh"
