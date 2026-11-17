#!/data/data/com.termux/files/usr/bin/sh
# 读一个 B 站视频的公开信号：标题 / UP 主 / 时长 + 弹幕采样 + 热评。
# **免登录、只读**：不下载视频、不碰账号、不发评论。
#
# 用法：
#   sh bili-read.sh <视频链接>
#
# 已知边界（见 docs/mingyue/TROUBLESHOOTING.md / HANDOFF-SHARE.md）：
#   - 有字幕的视频没有登录 cookie 时拿不到 CC 字幕，只能拿弹幕；
#   - 搜索请用她的 web_search 工具，别用 yt-dlp bilisearch:（412 风控）；
#   - 接口会变、会限流：一个视频一次，失败跳过，不要重试轰炸。
set -u

URL="${1:-}"
case "$URL" in
  ""|-h|--help)
    echo "用法: sh bili-read.sh <B站视频链接>"
    exit 0
    ;;
esac

UA="Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"
BV=$(printf '%s' "$URL" | sed -n 's|.*\(BV[0-9A-Za-z]\{10\}\).*|\1|p')
TMP="${TMPDIR:-$HOME/mingyue/tmp}/bili-read-$$"
mkdir -p "$TMP" || exit 1
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "== 元数据 =="
yt-dlp --no-warnings --skip-download \
  --print "标题: %(title)s" \
  --print "UP主: %(uploader)s" \
  --print "时长: %(duration)s 秒" \
  --print "发布: %(upload_date)s" \
  --print "简介: %(description).240s" \
  "$URL" 2>&1 | head -n 12

if [ -z "${BV:-}" ]; then
  echo
  echo "（链接里没识别到 BV 号，跳过弹幕和热评）"
  exit 0
fi

echo
echo "== 弹幕采样 =="
if yt-dlp --no-warnings --skip-download --write-subs --sub-langs danmaku \
  -o "$TMP/%(id)s.%(ext)s" "$URL" >/dev/null 2>&1; then
  F=$(ls -1 "$TMP"/* 2>/dev/null | head -n 1)
  if [ -n "${F:-}" ]; then
    echo "  弹幕文件 $(wc -c <"$F" | tr -d ' ') 字节；采样（前 40 条，按出现顺序）："
    # 弹幕 XML 通常整篇一行：先按 </d> 断行，再逐条取文本。
    sed 's|</d>|</d>\n|g' "$F" 2>/dev/null \
      | sed -n 's|.*<d [^>]*>\([^<]*\)</d>.*|\1|p' \
      | head -n 40 | sed 's/^/    /'
  else
    echo "  没拿到弹幕文件（该视频可能关闭了弹幕）"
  fi
else
  echo "  弹幕下载失败（跳过，不影响分享）"
fi

echo
echo "== 热评（免登录接口，最热 5 条）=="
AID=$(curl -s -m 10 -A "$UA" -e "https://www.bilibili.com" \
  "https://api.bilibili.com/x/web-interface/view?bvid=$BV" \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print(""); raise SystemExit
print((d.get("data") or {}).get("aid") or "")' 2>/dev/null)

if [ -z "${AID:-}" ]; then
  echo "  拿不到 aid（接口失败或被限流），跳过热评"
  exit 0
fi

curl -s -m 10 -A "$UA" -e "https://www.bilibili.com" \
  "https://api.bilibili.com/x/v2/reply?type=1&oid=$AID&sort=2&ps=5" \
  | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("  热评接口返回的不是 JSON（可能被限流）"); raise SystemExit
replies = ((d.get("data") or {}).get("replies") or []) if isinstance(d, dict) else []
if not replies:
    print("  没有热评（新视频或接口限流）")
for r in replies[:5]:
    text = ((r.get("content") or {}).get("message") or "").replace("\n", " ")
    like = r.get("like") or 0
    print("  [赞 %d] %s" % (like, text[:160]))'
