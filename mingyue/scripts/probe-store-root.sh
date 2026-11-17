#!/data/data/com.termux/files/usr/bin/sh
# 查附件存储实际解析出的根路径，以及 save 里怎么写文件。只读。
set -u

D="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules/@deepseek-ai/dsh"
cd "$D" || exit 1

echo "== resolveDshHome(undefined) 解析出什么 =="
node --input-type=module -e "
import { resolveDshHome, dshHomePath, dshCachePath } from '@deepseek-ai/dsh-home-paths';
import { join } from 'node:path';
const h = resolveDshHome(undefined);
console.log('  dshHome =', h);
console.log('  root    =', join(h, 'attachments', 'v1'));
console.log('  cache   =', dshCachePath({ dshHome: h }, 'attachments'));
" 2>&1 | tail -5

echo
echo "== attachment-local 里所有 fs 写操作 =="
A="$D/node_modules/@deepseek-ai/dsh-attachment-local/lib/index.js"
grep -n -E "mkdir|writeFile|createWriteStream|rename|open\(|realpath|statfs|tmpdir" "$A" 2>/dev/null | head -25

echo
echo "== client-file-upload 的 save() =="
F="$D/node_modules/@deepseek-ai/dsh-client-file-upload/lib/index.js"
sed -n '300,335p' "$F" 2>/dev/null

echo
echo "== 引擎进程的工作目录 =="
P=$(cat ~/.dsh-app-remote/web.pid 2>/dev/null || true)
if [ -n "${P:-}" ]; then
  ls -l "/proc/$P/cwd" 2>/dev/null || echo "  读不到 cwd"
fi
