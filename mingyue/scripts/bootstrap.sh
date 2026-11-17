#!/usr/bin/env bash
# 溟月 · 新主机引导（平台差异只在这里）
# 用法：bootstrap.sh [termux|linux|auto] [--with-ntfy]
set -euo pipefail

MODE="${1:-auto}"
WITH_NTFY=0
for a in "$@"; do [ "$a" = "--with-ntfy" ] && WITH_NTFY=1; done

if [ "$MODE" = "auto" ]; then
  if [ -n "${PREFIX:-}" ] && [ "${PREFIX#*com.termux}" != "$PREFIX" ]; then
    MODE=termux
  else
    MODE=linux
  fi
fi

DSH_VERSION="${DSH_VERSION:-0.2.2-rc.1}"
HOME_DIR="${MINGYUE_HOME:-$HOME/mingyue}"

echo "== 平台：$MODE =="

case "$MODE" in
  termux)
    pkg update -y
    pkg install -y nodejs openssh python age zstd tar sqlite
    ;;
  linux)
    SUDO=""
    [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO apt-get update -y
    $SUDO apt-get install -y nodejs npm openssh-server python3 age zstd tar sqlite3 curl
    ;;
  *)
    echo "未知平台：$MODE（只能是 termux 或 linux）" >&2; exit 2 ;;
esac

# Node 版本检查（DSH 需要 ^22.19 或 >=24）
if command -v node >/dev/null; then
  echo "node: $(node -v)"
else
  echo "⚠️  node 未安装，DSH 起不来" >&2
fi

# DSH
if ! command -v dsh >/dev/null; then
  npm config set registry https://registry.npmmirror.com >/dev/null 2>&1 || true
  npm i -g "@deepseek-ai/dsh@${DSH_VERSION}"
fi

# 目录
mkdir -p "$HOME_DIR"/{scripts,schedules,reads,daily,tmp}

# 自启
if [ "$MODE" = "termux" ]; then
  BOOT="$HOME/.termux/boot"
  mkdir -p "$BOOT"
  cat > "$BOOT/server" <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
termux-wake-lock
sshd
EOF
  chmod +x "$BOOT/server"
  echo "已写 ~/.termux/boot/server（记得装 Termux:Boot 并打开一次）"
else
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/mingyue-dsh.service" <<EOF
[Unit]
Description=Mingyue DSH
After=network-online.target

[Service]
ExecStart=$(command -v dsh) web --host 127.0.0.1 --port 3080 --no-open
Restart=always
RestartSec=5
WorkingDirectory=${HOME_DIR}

[Install]
WantedBy=default.target
EOF
  echo "已写 $UNIT_DIR/mingyue-dsh.service"
  echo "启用：systemctl --user daemon-reload && systemctl --user enable --now mingyue-dsh"
  echo "无登录也常驻：loginctl enable-linger \$USER"
fi

# 可选：ntfy（二进制，不自动下载）
if [ "$WITH_NTFY" -eq 1 ]; then
  if command -v ntfy >/dev/null; then
    echo "ntfy 已存在：$(command -v ntfy)"
  else
    echo "⚠️  未找到 ntfy。从 Releases 取 linux_arm64 版本放到 ~/bin 并 chmod +x："
    echo "   https://github.com/binwiederhier/ntfy/releases"
  fi
fi

cat <<NEXT

== 下一步 ==
1) 恢复数据：bash restore.sh <导出的包>
2) 起服务：$([ "$MODE" = termux ] && echo "重开 Termux 或手动跑 dsh web" || echo "systemctl --user start mingyue-dsh")
3) 重建定时任务：把 schedules/SETUP.md 贴给 agent
4) App 里加这台主机的 SSH 条目
NEXT
