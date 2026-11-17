#!/data/data/com.termux/files/usr/bin/sh
# 测 yt-dlp 的 B 站搜索与弹幕下载能力（只读，不下载视频）。
# 用法：sh probe-bilibili-search.sh [关键词]
set -u

KW="${1:-新番}"

echo "== 1. B 站搜索（yt-dlp 的 bilisearch:）=="
yt-dlp --no-warnings --flat-playlist --playlist-end 5 \
  --print "%(title)s || %(url)s" \
  "bilisearch:${KW}" 2>&1 | head -10

echo
echo "== 2. 弹幕能不能下（不碰视频流）=="
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp/mingyue-danmaku-test"
rm -rf "$TMP"; mkdir -p "$TMP" || exit 1
if yt-dlp --no-warnings --skip-download --write-subs --sub-langs "danmaku" \
     -o "$TMP/%(id)s.%(ext)s" "https://www.bilibili.com/video/BV1GJ411x7h7" >/dev/null 2>&1; then
  F=$(ls -1 "$TMP" 2>/dev/null | head -1)
  if [ -n "${F:-}" ]; then
    echo "  拿到：$F（$([ -f "$TMP/$F" ] && wc -c < "$TMP/$F" || echo '?') 字节）"
    echo "  前几条弹幕文本："
    # 弹幕 XML：<d p="...">文本</d>
    sed -n 's/.*<d [^>]*>\([^<]*\)<\/d>.*/\1/p' "$TMP/$F" 2>/dev/null | head -8 | sed 's/^/    /'
  else
    echo "  没拿到文件"
  fi
else
  echo "  失败"
fi
rm -rf "$TMP"

echo
echo "== 3. 评论接口（不需登录试试）=="
BV="BV1GJ411x7h7"
AID=$(curl -s -m 10 "https://api.bilibili.com/x/web-interface/view?bvid=$BV" | sed -n 's/.*"aid":\([0-9]*\).*/\1/p' | head -1)
echo "  aid=$AID"
if [ -n "${AID:-}" ]; then
  curl -s -m 10 "https://api.bilibili.com/x/v2/reply?type=1&oid=$AID&sort=2&ps=3" \
    | sed -n 's/.*"message":"\([^"]\{1,80\}\)".*/  热评: \1/p' | head -3
fi
