#!/data/data/com.termux/files/usr/bin/sh
# 修：Android 上 fs.link() 报 EACCES，导致附件保存失败。
# 做法：硬链接失败时退化为复制文件。
#
# 用法：
#   sh patch-attachment-link.sh            打补丁
#   sh patch-attachment-link.sh --verify   检查
#   sh patch-attachment-link.sh --rollback 还原
set -u

NODE_ROOT="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules"
TARGET="$NODE_ROOT/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js"
BACKUP_DIR="$HOME/.cache/mingyue/attachment-link-backup"

die() { echo "✗ $*" >&2; exit 1; }
[ -f "$TARGET" ] || die "找不到 $TARGET"
already() { grep -q '_mingyueLink' "$TARGET" 2>/dev/null; }

case "${1:-patch}" in
  --verify) already && echo "✓ 已打" || echo "✗ 未打"; exit 0 ;;
  --rollback)
    [ -f "$BACKUP_DIR/index.js" ] || die "没有备份"
    cp "$BACKUP_DIR/index.js" "$TARGET" && echo "✓ 已还原（去掉了 link 补丁）" || die "还原失败"
    exit 0 ;;
esac

if already; then
  echo "检测到已打过（可能是有 bug 的旧版）——先回滚再打："
  echo "  sh $0 --rollback"
  echo "  sh $0"
  exit 0
fi

mkdir -p "$BACKUP_DIR" || die "建备份目录失败"
# 备份只建一次，避免把坏补丁备份进去
if [ ! -f "$BACKUP_DIR/index.js" ]; then
  cp "$TARGET" "$BACKUP_DIR/index.js" || die "备份失败"
  echo "✓ 备份到 $BACKUP_DIR/index.js"
else
  echo "✓ 备份已存在，复用"
fi

python3 - "$TARGET" <<'PY'
import sys, io
path = sys.argv[1]
src = io.open(path, encoding="utf-8").read()

imp = 'import { chmod, link, mkdir, open, readFile, rename, rm, unlink, writeFile } from "node:fs/promises";'
if imp not in src:
    print("✗ 找不到预期的 import 行；文件版本不同", file=sys.stderr)
    sys.exit(2)

# 关键：原本的 link 换成别名 _mingyueFsLink，这样 helper 里调用它不会自递归。
new_imp = 'import { chmod, copyFile, link as _mingyueFsLink, mkdir, open, readFile, rename, rm, unlink, writeFile } from "node:fs/promises";'
src = src.replace(imp, new_imp, 1)

helper = new_imp + '''

/* MINGYUE-LINK-PATCH: Android 上 fs.link() 会 EACCES，退化为复制文件。 */
const _mingyueLink = async (from, to) => {
        try {
                await _mingyueFsLink(from, to);
        } catch (error) {
                const code = error && error.code;
                if (code === "EACCES" || code === "EPERM" || code === "ENOSYS" || code === "EXDEV" || code === "EMLINK") {
                        await copyFile(from, to);
                        return;
                }
                throw error;
        }
};'''
src = src.replace(new_imp, helper, 1)

n = src.count('await link(')
if n < 1:
    print("✗ 没找到 await link( 调用", file=sys.stderr)
    sys.exit(2)
# helper 里用的是 _mingyueFsLink，不会被这条替换命中
src = src.replace('await link(', 'await _mingyueLink(')

io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("✓ 已改 %d 处硬链接为容错版（helper 不会自递归）" % n)
PY
[ $? -eq 0 ] || { cp "$BACKUP_DIR/index.js" "$TARGET"; die "替换失败，已还原"; }

echo
echo "== 自检：helper 里必须是 _mingyueFsLink，不能是 _mingyueLink =="
grep -n -A6 'const _mingyueLink' "$TARGET" | sed 's/^/  /' | head -10

echo
echo "== 模块可加载吗 =="
node --input-type=module -e "await import('file://$TARGET'); console.log('  OK')" 2>&1 | tail -3

echo
echo "✓ 完成。下一步："
echo "  1) App 里重启托管的 DSH"
echo "  2) sh ~/mingyue/scripts/probe-upload.sh   ← 预期 ok:true"
echo "  3) App 里发一张图试试"
