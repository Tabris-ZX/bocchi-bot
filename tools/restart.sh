#!/bin/bash
# 终止所有 bocchi 相关进程（launcher + worker）
pkill -f 'bocchi.cli' 2>/dev/null
sleep 1

# 确保 8081 端口已释放
for i in $(seq 1 10); do
    if ! ss -tlnp | grep -q ':8081[[:space:]]'; then
        break
    fi
    # 如果还有进程占用，强制杀掉
    pid=$(ss -tlnp | grep ':8081[[:space:]]' | grep -oP 'pid=\K[0-9]+' | head -1)
    [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
    sleep 1
done

cd /home/zx/work/bot && uv run zx
