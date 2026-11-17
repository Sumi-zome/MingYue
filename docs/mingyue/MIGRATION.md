# 溟月 · 云端备份与主机迁移

> 2026-11-16。配套 [PLAN.md](PLAN.md) 与 [MEMORY.md](MEMORY.md)。
> 目标：**她住在哪台机器都可以**——今天在旧手机，明天换到云主机，后天换回电脑，**记忆不丢、App 不改**。

---

## 0. 为什么现在就要设计这个

你的两个担心都是真的：

1. 旧手机不可能一直当服务器（电池老化、系统杀后台、某天坏了）。
2. 上云更稳（不怕断电、不怕被杀、随时可达）。

但如果等换机器那天才开始想，你会发现：路径写死在 Termux 里、定时任务要重配、记忆库拿不出来。**所以"备份"和"迁移"要用同一套东西做**——导出格式就是升级接口。

---

## 1. 一个原则：她的"家"必须自包含

```
$HOME/mingyue/          ← 整个目录就是"她"
├─ memory.db            六层记忆
├─ persona.md / me.md / rules.md
├─ reads/               读过的内容
├─ skills/content/      内容理解
├─ scripts/             mem.py / fetch.py / push.sh / maybe_speak.sh / backup.sh
├─ schedules/           三条定时任务的提示词（纯文本）
└─ manifest.json        版本、规格、依赖
```

**硬规矩**：

- 所有脚本用 `$HOME/mingyue`，**不许出现 `/data/data/com.termux/...`**（唯一的例外是 Termux:Boot 的 shebang）。
- 她依赖的外部程序（node / dsh / ntfy / age）由一个 `bootstrap.sh` 统一安装，平台差异只在这一个文件里。
- **会话不搬**。会话是引擎私有的，搬过去也用不了；搬的是"她的记忆和人设"，换主机后重新开一段对话即可。

---

## 2. 导出（备份 = 迁移包）

```bash
$HOME/mingyue/scripts/export.sh [--out DIR]
```

产物：

```
mingyue-20261116-2110.tar.zst.age     ← age 加密（没有 age 就用 gpg）
├─ mingyue/…                           （不含 memory.db 的 wal/shm）
├─ manifest.json
└─ SHA256SUMS
```

`manifest.json` 的内容：

```json
{
  "schema": 1,
  "exported_at": "2026-11-16T21:10:00+08:00",
  "host": "old-phone",
  "platform": "termux",
  "dsh_version": "0.2.2-rc.1",
  "workspace": "~/mingyue",
  "schedules": ["schedules/noon.md", "schedules/night.md", "schedules/weekly.md"],
  "ntfy": { "topic": "mingyue", "port": 8090 },
  "encrypted": true
}
```

**密钥**：一把 `age` 公钥（私钥只放 PC 上，不放在手机上）。这样手机只负责"加密上传"，拿到文件的任何地方都解不开——**手机上不存解密能力，丢手机不丢记忆**。

> 这一条比"上传到哪"更重要：不管你传到 COS、Git 仓库还是 U 盘，文件本身是密文。

---

## 3. 备份到哪：四种，按成本排

| 目标 | 成本 | 优点 | 缺点 | 建议 |
|---|---|---|---|---|
| **`scp` 拉回 PC** | 0 | 最简单，无第三方 | PC 要在线 | **第一步就做这个** |
| **腾讯云 COS / CloudBase 对象存储** | 几分钱/月 | 国内快、稳定 | 要实名 + 保管密钥 | 有账号后加 |
| **Git 私有仓库**（独立 orphan 分支） | 0 | 自带版本历史 | 二进制会涨仓库 | 可选 |
| **WebDAV**（坚果云等） | 0–低 | 配置简单 | 依赖第三方 | 可选 |

**推荐路径**：先 `scp`（今天就能做）→ 有腾讯云账号后切 COS（改动只在 `export.sh` 的末行）。

**频率**：每天一次（由定时任务触发），保留最近 14 份 + 每月一份。

---

## 4. 恢复与迁移：`bootstrap.sh` + `restore.sh`

### 4.1 新主机上要做的三步

> 脚本已写好在仓库 `mingyue/scripts/`（`export.sh` / `restore.sh` / `bootstrap.sh`），
> 用 `scp` 传到主机即可，见 [mingyue/README.md](../../mingyue/README.md)。

```bash
# 1. 装基础环境（平台差异只在这个脚本里）
bash bootstrap.sh termux      # 或 bash bootstrap.sh linux

# 2. 解包（在 PC 上解开再传，或在新主机上解开）
bash restore.sh mingyue-20261116-2110.tar.zst.age

# 3. 自检
python3 ~/mingyue/scripts/mem.py check
```

### 4.2 `bootstrap.sh` 做什么

| 平台 | 安装 | 自启 |
|---|---|---|
| `termux` | node / openssh / python / age / ntfy | `~/.termux/boot/server`（shebang 用绝对路径） |
| `linux` | node / openssh / python / age / ntfy（apt 或二进制） | systemd unit：`mingyue-dsh.service` + `mingyue-ntfy.service` |

两边都做：建 `~/mingyue`、装 skill、`dsh plugin` 不需要（我们不用插件）。

### 4.3 `restore.sh` 做什么

1. 校验 `SHA256SUMS`
2. 解包到 `$HOME/mingyue`（**先备份已有目录**为 `mingyue.bak-<时间>`）
3. `sqlite3 memory.db "PRAGMA integrity_check"` + `mem.py rebuild --check`
4. 打印"还需要手动做的三件事"（见 4.4）

### 4.4 迁移后必须人做的一件事：重建定时任务

定时任务在引擎里，不在文件里。所以：

- 三条任务的**完整提示词**存在 `mingyue/schedules/*.md`（纯文本，随备份走）。
- 迁移后，把 `schedules/SETUP.md` 贴给新主机上的 agent，让它按内容用 `schedule_create` 建三条任务。
- 这是刻意的选择：**手动一次（约 3 分钟）**，比写一个易碎的自动化恢复脚本划算。

### 4.5 App 侧要改什么

**只改一个地方：主机地址。**

- 现在：SSH 主机 = `100.x.y.z:8022`
- 换到云：加一台新 SSH 主机，指向云主机的地址，选中它即可。
- 老主机条目留着，随时能切回去。

这就是所谓的"升级接口"——**App 已经支持多主机，所以换后端对 App 是零改动**。

---

## 5. 迁移演练（这步不能省）

**在真的换主机之前，先在 PC 的 WSL 上跑一遍**：

```
旧手机 export → scp 到 PC → WSL 里 bootstrap.sh linux → restore.sh → mem.py check → 手机 App 加 WSL 这台 → 对话
```

通过的标志：

- [ ] 能查到旧记忆（`mem.py search "宿舍"` 有结果）
- [ ] 她的语气和旧机器上一致（persona 读到了）
- [ ] 三条定时任务重建后能正常触发
- [ ] 旧手机没被影响，还能连

**只有演练通过，迁移才算有接口。** 没演练过的备份，等于没有备份。

---

## 6. 什么时候值得真的上云

不是"云更好"，是"云解决什么"：

| 问题 | 云解决吗 | 旧手机能解决吗 |
|---|---|---|
| 宿舍断电 | ✅ | 靠电池（能撑几小时，但会没电） |
| 系统杀后台 | ✅ | 靠白名单（偶尔失效） |
| 电池老化 | ✅ | 换电池（159） |
| 出门在外要连 | ✅ | 流量 + Tailscale 也能 |
| 零成本 | ❌ | ✅ |
| 手机丢了数据还在 | ✅（配合备份） | ❌ |

**上云触发条件（满足任一条就迁，不再凭感觉争论）**

| # | 条件 | 怎么判定 |
|---|---|---|
| 1 | 一周内她掉线 ≥ 2 次 | App 里出现"连接断开/主机离线"，或你自己记一笔 |
| 2 | 旧手机电池健康度 < 80%，或换电后仍掉得很快 | 设置 → 电池 → 电池健康度 |
| 3 | 需要在没有电脑的环境连续使用（实习、出差、回家） | 出现一次即算 |
| 4 | 你开始担心手机丢了/坏了，影响正常使用 | 主观，出现即算 |

**流程**：任一条成立 → 先做一次迁移演练（§5）→ 演练通过后再买学生机 → 按 §4 迁过去。

**未触发前**：只做备份（§3），每月可选跑一次演练。不要因为"云听起来更好"就提前花钱。

预算参考：学生机 2C2G 首年百元级，先别买三年。

---

## 7. 验收

1. `export.sh` 产出一个加密包，拿到 PC 上 `age -d` 能解开。
2. 手机上**解不开**（私钥不在手机上）。
3. WSL 演练：新主机恢复后能对话，且查得到旧记忆。
4. 恢复过程弄坏东西时，`mingyue.bak-*` 能在 30 秒内切回去。
5. 迁移演练结束后，旧手机重新连上，一切照旧。

---

## 8. 跨平台：她本来就是可移植的

这不是巧合——设计时有三条约束就是为迁移留的：

1. 脚本里**只用 `$HOME` / `$MINGYUE_HOME`**，不写死 Termux 路径
2. `mem.py` **只用 Python 标准库**，不装任何 pip 包
3. **导出格式就是迁移接口**（加密包 + manifest + 恢复脚本）

| 组件 | Termux | Linux | Windows | 备注 |
|---|---|---|---|---|
| `mem.py` / `selftest.py` / `schema.sql` | ✅ | ✅ | ✅ | 纯 stdlib；Windows 上 `py -3` 实测过 |
| `memory.db` / `journal.jsonl` / `AGENTS.md` / `reads/` | ✅ | ✅ | ✅ | 纯文本与 SQLite |
| `export.sh` / `restore.sh` | ✅ | ✅ | ⚠️ | 需要 Git Bash；`zstd`/`age` 手动装 |
| `status.sh` | ✅ | ✅ | ❌ | 它靠 `ps -ef`，Git Bash 的 ps 看不到 Windows 进程 → 需 `status.ps1` |
| `bootstrap.sh` | ✅ | ✅ | ❌ | 只有 termux / linux 两条分支 |
| 自启 | Termux:Boot | systemd | 计划任务 | |
| `zstd` / `age` / `sqlite3` | `pkg` | `apt` | 手动装二进制 | |
| `ntfy` | 静态二进制 | systemd | 不推荐 | Windows 上改用邮件或其它推送 |
| 手机 App（溟月） | ✅ | ❌ | ❌ | 桌面端用 DSH Desktop，App 只是客户端 |

### 真的搬过去时要做什么

**搬到 Linux**：`bash bootstrap.sh linux` + `restore.sh`，几乎是开箱的（systemd 单元已内置）。

**搬到 Windows**（把 PC 当主机）：
1. 装 `age` / `zstd` / `sqlite3` 三个二进制，放进 PATH
2. 写一个 `status.ps1`（用 `Get-Process` / `Get-NetTCPConnection` 替掉 `ps`）
3. 自启靠 DSH App 的**托管启动**就够，不必做计划任务
4. `mem.py ingest` 需要 `zstd.exe`，或者等你升到 Python 3.14（自带 `compression.zstd`）

### 一条要守住的规矩

**`mem.py` 永远只用 Python 标准库。**

它是最值钱的资产：1400 行、13 条自检、跨平台验证过。一旦引入 pip 依赖，就同时失去"手机上能跑""Windows 上能跑""几年后还能跑"这三件事。

---

### 8.1 三个"版本头"：升级时靠它们判断怎么读

光有"能搬"不够，还得能判断**搬到新版本上之后怎么读**。三个地方各要一个版本头：

| 对象 | 版本载体 | 读取规则 |
|---|---|---|
| **数据库结构** | `PRAGMA user_version` | `init` 读版本 → 按需 `ALTER` → 写回；`check` 打印当前版本 |
| **审计记录** | 每条 `journal.jsonl` 记录的 `v` 字段（库内 `journal.v` 同值镜像） | 缺省视为 `v:1`；重放按各自版本解析 |
| **会话文件** | 文件名 `session.v4.jsonl.zstd` **+ 文件头** `version` / `sessionFormatVersion` | 只遍历 v4 文件名；文件头版本不在已知集合 `{4}` 或缺失 → **明确报错（退出码 4）**，绝不当成空数据。事件里的 `sessionFormatVersion` 有 v3→v4 迁移遗留值，不参与判定 |

**规则一句话**：写入带版本，读取容忍"没有版本 = 1"，遇到不认识的版本就停下来报错。

为什么现在定：窗口 C 要把 schema 从 v1 升到 v2（加 `core.origin`）。没有版本号，半年后你只会看到一堆列，猜不出它们是哪次加的、升级脚本该从哪一步开始。

**反例（千万不要这样）**：`ingest` 遇到没见过的会话格式时返回空候选 → 定时任务"成功"了 → 她静默地什么都记不住 → 你两周后才发现。**认不出来就必须报错。**

---

## 9. 一句话

**备份和迁移是同一件事**：把她的家打成一个加密包，里头带一份"怎么在新机器上重新站起来"的说明。
云只是这个包的**目的地**之一，不是前提。
**平台也一样**：她的记忆和脚本不绑在安卓上，绑的只是"启动方式"和"几个二进制工具"。
