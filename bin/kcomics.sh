#!/bin/sh
LOG_DIR=/mnt/us/extensions/kcomics/bin/logs
LOG_FILE="$LOG_DIR/kcomics.log"
PAUSE_LIST="/tmp/kcomics_paused_pids"
FB_DEV="/dev/fb0"
FB_SNAPSHOT="/tmp/kcomics_fb.bin"
PYTHON=/mnt/us/python3/bin/python3.14
KCOMICS_DIR=/mnt/us/extensions/kcomics/bin

export LD_LIBRARY_PATH=$KCOMICS_DIR/lib:$LD_LIBRARY_PATH
export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

mkdir -p "$LOG_DIR" 2>/dev/null || true
: > "$LOG_FILE"

log() {
    echo "[运行脚本] $*" >> "$LOG_FILE"
}

# 扫描打开了 /dev/fb0 文件描述符的进程
find_fb_users() {
    for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
        fd_dir="/proc/$pid/fd"
        [ -d "$fd_dir" ] || continue
        for fd in "$fd_dir"/*; do
            [ -L "$fd" ] || continue
            target=$(readlink "$fd" 2>/dev/null)
            if [ "$target" = "$FB_DEV" ]; then
                echo "$pid"
                break
            fi
        done
    done | sort -u
}

# 暂停占用 /dev/fb0 的进程并把 PID 保存到 PAUSE_LIST
pause_fb_users() {
    rm -f "$PAUSE_LIST"
    touch "$PAUSE_LIST"
    log "正在查找占用 $FB_DEV 的进程..."
    found=0
    for pid in $(find_fb_users); do
        # 基本检查
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # 避免暂停自身
            if [ "$pid" -eq $$ ]; then
                log "跳过自身进程 pid=$pid"
                continue
            fi
            log "暂停 pid=$pid($(cat /proc/$pid/comm 2>/dev/null || echo 未知))"
            kill -STOP "$pid" 2>>"$LOG_FILE" || log "向 $pid 发送 SIGSTOP 失败"
            echo "$pid" >> "$PAUSE_LIST"
            found=1
        fi
    done

    if [ $found -eq 0 ]; then
        log "未发现占用 $FB_DEV 的进程"
    else
        log "已暂停的 PID 列表保存到 $PAUSE_LIST"
    fi
}

# 从 PAUSE_LIST 恢复被暂停的进程
resume_fb_users() {
    if [ ! -f "$PAUSE_LIST" ]; then
        log "未找到暂停列表($PAUSE_LIST)无需恢复"
        return
    fi
    while read -r pid; do
        [ -z "$pid" ] && continue
        if kill -0 "$pid" 2>/dev/null; then
            log "恢复 pid=$pid($(cat /proc/$pid/comm 2>/dev/null || echo 未知))"
            kill -CONT "$pid" 2>>"$LOG_FILE" || log "向 $pid 发送 SIGCONT 失败"
        else
            log "PID $pid 已不存在,跳过"
        fi
    done < "$PAUSE_LIST"
    rm -f "$PAUSE_LIST"
}

# 保存当前屏幕内容到快照文件
save_snapshot() {
    log "正在保存屏幕快照..."
    "$PYTHON" "$KCOMICS_DIR/fb_snapshot.py" save "$FB_SNAPSHOT" >>"$LOG_FILE" 2>&1
    if [ -f "$FB_SNAPSHOT" ]; then
        log "屏幕快照已保存到 $FB_SNAPSHOT"
    else
        log "屏幕快照保存失败"
    fi
}

# 把快照写回屏幕
restore_snapshot() {
    if [ ! -f "$FB_SNAPSHOT" ]; then
        log "未找到屏幕快照($FB_SNAPSHOT),跳过还原"
        return
    fi
    log "正在还原屏幕快照..."
    "$PYTHON" "$KCOMICS_DIR/fb_snapshot.py" restore "$FB_SNAPSHOT" >>"$LOG_FILE" 2>&1
    rm -f "$FB_SNAPSHOT"
    log "屏幕还原完成"
}
# 确保退出时恢复
on_exit() {
    log "启动器退出,尝试恢复 framebuffer 占用进程..."
    restore_snapshot
    resume_fb_users
    reload_modules
    log "恢复完成."
}
trap 'on_exit' INT TERM EXIT

# 主流程
log "正在启动 kComics"

# 暂停所有实际占用 /dev/fb0 的进程
pause_fb_users

# 保存当前系统画面
save_snapshot

usleep 300000

# 运行应用
"$PYTHON" "$KCOMICS_DIR/kcomics.py" >> "$LOG_FILE" 2>&1
RET=$?
usleep 500000
restore_snapshot
resume_fb_users
log "kComics 已退出,返回码 $RET"
trap - INT TERM EXIT
exit $RET
