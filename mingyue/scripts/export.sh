#!/usr/bin/env bash
# 溟月 · 导出（备份 = 迁移包）
# 用法：export.sh [--out DIR] [--plain]
#   默认加密：需要 age 公钥（AGE_RECIPIENT_FILE，默认 ~/.config/mingyue/age.pub）
#   --plain 跳过加密（仅调试用，别留在机器上）
set -euo pipefail

MINGYUE_HOME="${MINGYUE_HOME:-$HOME/mingyue}"
OUT_DIR="${HOME}/backups"
RECIPIENT_FILE="${AGE_RECIPIENT_FILE:-$HOME/.config/mingyue/age.pub}"
KEEP="${KEEP:-14}"
PLAIN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT_DIR="$2"; shift 2 ;;
    --plain) PLAIN=1; shift ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "未知参数: $1" >&2; exit 2 ;;
  esac
done

[ -d "$MINGYUE_HOME" ] || { echo "找不到 $MINGYUE_HOME" >&2; exit 1; }
mkdir -p "$OUT_DIR"

# 平台与版本
if [ -n "${PREFIX:-}" ] && [ "${PREFIX#*com.termux}" != "$PREFIX" ]; then
  PLATFORM=termux
else
  PLATFORM=linux
fi
DSH_VERSION="$(dsh --version 2>/dev/null | head -1 || true)"
DSH_VERSION="${DSH_VERSION:-unknown}"

# Termux 里 hostname 是 localhost，读机型更有辨识度
HOSTID="${MINGYUE_HOST:-$(getprop ro.product.model 2>/dev/null | tr -d '\r' || true)}"
[ -n "$HOSTID" ] || HOSTID="$(hostname 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"

# manifest：写进她的家，随包一起走
SCHED_JSON="$(
  cd "$MINGYUE_HOME" && ls -1 schedules/*.md 2>/dev/null \
    | sed 's/.*/"&"/' | paste -sd, - || true
)"
cat > "$MINGYUE_HOME/manifest.json" <<JSON
{
  "schema": 1,
  "exported_at": "$(date -Iseconds)",
  "host": "${HOSTID}",
  "arch": "${ARCH}",
  "platform": "${PLATFORM}",
  "dsh_version": "${DSH_VERSION}",
  "workspace": "${MINGYUE_HOME}",
  "schedules": [${SCHED_JSON}],
  "ntfy": { "topic": "mingyue", "port": 8090 }
}
JSON

TS="$(date +%Y%m%d-%H%M)"
BASE="mingyue-${TS}.tar.zst"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# 打包：排除 SQLite 的 wal/shm 与原始语料归档
tar -C "$(dirname "$MINGYUE_HOME")" \
    --exclude="$(basename "$MINGYUE_HOME")/archive" \
    --exclude="$(basename "$MINGYUE_HOME")/tmp" \
    --exclude='*.db-wal' --exclude='*.db-shm' \
    -cf - "$(basename "$MINGYUE_HOME")" | zstd -19 -T0 -q -o "$STAGE/$BASE"

FINAL="$OUT_DIR/$BASE"
if [ "$PLAIN" -eq 0 ]; then
  [ -f "$RECIPIENT_FILE" ] || {
    echo "缺少 age 公钥：$RECIPIENT_FILE" >&2
    echo "先生成密钥对（在 PC 上）：age-keygen -o ~/.config/mingyue/age.key" >&2
    echo "再把公钥放到这台机器上；或加 --plain 只做本地调试" >&2
    exit 1
  }
  command -v age >/dev/null || { echo "没有安装 age" >&2; exit 1; }
  age -R "$RECIPIENT_FILE" -o "$OUT_DIR/$BASE.age" "$STAGE/$BASE"
  FINAL="$OUT_DIR/$BASE.age"
  echo "已加密：$FINAL"
else
  cp "$STAGE/$BASE" "$FINAL"
  echo "⚠️  未加密：$FINAL"
fi

( cd "$OUT_DIR" && sha256sum "$(basename "$FINAL")" > "$(basename "$FINAL").sha256" )

# 只保留最近 KEEP 份加密包
ls -1t "$OUT_DIR"/mingyue-*.tar.zst* 2>/dev/null \
  | tail -n +$((KEEP + 1)) \
  | while IFS= read -r old; do rm -f "$old" "$old.sha256"; done

echo "完成。包大小：$(du -h "$FINAL" | cut -f1)"
