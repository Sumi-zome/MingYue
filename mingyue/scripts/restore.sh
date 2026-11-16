#!/usr/bin/env bash
# 溟月 · 恢复（在新主机上把她的家放回去）
# 用法：restore.sh [--yes] ARCHIVE
#   支持 .tar.zst 与 .tar.zst.age；有同名 .sha256 会先校验。
set -euo pipefail

ASSUME_YES=0
ARCHIVE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) ARCHIVE="$1"; shift ;;
  esac
done
[ -n "$ARCHIVE" ] && [ -f "$ARCHIVE" ] || { echo "用法：restore.sh [--yes] ARCHIVE" >&2; exit 2; }

TARGET="${MINGYUE_HOME:-$HOME/mingyue}"

# 1. 校验
if [ -f "$ARCHIVE.sha256" ]; then
  ( cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256" ) \
    || { echo "校验失败：文件损坏或被改过" >&2; exit 1; }
else
  echo "⚠️  没有 .sha256，跳过校验"
fi

# 2. 解密
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
IN="$ARCHIVE"
case "$ARCHIVE" in
  *.age)
    command -v age >/dev/null || { echo "没有安装 age" >&2; exit 1; }
    KEYFILE="${AGE_IDENTITY_FILE:-$HOME/.config/mingyue/age.key}"
    [ -f "$KEYFILE" ] || { echo "缺少私钥：$KEYFILE" >&2; exit 1; }
    age -d -i "$KEYFILE" -o "$STAGE/plain.tar.zst" "$ARCHIVE"
    IN="$STAGE/plain.tar.zst"
    ;;
esac

# 3. 解包
zstd -d -q -c "$IN" | tar -C "$STAGE" -xf -
SRC="$STAGE/$(basename "$TARGET")"
[ -d "$SRC" ] || { echo "包里没有 $(basename "$TARGET")/ 目录" >&2; exit 1; }

# 4. 换入（旧的先留一份）
if [ -d "$TARGET" ]; then
  BAK="${TARGET}.bak-$(date +%Y%m%d-%H%M%S)"
  if [ "$ASSUME_YES" -ne 1 ]; then
    printf '将把现有 %s 移到 %s，然后写入新数据。继续？[y/N] ' "$TARGET" "$BAK"
    read -r answer
    case "$answer" in y|Y|yes|YES) ;; *) echo "已取消"; exit 1 ;; esac
  fi
  mv "$TARGET" "$BAK"
  echo "旧数据保留在：$BAK"
fi
mkdir -p "$(dirname "$TARGET")"
mv "$SRC" "$TARGET"

# 5. 完整性
if command -v sqlite3 >/dev/null && [ -f "$TARGET/memory.db" ]; then
  result="$(sqlite3 "$TARGET/memory.db" 'PRAGMA integrity_check;' || true)"
  [ "$result" = "ok" ] || { echo "memory.db 完整性检查失败：$result" >&2; exit 1; }
  echo "memory.db integrity_check: ok"
fi

if [ -f "$TARGET/scripts/mem.py" ] && command -v python3 >/dev/null; then
  python3 "$TARGET/scripts/mem.py" check || echo "⚠️  mem.py check 未通过（阶段 B 之前没有这个文件属正常）"
fi

# 6. 还需要人做的
cat <<'NEXT'

恢复完成。还需要手动做三件事：
  1) 重建定时任务：把 schedules/SETUP.md 贴给这台主机上的 agent
  2) 起服务：termux 用 ~/.termux/boot/server；linux 用 systemctl --user enable --now mingyue-dsh
  3) App 里加这台主机的 SSH 条目，然后连上去新建一个对话

回滚：把 mingyue.bak-* 改回 mingyue 即可（30 秒）。
NEXT
