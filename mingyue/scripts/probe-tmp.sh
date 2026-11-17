#!/data/data/com.termux/files/usr/bin/sh
# 检查临时目录：Node 的 os.tmpdir() 在 Android 上可能指向不存在的 /tmp。
set -u

echo "== 系统临时目录 =="
ls -ld /tmp 2>/dev/null || echo "  /tmp 不存在"
echo "TMPDIR=${TMPDIR:-（未设置）}"
echo "TMP=${TMP:-（未设置）}"
ls -ld "${PREFIX:-/data/data/com.termux/files/usr}/tmp" 2>/dev/null || echo "  \$PREFIX/tmp 不存在"

echo
echo "== Node 看到的 tmpdir =="
node -e "const os=require('os'); const fs=require('fs'); const t=os.tmpdir(); console.log('os.tmpdir() =', t); console.log('存在？', fs.existsSync(t));"

echo
echo "== 往 tmpdir 写一个文件试试 =="
node -e "
const os=require('os'); const fs=require('fs'); const path=require('path');
const t=os.tmpdir();
try {
  const f=path.join(t,'mingyue-tmp-probe');
  fs.writeFileSync(f,'ok');
  fs.unlinkSync(f);
  console.log('写临时文件: OK');
} catch (e) {
  console.log('写临时文件: FAIL ->', e.code || '', e.message.split('\n')[0]);
}
"

echo
echo "== 当前引擎进程的环境里有没有 TMPDIR =="
P=$(cat ~/.dsh-app-remote/web.pid 2>/dev/null || true)
if [ -n "${P:-}" ] && [ -r "/proc/$P/environ" ]; then
  tr '\0' '\n' < "/proc/$P/environ" | grep -i -E '^(TMPDIR|TMP|HOME|PATH)=' || echo "  读到了但没匹配"
else
  echo "  读不到 /proc/$P/environ（Android 限制，正常）"
fi
