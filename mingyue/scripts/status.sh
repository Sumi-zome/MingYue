#!/usr/bin/env bash
# 溟月 · 状态自检：sshd、DSH 引擎、她的家
# 用法：ssh mingyue "bash ~/mingyue/scripts/status.sh"
set -uo pipefail

STATE="${HOME}/.dsh-app-remote"
HOSTDIR="${MINGYUE_HOME:-$HOME/mingyue}"

echo "== 主机 =="
uname -srm 2>/dev/null || echo unknown

echo
echo "== sshd（入口）=="
if ps -ef 2>/dev/null | grep -v grep | grep -q '[s]shd'; then
  echo "在跑"
else
  echo "没在跑（重启后应该由 ~/.termux/boot/server 拉起）"
fi

echo
echo "== DSH 引擎 =="
PID=""
[ -f "$STATE/web.pid" ] && PID="$(cat "$STATE/web.pid" 2>/dev/null || true)"
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  echo "进程在跑：PID $PID（App 托管启动）"
elif ps -ef 2>/dev/null | grep -v grep | grep -q 'dsh web'; then
  echo "有 dsh web 进程，但不是 App 托管记录里的那个 PID"
else
  echo "没在跑 —— 打开 App 连一次即可拉起"
fi

# 真实端口在启动行里；只取端口，不打印 token
PORT="$(grep -o 'http://127\.0\.0\.1:[0-9][0-9]*' "$STATE/web.log" 2>/dev/null | tail -1 | grep -o '[0-9][0-9]*$' || true)"
if [ -n "${PORT:-}" ]; then
  CODE="$(curl -s -o /dev/null -m 5 -w '%{http_code}' "http://127.0.0.1:${PORT}/" 2>/dev/null || echo 000)"
  echo "监听端口 ${PORT} → http:${CODE}"
else
  echo "web.log 里没有启动行（引擎可能还没被拉起过）"
fi

echo
echo "== 她的家 =="
if [ -d "$HOSTDIR" ]; then
  du -sh "$HOSTDIR" 2>/dev/null || true
  ls -1 "$HOSTDIR" 2>/dev/null | head -20
else
  echo "目录不存在：$HOSTDIR"
fi

echo
echo "== 备份 =="
ls -1t "$HOME"/backups/mingyue-* 2>/dev/null | head -3 || echo "还没有备份"

echo
echo "== Termux 兼容补丁（附件/图片能不能用）=="
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$HERE/fix-termux.sh" ]; then
  bash "$HERE/fix-termux.sh" --check 2>&1 | sed 's/^/  /'
else
  echo "  找不到 fix-termux.sh（补丁脚本没同步过来？）"
fi
