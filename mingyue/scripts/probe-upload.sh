#!/data/data/com.termux/files/usr/bin/sh
# 直接打引擎的两个上传端点，拿服务端原始错误。
# 只读：不发消息、不改会话，只上传一个 5 字节的探针文件。
set -u

LOG="$HOME/.dsh-app-remote/web.log"
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp"
JAR="$TMP/mingyue-cookie.txt"
OUT="$TMP/mingyue-upload-probe.json"

LINE=$(grep -o 'http://127\.0\.0\.1:[0-9]*/?token=[A-Za-z0-9_-]*' "$LOG" 2>/dev/null | tail -1)
[ -n "${LINE:-}" ] || { echo "找不到启动行（$LOG）"; exit 1; }
PORT=$(echo "$LINE" | sed -n 's|.*127\.0\.0\.1:\([0-9]*\)/?token=.*|\1|p')
TOKEN=$(echo "$LINE" | sed -n 's|.*token=\([A-Za-z0-9_-]*\)$|\1|p')
BASE="http://127.0.0.1:$PORT"

echo "== 引擎 =="
echo "  端口 $PORT"

echo
echo "== 换取 cookie =="
CODE=$(curl -s -o /dev/null -w '%{http_code}' -c "$JAR" "$BASE/?token=$TOKEN")
echo "  GET /?token=… -> $CODE"
case "$CODE" in
  200|301|302|303) ;;
  *) echo "  登录失败，停止"; exit 1 ;;
esac
if grep -q 'dsh-auth' "$JAR" 2>/dev/null; then
  echo "  cookie 已拿到"
else
  echo "  cookie 没拿到（jar: $JAR）"; exit 1
fi

SID=$(ls -1 "$HOME/.dsh/sessions"/*/ 2>/dev/null | head -1 | sed 's|.*/\([^/]*\)/$|\1|')
[ -n "${SID:-}" ] || { echo "  找不到会话 id"; exit 1; }
echo "  用会话 $SID"

echo
echo "== ① 二进制上传 POST /api/session/uploadFileBinary =="
CODE=$(curl -s -o "$OUT" -w '%{http_code}' -b "$JAR" -X POST \
  "$BASE/api/session/uploadFileBinary?sessionId=$SID&name=probe.txt" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary 'hello')
echo "  HTTP $CODE"
echo "  响应："
head -c 800 "$OUT" 2>/dev/null | sed 's/^/    /'
echo

echo
echo "== ② RPC 上传 POST /api/fileUploads/upload =="
CODE=$(curl -s -o "$OUT" -w '%{http_code}' -b "$JAR" \
  -H 'Content-Type: application/json' -X POST "$BASE/api/fileUploads/upload" \
  --data '{"type":"client-request","rpcId":"probe-1","method":"fileUploads/upload","payload":{"args":{"request":{"data":"aGVsbG8=","name":"probe.txt"}}}}')
echo "  HTTP $CODE"
echo "  响应："
head -c 800 "$OUT" 2>/dev/null | sed 's/^/    /'
echo
