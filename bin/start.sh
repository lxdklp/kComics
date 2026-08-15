#!/bin/sh

# 日志路径
LOG_DIR=/mnt/us/extensions/kcomics/bin/logs
LOG_FILE=/mnt/us/extensions/kcomics/bin/logs/kcomics.log

# 创建日志目录
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
fi
: > "$LOG_FILE"

setsid /bin/sh /mnt/us/extensions/kcomics/bin/kcomics.sh
