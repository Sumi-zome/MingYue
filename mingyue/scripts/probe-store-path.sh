#!/data/data/com.termux/files/usr/bin/sh
# 查附件存储在算路径时用了什么。只读。
set -u

D="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules/@deepseek-ai/dsh/node_modules"
PKG="$D/@deepseek-ai/dsh-attachment-local"

echo "== 包位置 =="
ls -ld "$PKG" 2>/dev/null || { echo "找不到 $PKG"; exit 1; }
ls -1 "$PKG/lib" 2>/dev/null | head

echo
echo "== 相关环境变量 =="
for v in HOME DSH_HOME TMPDIR PREFIX; do
  eval "echo \"  $v=\${$v:-（未设置）}\""
done

echo
echo "== 模块里与路径有关的行 =="
grep -rn -E "dshHomePath|homedir|attachments|process\.env|path\.(join|resolve|dirname)" \
  "$PKG/lib"/*.js 2>/dev/null | head -30

echo
echo "== Node 的 homedir / tmpdir =="
node -e "const os=require('os');console.log('  homedir=',os.homedir());console.log('  tmpdir=',os.tmpdir())"

echo
echo "== dsh-home-paths 的实现 =="
HP="$D/@deepseek-ai/dsh-home-paths"
if [ -d "$HP" ]; then
  ls -1 "$HP" 2>/dev/null | head
  grep -rn -E "function dshHomePath|DSH_HOME|homedir|\.dsh" "$HP"/lib/*.js "$HP"/index.js 2>/dev/null | head -20
else
  echo "  没有独立的 dsh-home-paths 包"
fi
