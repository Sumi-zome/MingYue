#!/data/data/com.termux/files/usr/bin/sh
# 统计所有会话头里的 cwd 分布（判断 App 的默认工作区到底是哪个）。
# 只读。
set -u

ROOT="${1:-$HOME/.dsh/sessions}"

echo "== 会话根 =="
echo "  $ROOT"

echo
echo "== cwd 分布 =="
find "$ROOT" -name 'session.v4.jsonl.zstd' 2>/dev/null | while read -r f; do
  zstd -dc "$f" 2>/dev/null | head -1
done | grep -o '"cwd":"[^"]*"' | sed 's/^"cwd":"//; s/"$//' | sort | uniq -c | sort -rn

echo
echo "== 会话总数 =="
find "$ROOT" -name 'session.v4.jsonl.zstd' 2>/dev/null | wc -l
