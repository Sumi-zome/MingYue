#!/usr/bin/env bash
# 溟月 · Termux 兼容补丁：一条命令让 DSH 引擎在 Android/Termux 上能收发附件与图片。
#
# 背景（2026-11-17 实测）：上游 DSH 在 Android 上有四处不兼容，
# 都会让"发图片/附件"失败，而且日志里什么都不显示：
#   ① sharp 没有 android-arm64 预编译包（图片解码）
#   ② 落盘前向上 fsync 到文件系统根，撞上不可读的 /data/data
#   ③ 内容寻址用硬链接去重，Android 拒绝 link()
#   ④ 错误被 catch 吞掉，只回一个笼统错误码
#
# 用法：
#   bash fix-termux.sh          应用全部补丁（幂等，失败自动回滚）
#   bash fix-termux.sh --check  只检查状态（升级 dsh 后先跑这个）
#
# 何时跑：`npm i -g @deepseek-ai/dsh` 升级之后**必须重跑一次**，
# 因为升级会覆盖 node_modules 里的补丁与编译产物。
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

D="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules/@deepseek-ai/dsh"
SHARP="$D/node_modules/sharp"
ATT="$D/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js"

pass=0
fail=0
ok()   { echo "  ✓ $*"; pass=$((pass + 1)); }
bad()  { echo "  ✗ $*"; fail=$((fail + 1)); }

echo "== 1. sharp（图片解码）=="
if [ -d "$SHARP" ]; then
  OUT="$(cd "$D" && node -e "require('sharp')({create:{width:8,height:8,channels:3,background:'#f00'}}).png().toBuffer().then(b=>console.log('OK')).catch(e=>console.log('FAIL'))" 2>/dev/null | tail -1)"
  if [ "$OUT" = "OK" ]; then
    ok "sharp 可用"
  else
    bad "sharp 不可用（需从源码编译）"
    [ "$CHECK_ONLY" -eq 0 ] && { echo "     → 运行 build-sharp.sh"; bash "$HERE/build-sharp.sh" || bad "sharp 编译失败"; }
  fi
else
  bad "找不到 sharp 目录：$SHARP"
fi

echo
echo "== 2. 附件存储补丁 =="
if [ -f "$ATT" ]; then
  grep -q 'MINGYUE-DURABLE-PATCH' "$ATT" && ok "durable 补丁（跳过不可读祖先）" || {
    bad "durable 补丁缺失"; [ "$CHECK_ONLY" -eq 0 ] && bash "$HERE/patch-attachment-durable.sh" >/dev/null && ok "durable 补丁已打"
  }
  grep -q 'MINGYUE-LINK-PATCH' "$ATT" && ok "link 补丁（硬链接失败转复制）" || {
    bad "link 补丁缺失"; [ "$CHECK_ONLY" -eq 0 ] && bash "$HERE/patch-attachment-link.sh" >/dev/null && ok "link 补丁已打"
  }
  grep -q 'MINGYUE-LOG-PATCH' "$ATT" && ok "错误日志补丁（失败时打印底层错误）" || {
    bad "错误日志补丁缺失"; [ "$CHECK_ONLY" -eq 0 ] && bash "$HERE/patch-attachment-log.sh" >/dev/null && ok "日志补丁已打"
  }
else
  bad "找不到 $ATT"
fi

echo
echo "== 3. 附件目录 =="
if [ -d "$HOME/.dsh/attachments" ]; then
  ok "~/.dsh/attachments 存在"
else
  mkdir -p "$HOME/.dsh/attachments" && ok "已创建 ~/.dsh/attachments" || bad "建不了 ~/.dsh/attachments"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "全部就绪（$pass 项通过）"
  [ "$CHECK_ONLY" -eq 0 ] && echo "记得在 App 里重启托管的 DSH 让补丁生效。"
  exit 0
fi

echo "有 $fail 项未就绪（$pass 项通过）"
[ "$CHECK_ONLY" -eq 1 ] && echo "运行：bash ~/mingyue/scripts/fix-termux.sh   来修复"
exit 1
