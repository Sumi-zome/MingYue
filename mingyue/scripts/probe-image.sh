#!/data/data/com.termux/files/usr/bin/sh
# 查主机上图片相关依赖是否可用（Termux/Bionic 最容易在这里翻车）。
# 只读，不改任何东西。
set -u

echo "== 环境 =="
uname -m
echo "PREFIX=$PREFIX"
echo "node=$(node -v 2>/dev/null || echo 无)"

echo
echo "== DSH 安装位置 =="
DSH_BIN=$(command -v dsh 2>/dev/null || true)
echo "dsh=$DSH_BIN"
NODE_ROOT=$(npm root -g 2>/dev/null || true)
echo "npm root=$NODE_ROOT"
DSH_DIR="$NODE_ROOT/@deepseek-ai/dsh"
if [ ! -d "$DSH_DIR" ]; then
  echo "找不到 $DSH_DIR"
  exit 1
fi

echo
echo "== 图片相关依赖（有/无）=="
for name in sharp jimp canvas @napi-rs/canvas image-size probe-image-size; do
  if [ -d "$DSH_DIR/node_modules/$name" ]; then
    echo "  [有] $name"
  else
    echo "  [无] $name"
  fi
done

echo
echo "== 尝试加载 =="
cd "$DSH_DIR" || exit 1
for name in sharp jimp @napi-rs/canvas; do
  node -e "try{require('$name');console.log('$name: OK')}catch(e){console.log('$name: FAIL ->',String(e.message).split('\n')[0])}" 2>&1 | tail -2
done

echo
echo "== 原生模块（.node）清单，前 15 个 =="
find "$DSH_DIR/node_modules" -name '*.node' 2>/dev/null | head -15

echo
echo "== 关键原生模块能否加载 =="
for name in better-sqlite3 koffi; do
  node -e "try{require('$name');console.log('$name: OK')}catch(e){console.log('$name: FAIL ->',String(e.message).split('\n')[0])}" 2>&1 | tail -2
done

echo
echo "== 磁盘与内存 =="
df -h ~ 2>/dev/null | tail -1
grep -E 'MemTotal|MemAvailable' /proc/meminfo 2>/dev/null || echo "读不到 /proc/meminfo"
