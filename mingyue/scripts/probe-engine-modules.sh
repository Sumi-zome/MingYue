#!/data/data/com.termux/files/usr/bin/sh
# 探明引擎侧模块能否加载（附件相关的模块加载失败会导致 RPC 根本不存在）。
# 只读，不起服务。
set -u

NODE_ROOT="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules"
DSH_DIR="$NODE_ROOT/@deepseek-ai/dsh"

[ -d "$DSH_DIR" ] || { echo "找不到 $DSH_DIR"; exit 1; }
cd "$DSH_DIR" || exit 1

echo "== 引擎目录 =="
pwd

try() {
  name="$1"
  node -e "
    try { require('$name'); console.log('  OK   $name'); }
    catch (e) {
      console.log('  FAIL $name');
      console.log('       ' + String(e && e.message || e).split('\n')[0]);
    }
  " 2>&1 | tail -3
}

echo
echo "== 附件相关模块能否加载 =="
for m in sharp @deepseek-ai/dsh-attachment-local @deepseek-ai/dsh-client-file-upload @deepseek-ai/dsh-storage-domain @deepseek-ai/dsh-storage; do
  try "$m"
done

echo
echo "== 最近的启动日志 =="
ls -1t ~/.dsh/logs 2>/dev/null | head -3

NEWEST=$(ls -1t ~/.dsh/logs/*.log 2>/dev/null | head -1)
if [ -n "${NEWEST:-}" ]; then
  echo
  echo "== 最新日志里的错误行（$NEWEST）=="
  grep -n -i -E 'error|fail|cannot|throw' "$NEWEST" 2>/dev/null | head -15 || echo "  没有错误行"
fi

echo
echo "== attachments 目录状态 =="
ls -la ~/.dsh/attachments 2>/dev/null || echo "  不存在"
