#!/data/data/com.termux/files/usr/bin/sh
# 验证 session/search（会话历史搜索）是否可用。
#
# 前提：profile 里 session-query-sqlite 已配 path + openAt: first-search，
# 并且【重启过托管的 DSH】。
#
# 用法：sh probe-search.sh "关键词"
set -u

QUERY="${1:-测试}"
LOG="$HOME/.dsh-app-remote/web.log"
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp"
JAR="$TMP/mingyue-search-cookie.txt"
OUT="$TMP/mingyue-search-result.json"

LINE=$(grep -o 'http://127\.0\.0\.1:[0-9]*/?token=[A-Za-z0-9_-]*' "$LOG" 2>/dev/null | tail -1)
[ -n "${LINE:-}" ] || { echo "✗ 找不到启动行（引擎没在跑？）"; exit 1; }
PORT=$(echo "$LINE" | sed -n 's|.*127\.0\.0\.1:\([0-9]*\)/?token=.*|\1|p')
TOKEN=$(echo "$LINE" | sed -n 's|.*token=\([A-Za-z0-9_-]*\)$|\1|p')
BASE="http://127.0.0.1:$PORT"

echo "== 引擎 =="
echo "  端口 $PORT"

CODE=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" "$BASE/?token=$TOKEN")
echo "  登录 -> $CODE"
case "$CODE" in 200|301|302|303) ;; *) echo "✗ 登录失败"; exit 1 ;; esac

echo
echo "== session/search 查询「$QUERY」=="
BODY=$(printf '{"type":"client-request","rpcId":"probe-search-1","method":"session/search","payload":{"args":{"request":{"query":"%s"}}}}' "$QUERY")
CODE=$(curl -s -o "$OUT" -w '%{http_code}' -b "$JAR" \
  -H 'Content-Type: application/json' -X POST "$BASE/api/session/search" --data "$BODY")
echo "  HTTP $CODE"
echo "  响应（前 600 字）："
head -c 600 "$OUT" 2>/dev/null | sed 's/^/    /'
echo
echo
echo "== 判读 =="
if grep -q 'session search is disabled' "$OUT" 2>/dev/null; then
  echo "  ✗ 索引没开：配置没生效（重启引擎了吗？）或 patch 没被合进 profile"
elif grep -q '"ok":true' "$OUT" 2>/dev/null; then
  N=$(grep -o '"sessionId"' "$OUT" 2>/dev/null | wc -l)
  echo "  ✓ 搜索可用，命中 $N 个会话"
else
  echo "  ⚠ 看上面的原始响应判断（可能是 0 命中：FTS5 unicode61 对中文只按整段匹配）"
fi
