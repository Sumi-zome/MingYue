#!/usr/bin/env bash
# 溟月 · 随机早安入口：在 08:00–10:30 里随机挑一刻投递到用户会话（逻辑在 ping.py）。
#
# 每天 00:05 由定时任务「溟月·安排早安」调用：
#   bash ~/mingyue/scripts/morning-schedule.sh
#
# 用法见 `--help` / docs/mingyue/PROACTIVE.md。
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
home_dir=${MINGYUE_HOME:-$HOME/mingyue}
exec python3 "$here/ping.py" --config "$home_dir/morning.json" "$@"
