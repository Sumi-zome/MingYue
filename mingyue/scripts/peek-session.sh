#!/data/data/com.termux/files/usr/bin/sh
# 探明 DSH 会话文件结构。
# 只打印「字段名」和「记录类型计数」，**不打印任何消息正文** —— 输出可以直接贴给别人看。
#
# 用法：
#   sh peek-session.sh                 # 最新的会话文件
#   sh peek-session.sh <file>          # 指定文件
#   sh peek-session.sh --all           # 只统计每个会话属于哪个工作区目录

set -u

SESSROOT="${HOME}/.dsh/sessions"

if [ "${1:-}" = "--all" ]; then
  echo "== 所有工作区目录与会话数 =="
  for d in "$SESSROOT"/*/; do
    [ -d "$d" ] || continue
    n=$(ls -1 "$d" 2>/dev/null | wc -l)
    echo "  $(basename "$d")  →  $n 个会话"
  done
  exit 0
fi

if [ -n "${1:-}" ] && [ -f "${1:-}" ]; then
  f="$1"
else
  f=$(ls -1t "$SESSROOT"/*/*/session.v4.jsonl.zstd 2>/dev/null | head -1)
fi
[ -n "${f:-}" ] || { echo "找不到会话文件（$SESSROOT/*/*/session.v4.jsonl.zstd）"; exit 1; }

echo "== 文件 =="
echo "  $f"
echo "  解压后 $(zstd -dc "$f" 2>/dev/null | wc -l) 行"

echo "== 前 3 条记录的字段名 =="
zstd -dc "$f" 2>/dev/null | head -3 | python3 -c '
import sys, json
for i, line in enumerate(sys.stdin, 1):
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        print("  第%d行不是 JSON（前 60 字符）：%s" % (i, line[:60]))
        continue
    print("  第%d行字段：%s" % (i, sorted(obj.keys())))
'

echo "== 记录类型分布（前 3000 行）=="
zstd -dc "$f" 2>/dev/null | head -3000 | python3 -c '
import sys, json, collections
c = collections.Counter()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        c["<not-json>"] += 1
        continue
    c[str(obj.get("type") or obj.get("kind") or "<no-type>")] += 1
for k, v in c.most_common(15):
    print("  %s: %d" % (k, v))
'

echo "== 可能的工作区字段 =="
zstd -dc "$f" 2>/dev/null | head -3000 | python3 -c '
import sys, json
flat, nested = set(), set()
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if not isinstance(obj, dict):
        continue
    flat.update(obj.keys())
    for v in obj.values():
        if isinstance(v, dict):
            nested.update(v.keys())
cands = ("workspace", "workspaceRoot", "cwd", "root", "dir", "path", "project")
hit_flat = [k for k in cands if k in flat]
hit_nested = [k for k in cands if k in nested]
print("  顶层命中：%s" % (hit_flat or "无"))
print("  嵌套命中：%s" % (hit_nested or "无"))
print("  顶层字段全集（供判断）：%s" % sorted(flat))
print("  嵌套字段全集（供判断）：%s" % sorted(nested))
'
