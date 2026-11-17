#!/data/data/com.termux/files/usr/bin/sh
# 探明 yt-dlp 能不能读 B 站视频的元数据和字幕。
# 只读：不下载视频。
#
# 用法：sh probe-bilibili.sh [视频URL]
set -u

URL="${1:-https://www.bilibili.com/video/BV1GJ411x7h7}"

echo "== URL =="
echo "  $URL"

echo
echo "== 元数据（不下载）=="
yt-dlp --no-warnings --skip-download \
  --print "标题: %(title)s" \
  --print "UP主: %(uploader)s" \
  --print "时长: %(duration)s 秒" \
  --print "简介: %(description).200s" \
  "$URL" 2>&1 | head -12

echo
echo "== 可用字幕 =="
yt-dlp --no-warnings --skip-download --list-subs "$URL" 2>&1 | head -15

echo
echo "== 能不能只下字幕（不碰视频流）=="
TMP="${PREFIX:-/data/data/com.termux/files/usr}/tmp/mingyue-subs-test"
mkdir -p "$TMP" || exit 1
if yt-dlp --no-warnings --skip-download --write-subs --write-auto-subs \
     --sub-langs "zh.*" --sub-format "vtt/srt/best" \
     -o "$TMP/%(id)s.%(ext)s" "$URL" >/dev/null 2>&1; then
  FOUND=$(ls -1 "$TMP" 2>/dev/null | head -3)
  if [ -n "$FOUND" ]; then
    echo "  拿到字幕文件："
    echo "$FOUND" | sed 's/^/    /'
    FIRST=$(ls -1 "$TMP"/* | head -1)
    echo "  前 5 行内容："
    head -5 "$FIRST" 2>/dev/null | sed 's/^/    /'
  else
    echo "  没有字幕文件（该视频可能没有字幕，或需要登录 cookie）"
  fi
else
  echo "  字幕下载失败（可能需要登录 cookie：SESSDATA）"
fi
rm -rf "$TMP"
