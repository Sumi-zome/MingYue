#!/data/data/com.termux/files/usr/bin/sh
# 修 DSH profile 的「默认模型」——定时任务新建的会话用它。
#
# 背景（2026-11-17）：主机 profile 里默认模型被设成了 amazon-bedrock /
# anthropic.claude-fable-5-1，主机没有 bedrock 适配器 → 所有定时任务
# 新建的会话整轮失败：no adapter registered for provider "amazon-bedrock"。
# 聊天没事，因为 App 里是手动选的模型。
#
# 用法：
#   sh fix-default-model.sh                    # 改成 deepseek-account / deepseek-flash
#   sh fix-default-model.sh <provider> <model>
#   sh fix-default-model.sh --check            # 只看当前值
set -eu

F="${DSH_PROFILE_PATCH:-$HOME/.dsh/profiles/web/cordis.patch.yml}"
PROVIDER="${1:-deepseek-account}"
MODEL="${2:-deepseek-flash}"

[ -f "$F" ] || { echo "✗ 找不到 $F"; exit 1; }

show() {
  echo "== 当前 agent-default-model =="
  python3 - "$F" <<'PY'
import sys, io
lines = io.open(sys.argv[1], encoding="utf-8").read().split("\n")
try:
    i = next(i for i, l in enumerate(lines) if l.strip() == "- id: agent-default-model")
except StopIteration:
    print("  （profile 里没有 agent-default-model 条目）")
    sys.exit(0)
for l in lines[i:i + 8]:
    print("  " + l)
PY
}

if [ "${1:-}" = "--check" ]; then
  show
  exit 0
fi

cp "$F" "$F.bak-$(date +%Y%m%d-%H%M%S)" || exit 1

python3 - "$F" "$PROVIDER" "$MODEL" <<'PY'
import sys, io, re
path, prov, model = sys.argv[1], sys.argv[2], sys.argv[3]
lines = io.open(path, encoding="utf-8").read().split("\n")
try:
    i = next(i for i, l in enumerate(lines) if l.strip() == "- id: agent-default-model")
except StopIteration:
    print("✗ profile 里没有 agent-default-model 条目", file=sys.stderr)
    sys.exit(2)
changed = 0
for j in range(i, min(i + 12, len(lines))):
    if re.match(r"\s+provider:", lines[j]):
        lines[j] = re.sub(r"(provider:\s*).*", r"\g<1>" + prov, lines[j]); changed += 1
    elif re.match(r"\s+model:", lines[j]):
        lines[j] = re.sub(r"(model:\s*).*", r"\g<1>" + model, lines[j]); changed += 1
io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
print("✓ 改了 %d 行" % changed)
PY

show
echo
echo "下一步：在 App 里【重启托管的 DSH】让配置生效，然后跑一次定时任务验证。"
