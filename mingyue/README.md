# 溟月的家（源文件）

这个目录是**她家目录的源码**：脚本、人设/规则/初始档案和任务模板都在这里版本化；`memory.db`、`journal.jsonl`、`AGENTS.md` 的 CORE 区这些运行期数据留在主机上，不进仓库。

配套文档：[../docs/mingyue/MIGRATION.md](../docs/mingyue/MIGRATION.md)（为什么这样设计）、[PLAN.md](../docs/mingyue/PLAN.md)（整体计划）、[MEMORY.md](../docs/mingyue/MEMORY.md)（记忆架构）。

```
mingyue/
├─ scripts/
│  ├─ mem.py         记忆库读写（init/add-episode/consolidate/ingest/search/pin/render/
│  │                 core-refresh/decay/import-profile/forget/report/rebuild/check）
│  ├─ schema.sql     记忆库表结构（mem.py init 逐条执行；schema v2）
│  ├─ apply-manual.py把 persona.md + rules.md 拼进 AGENTS.md 手工区（render 不碰）
│  ├─ selftest.py    mem.py 自查：python3 selftest.py（退出码 0 = 全过）
│  ├─ export.sh      导出加密包（备份 = 迁移包）
│  ├─ restore.sh     在新主机上恢复
│  ├─ bootstrap.sh   新主机装依赖 + 自启（平台差异只在这里）
│  ├─ status.sh      状态自检：sshd / 引擎 / 端口 / 家里 / 备份 / Termux 补丁
│  ├─ fix-termux.sh  **Termux 兼容补丁总入口**：修附件/图片（见 TROUBLESHOOTING §7）
│  ├─ build-sharp.sh 从源码编译 sharp（Termux 没有 Android 预编译包）
│  ├─ patch-attachment-{durable,link,log}.sh  附件存储的三处 Android 兼容补丁
│  ├─ probe-{image,sharp,tmp,store-root,store-path,engine-modules,upload}.sh  排障探针
│  └─ peek-session.sh 只打印会话字段名，不泄露内容（排查会话格式用）
├─ persona.md         人设卡（源文件，apply-manual.py 拼进 AGENTS.md）
├─ rules.md           说话 + 检索规则（源文件，同上；写清"何时 search / 搜不到不许编"）
├─ me.md              初始档案（部署时 mem.py import-profile 灌一次，之后交给记忆系统）
└─ schedules/
   ├─ SETUP.md           迁移后重建定时任务的提示词（含前置检查与手动验收流程）
   ├─ night-extract.md   每天 04:00 抽取（ingest 昨天 → 模型输出候选 JSONL）
   ├─ night-consolidate.md 每天 04:10 沉淀（consolidate 昨天 → core-refresh → render）
   └─ weekly-review.md   每周一 04:20 周反思（report → decay → ≤5 行总结）
```

> 运行期数据（`memory.db`、`journal.jsonl`、`AGENTS.md`）不进仓库，留在主机上。

> 写人设的经验（2026-11-17 实测）：**只有"不要做什么"的禁令会得到"没有性格"**，不是"克制"。
> 第一版 persona 全是「句子短」「允许沉默」「不卖萌」这类限制，结果她冷、敷衍、不主动。
> 加上「## 你是怎样的人」正向描述（有情绪 / 会主动 / 有记性 / 有偏好），并删掉「允许沉默」后，立刻有活人感。
> 改完跑一次 `apply-manual.py`，不用重启引擎（`AGENTS.md` 每轮自动注入）。
> 备份包里 `journal.jsonl` 是审计真源：删了 `memory.db` 就靠它 `mem.py rebuild --from` 重建。

## 一次性准备：age 密钥对

**在 PC 上**（不要在手机上生成私钥）：

```bash
age-keygen -o ~/.config/mingyue/age.key      # 私钥，只留在这台 PC
age-keygen -y ~/.config/mingyue/age.key > ~/.config/mingyue/age.pub
```

把 **公钥** 放到主机上：

```bash
ssh u0_aXXX@100.x.y.z -p 8022 'mkdir -p ~/.config/mingyue'
scp -P 8022 ~/.config/mingyue/age.pub u0_aXXX@100.x.y.z:~/.config/mingyue/
```

这样：手机只能加密、不能解密。**丢手机不等于丢记忆。**

> **Windows 上的 age**（本机实测，2026-11-16）：官方包解压到
> `%LOCALAPPDATA%\age\age\`，**没有加入系统 PATH**（避免改动用户环境变量）。
> 需要时用完整路径，例如：
> `& "$env:LOCALAPPDATA\age\age\age-keygen.exe" -y "$env:USERPROFILE\.config\mingyue\age.key"`。
> 想加进 PATH 再自己加，脚本不依赖这一点（手机端才需要 `age` 在 PATH 里）。

## 把脚本放到主机

```bash
scp -P 8022 -r mingyue/scripts mingyue/schedules u0_aXXX@100.x.y.z:~/mingyue/
ssh -p 8022 u0_aXXX@100.x.y.z 'chmod +x ~/mingyue/scripts/*.sh'
```

> `mem.py ingest` 要 `zstd`（`bootstrap.sh` 已装；`command -v zstd` 确认）。

## 部署人设 / 规则 / 初始档案（一次）

```bash
scp -P 8022 mingyue/persona.md mingyue/rules.md mingyue/me.md u0_aXXX@100.x.y.z:~/mingyue/
# 主机上：
python3 ~/mingyue/scripts/apply-manual.py       # persona + rules → AGENTS.md 手工区（幂等）
python3 ~/mingyue/scripts/mem.py import-profile ~/mingyue/me.md   # 一次性；重跑是 NOOP
python3 ~/mingyue/scripts/mem.py core-refresh   # 让新 facts 进「最近」并 render
```

- `AGENTS.md` 的 CORE 区归 `mem.py render`，手工区归 `apply-manual.py`；**不要手改 AGENTS.md**。
- 改完 `persona.md` / `rules.md` 重跑一次 `apply-manual.py`；`--check` 只比对。
- `me.md` 是"打底"用的，导完就不用再改（后面交给记忆系统）。

## 日常

```bash
# 主机上
~/mingyue/scripts/export.sh                 # 产物在 ~/backups/
scp -P 8022 u0_aXXX@100.x.y.z:~/backups/mingyue-*.age .   # 拉回 PC
```

有腾讯云账号后，把 `export.sh` 末尾加一行上传 COS 即可——**改动只有一行**，因为格式没变。

## 迁移演练（换主机前必须做一次）

在 PC 的 WSL 里：

```bash
bash mingyue/scripts/bootstrap.sh linux
bash mingyue/scripts/restore.sh --yes mingyue-20261116-2110.tar.zst.age
```

然后在 App 里加 WSL 这台主机，连上去对话，确认查得到旧记忆、语气一致。

## 约定

- 脚本只用 `$HOME` / `$MINGYUE_HOME`，**不写死 Termux 路径**（唯一例外是 Termux:Boot 的 shebang）。
- `archive/`（旧聊天原文）不进备份包。
- 恢复永远先备份旧目录为 `mingyue.bak-<时间>`，回滚是 30 秒的事。
