#!/data/data/com.termux/files/usr/bin/sh
# 临时诊断补丁：让 attachment-local 在保存失败时把原始错误打到 stderr（web.log）。
# 用法：
#   sh patch-attachment-log.sh            打补丁
#   sh patch-attachment-log.sh --verify   检查
#   sh patch-attachment-log.sh --rollback 还原
set -u

NODE_ROOT="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules"
TARGET="$NODE_ROOT/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js"
BACKUP_DIR="$HOME/.cache/mingyue/attachment-log-backup"

die() { echo "✗ $*" >&2; exit 1; }
[ -f "$TARGET" ] || die "找不到 $TARGET"
already() { grep -q 'MINGYUE-LOG-PATCH' "$TARGET" 2>/dev/null; }

case "${1:-patch}" in
  --verify) already && echo "✓ 已打" || echo "✗ 未打"; exit 0 ;;
  --rollback)
    [ -f "$BACKUP_DIR/index.js" ] || die "没有备份"
    cp "$BACKUP_DIR/index.js" "$TARGET" && echo "✓ 已还原" || die "还原失败"
    exit 0 ;;
esac

if already; then echo "已经打过，跳过"; exit 0; fi

mkdir -p "$BACKUP_DIR" || die "建备份目录失败"
cp "$TARGET" "$BACKUP_DIR/index.js" || die "备份失败"
echo "✓ 备份到 $BACKUP_DIR/index.js"

python3 - "$TARGET" <<'PY'
import sys, io
path = sys.argv[1]
src = io.open(path, encoding="utf-8").read()

needle = 'throw new AttachmentError("Unable to persist attachment.", "ATTACHMENT_WRITE_FAILED", { cause: error });'
n = src.count(needle)
if n < 1:
    print("✗ 一处都没找到；文件版本可能不同", file=sys.stderr)
    sys.exit(2)

repl = (
    'console.error("[MINGYUE-LOG-PATCH] persist failed:", error && error.code, "|", error && error.message);\n'
    '                console.error("[MINGYUE-LOG-PATCH] stack:", error && error.stack);\n'
    '                throw new AttachmentError("Unable to persist attachment.", "ATTACHMENT_WRITE_FAILED", { cause: error });'
)
src = src.replace(needle, repl)
io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("✓ 已插入诊断日志（%d 处）" % n)
PY
[ $? -eq 0 ] || { cp "$BACKUP_DIR/index.js" "$TARGET"; die "替换失败，已还原"; }

echo
echo "✓ 完成。下一步："
echo "  1) 在 App 里重启托管的 DSH"
echo "  2) sh ~/mingyue/scripts/probe-upload.sh"
echo "  3) tail -40 ~/.dsh-app-remote/web.log   ← 真实错误在 MINGYUE-LOG-PATCH 那行"
