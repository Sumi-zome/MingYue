# 溟月的家（源文件）

这个目录是**她家目录的源码**：脚本和任务模板在这里版本化，`memory.db`、`persona.md` 这些运行期数据留在主机上，不进仓库。

配套文档：[../docs/mingyue/MIGRATION.md](../docs/mingyue/MIGRATION.md)（为什么这样设计）、[PLAN.md](../docs/mingyue/PLAN.md)（整体计划）。

```
mingyue/
├─ scripts/
│  ├─ mem.py         记忆库读写（init/add-episode/consolidate/search/pin/render/forget/report/rebuild/check）
│  ├─ schema.sql     记忆库表结构（mem.py init 逐条执行）
│  ├─ selftest.py    mem.py 自查：python3 selftest.py（退出码 0 = 全过）
│  ├─ export.sh      导出加密包（备份 = 迁移包）
│  ├─ restore.sh     在新主机上恢复
│  ├─ bootstrap.sh   新主机装依赖 + 自启（平台差异只在这里）
│  └─ status.sh      状态自检：sshd / 引擎 / 端口 / 家里 / 备份
└─ schedules/
   └─ SETUP.md       迁移后重建定时任务的提示词
```

> 运行期数据（`memory.db`、`journal.jsonl`、`AGENTS.md`）不进仓库，留在主机上。
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
