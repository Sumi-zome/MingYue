#!/data/data/com.termux/files/usr/bin/sh
# 从源码重建 DSH 自带的 sharp（Termux 上没有 android-arm64 预编译包）。
#
# 用法：
#   sh build-sharp.sh            重建（先备份，失败可 --rollback）
#   sh build-sharp.sh --verify   只验证当前 sharp 能否加载
#   sh build-sharp.sh --rollback 还原到备份
#
# 只动 sharp 这一个目录，不碰 DSH 其它部分。

set -u

NODE_ROOT="${PREFIX:-/data/data/com.termux/files/usr}/lib/node_modules"
DSH_DIR="$NODE_ROOT/@deepseek-ai/dsh"
SHARP_DIR="$DSH_DIR/node_modules/sharp"
BACKUP_DIR="$HOME/.cache/mingyue/sharp-backup"

die() { echo "✗ $*" >&2; exit 1; }

verify() {
  [ -d "$SHARP_DIR" ] || die "sharp 目录不存在：$SHARP_DIR"
  echo "== 验证 sharp =="
  ( cd "$DSH_DIR" && node -e "
    try {
      const sharp = require('sharp');
      sharp({ create: { width: 8, height: 8, channels: 3, background: '#ff0000' } })
        .png().toBuffer()
        .then(b => { console.log('OK bytes=' + b.length); process.exit(0); })
        .catch(e => { console.log('FAIL ' + e.message); process.exit(1); });
    } catch (e) {
      console.log('LOAD-FAIL ' + String(e.message).split('\n')[0]);
      process.exit(1);
    }
  " )
  return $?
}

rollback() {
  [ -d "$BACKUP_DIR" ] || die "没有备份：$BACKUP_DIR"
  echo "== 还原 =="
  rm -rf "$SHARP_DIR" || die "删不掉 $SHARP_DIR"
  cp -a "$BACKUP_DIR" "$SHARP_DIR" || die "还原失败"
  echo "✓ 已还原"
  verify
}

build() {
  [ -d "$SHARP_DIR" ] || die "sharp 目录不存在：$SHARP_DIR"
  echo "== 版本 =="
  node -p "require('$SHARP_DIR/package.json').version" 2>/dev/null || true

  echo
  echo "== 备份 =="
  mkdir -p "$(dirname "$BACKUP_DIR")"
  if [ -d "$BACKUP_DIR" ]; then
    echo "备份已存在，复用：$BACKUP_DIR"
  else
    cp -a "$SHARP_DIR" "$BACKUP_DIR" || die "备份失败，停止"
    echo "✓ 备份到 $BACKUP_DIR"
  fi

  echo
  echo "== 安装 libvips 与编译工具 =="
  pkg install -y libvips pkg-config python clang make 2>&1 | tail -3
  pkg install -y libvips-dev 2>&1 | tail -2 || true

  echo
  echo "== libvips 版本 =="
  pkg-config --modversion vips 2>/dev/null || die "pkg-config 找不到 vips：libvips 没装好"
  echo "vips-cpp: $(pkg-config --modversion vips-cpp 2>/dev/null || echo '找不到（可能影响编译）')"
  if [ ! -f "${PREFIX:-/data/data/com.termux/files/usr}/include/vips/vips8" ] && \
     [ ! -f "${PREFIX:-/data/data/com.termux/files/usr}/include/vips/vips.h" ]; then
    echo "⚠️  没找到 vips 头文件；编译可能报 'vips8 file not found'" >&2
  fi

  echo
  echo "== 装编译期依赖（node-addon-api / node-gyp）=="
  cd "$SHARP_DIR" || die "进不去 $SHARP_DIR"
  npm install --no-save --no-package-lock --omit=optional node-addon-api node-gyp 2>&1 | tail -5 \
    || die "装编译依赖失败"

  echo
  echo "== 装 glib 头文件与 xproto（vips 的 pkg-config 依赖它们）=="
  pkg install -y glib xorgproto 2>&1 | tail -3 || true
  pkg install -y glib-dev 2>&1 | tail -2 || true
  if [ -f "${PREFIX:-/data/data/com.termux/files/usr}/include/glib-2.0/glib-object.h" ]; then
    echo "✓ glib-object.h 存在"
  else
    echo "⚠️  仍找不到 glib-object.h，编译大概率还会失败" >&2
  fi
  echo "--- pkg-config --cflags vips ---"
  pkg-config --cflags vips 2>&1 || echo "  （失败）"

  echo
  echo "== 放行 libvips 版本闸门 =="
  # sharp 0.35.5 要求 vips >= 8.18.7，但 Termux 仓库只有 8.18.0。
  # 8.18.0 → 8.18.7 是 micro（补丁级）差异，API 兼容；把闸门降到 8.18.0。
  COMMON_H="$SHARP_DIR/src/common.h"
  if [ -f "$COMMON_H" ] && grep -q 'VIPS_MICRO_VERSION < 7' "$COMMON_H" 2>/dev/null; then
    sed -i 's/VIPS_MICRO_VERSION < 7/VIPS_MICRO_VERSION < 0/' "$COMMON_H" || die "改不动 $COMMON_H"
    echo "⚠️  已把闸门 8.18.7 → 8.18.0（升级 sharp 后要重新打这个补丁）"
  else
    echo "闸门已经是放行状态，跳过"
  fi

  echo
  echo "== 从源码编译（可能 5–30 分钟）=="
  echo "   注意：sharp 0.35 没有 install 脚本，npm rebuild 是空转，必须走 npm run build。"
  echo "   不要设 SHARP_IGNORE_GLOBAL_LIBVIPS —— 源码里 Boolean('0') 仍是 true，会禁用系统 libvips。"
  # pkg-config 若因缺 xproto/xrender 失败，vips 的 cflags 就一条都传不过去，
  # 编译时就会找不到 glib-object.h。这里手动补齐。
  EXTRA_CFLAGS="$(pkg-config --cflags vips vips-cpp glib-2.0 gobject-2.0 2>/dev/null || true)"
  EXTRA_LIBS="$(pkg-config --libs vips vips-cpp 2>/dev/null || true)"
  echo "   EXTRA_CFLAGS=$EXTRA_CFLAGS"
  if ! SHARP_FORCE_GLOBAL_LIBVIPS=1 CXXFLAGS="$EXTRA_CFLAGS ${CXXFLAGS:-}" CFLAGS="$EXTRA_CFLAGS ${CFLAGS:-}" LDFLAGS="$EXTRA_LIBS ${LDFLAGS:-}" \
       npm run build; then
    echo
    echo "✗ 编译失败。回滚：sh build-sharp.sh --rollback" >&2
    exit 1
  fi

  echo
  verify || {
    echo
    echo "✗ 编译过了但加载失败。回滚：sh build-sharp.sh --rollback" >&2
    exit 1
  }
  echo
  echo "✓ 成功。下一步：在 App 里重启托管的 DSH，然后试发图。"
  echo "  注意：npm i -g @deepseek-ai/dsh 升级会覆盖这份编译结果。"
}

case "${1:-build}" in
  --verify) verify ;;
  --rollback) rollback ;;
  --help|-h) sed -n '2,10p' "$0" ;;
  *) build ;;
esac
