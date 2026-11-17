#!/data/data/com.termux/files/usr/bin/sh
# 查 sharp 版本与 libvips 可用性，判断"能否从源码重建"。
# 只读，不改任何东西。
set -u

echo "== 基础 =="
uname -m
echo "node=$(node -v 2>/dev/null || echo 无)"

NODE_ROOT=$(npm root -g 2>/dev/null || true)
SHARP_DIR="$NODE_ROOT/@deepseek-ai/dsh/node_modules/sharp"
echo "sharp 目录=$SHARP_DIR"

if [ -d "$SHARP_DIR" ]; then
  echo "sharp 版本=$(node -p "require('$SHARP_DIR/package.json').version" 2>/dev/null || echo 读不到)"
  echo "--- 它自带的平台包（@img/*）---"
  ls -1 "$SHARP_DIR/node_modules/@img" 2>/dev/null || echo "  （没有 @img，可能是 0.32 及更早）"
else
  echo "找不到 sharp 目录"
fi

echo
echo "== libvips =="
if command -v pkg-config >/dev/null 2>&1; then
  echo "pkg-config vips 版本=$(pkg-config --modversion vips 2>/dev/null || echo 未安装)"
else
  echo "pkg-config 未安装"
fi
echo "--- 已安装的 vips 相关包 ---"
pkg list-installed 2>/dev/null | grep -i vips || echo "  没有"
echo "--- 可安装的 vips 包 ---"
pkg list-all 2>/dev/null | grep -i '^libvips' || echo "  仓库里没找到 libvips"

echo
echo "== 编译工具 =="
for c in clang make python3 pkg-config; do
  if command -v "$c" >/dev/null 2>&1; then echo "  [有] $c"; else echo "  [无] $c"; fi
done

echo
echo "== 结论提示 =="
echo "  sharp 0.33+ 且 libvips >= 8.15  → 值得试（链系统库）"
echo "  sharp 0.32 及更早               → 要自建 libvips，成功率低"
