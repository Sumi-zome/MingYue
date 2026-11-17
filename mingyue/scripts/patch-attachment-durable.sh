#!/data/data/com.termux/files/usr/bin/sh
# 修 attachment-local 的 "向上 fsync 所有祖先目录" 行为（Android 上 /data/data 不可读）。
#
# 用法：
#   sh patch-attachment-durable.sh           打补丁（先备份）
#   sh patch-attachment-durable.sh --verify  检查当前是否已打
#   sh patch-attachment-durable.sh --rollback 还原
set -u

NODE_ROOT="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules"
DSH_DIR="$NODE_ROOT/@deepseek-ai/dsh"
TARGET="$DSH_DIR/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js"
# 备份按 DSH 版本隔离：升级后旧备份不会被误还原进新版本
VERSION="$(node -p "require('$DSH_DIR/package.json').version" 2>/dev/null || echo unknown)"
BACKUP_DIR="$HOME/.cache/mingyue/attachment-durable-backup-$VERSION"

die() { echo "✗ $*" >&2; exit 1; }

[ -f "$TARGET" ] || die "找不到 $TARGET"

already() { grep -q 'MINGYUE-DURABLE-PATCH' "$TARGET" 2>/dev/null; }

case "${1:-patch}" in
  --verify)
    if already; then echo "✓ 已打补丁"; else echo "✗ 未打补丁"; fi
    exit 0 ;;
  --rollback)
    [ -f "$BACKUP_DIR/index.js" ] || die "没有备份：$BACKUP_DIR"
    cp "$BACKUP_DIR/index.js" "$TARGET" || die "还原失败"
    echo "✓ 已还原"
    exit 0 ;;
esac

if already; then
  echo "已经打过补丁，跳过。要重打请先 --rollback。"
  exit 0
fi

mkdir -p "$BACKUP_DIR" || die "建备份目录失败"
cp "$TARGET" "$BACKUP_DIR/index.js" || die "备份失败"
echo "✓ 备份到 $BACKUP_DIR/index.js"

python3 - "$TARGET" <<'PY'
import sys, io

path = sys.argv[1]
src = io.open(path, encoding="utf-8").read()

needle = 'const handle = await open(path, constants.O_RDONLY);'
count = src.count(needle)
if count != 1:
    print("✗ 预期 1 处 'open(path, O_RDONLY)'，实际 %d 处；不冒险，退出" % count, file=sys.stderr)
    sys.exit(2)

replacement = (
    'let handle; /* MINGYUE-DURABLE-PATCH: Android 上 /data/data 不可读，目录 fsync 改成尽力而为 */\n'
    '        try {\n'
    '                handle = await open(path, constants.O_RDONLY);\n'
    '        } catch (error) {\n'
    '                const code = error && error.code;\n'
    '                if (code === "EACCES" || code === "EPERM" || code === "ENOENT") return;\n'
    '                throw error;\n'
    '        }'
)
src = src.replace(needle, replacement, 1)
io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("✓ 已替换 1 处")
PY

[ $? -eq 0 ] || { cp "$BACKUP_DIR/index.js" "$TARGET"; die "替换失败，已还原"; }

echo
echo "== 语法检查 =="
node --input-type=module -e "await import('file://$TARGET'); console.log('  模块可加载')" 2>&1 | tail -3

echo
echo "✓ 完成。下一步：在 App 里重启托管的 DSH，再试发附件。"
echo "  回滚：sh patch-attachment-durable.sh --rollback"
