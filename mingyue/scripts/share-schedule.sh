#!/usr/bin/env bash
# 溟月 · 主动分享入口：两个窗口各随机挑一刻投递到用户会话（逻辑在 ping.py）。
#
# 每天 00:10 由定时任务「溟月·安排分享」调用：
#   bash ~/mingyue/scripts/share-schedule.sh
#
# 用法见 `--help` / docs/mingyue/PROACTIVE.md。
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
home_dir=${MINGYUE_HOME:-$HOME/mingyue}
exec python3 "$here/ping.py" --config "$home_dir/share.json" "$@"
