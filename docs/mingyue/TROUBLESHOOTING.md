# 溟月 · 故障排查

> 2026-11-17。记录**已经踩过的坑**。遇到问题时先搜这里，别从代码开始怀疑。
> 配套：[PLAN.md](PLAN.md)（设计与验收）、[MIGRATION.md](MIGRATION.md)（备份迁移）。

---

## 0. 一条判断链

```
App 连不上 / 连一下断一下
  → 先在 PC 上跑 status.sh，看引擎和端口
      ├─ 没有进程 / 没有端口 → 引擎层（看 §2）
      └─ 有进程、http:401      → 连接层（看 §3）
```

`http:401` 是**健康**信号：引擎在应答，只是没令牌不给看。看到 401 就别再怀疑后端了。

```powershell
ssh mingyue "bash ~/mingyue/scripts/status.sh"
```

---

## 1. App「连一下断一下」（已发生两次）

### 症状

App 显示「重新连接中」，连上几秒又断；`status.sh` 显示引擎正常（PID 稳定、端口在听、http:401）。

### 真因（2026-11-17 实测）

**新手机开热点导致过热，Tailscale 连接不稳定**，SSH 传输层抖动。
和引擎、脚本、记忆库**一点关系都没有**。

### 怎么快速确认

1. `status.sh` 看引擎 → 正常就排除后端
2. **关掉 Tailscale，改用局域网 IP 连**（同一 WiFi 下填旧手机的 `192.168.x.x:8022`）
   - 局域网稳、Tailscale 抖 → 就是网络层
3. 看新手机温度/是否在开热点

### 处理

- 别让手机一边开热点一边跑 VPN 长连接
- 给 Tailscale 加后台白名单、关电池优化
- 长期方案：**内网稳定时用局域网地址做主机会话，Tailscale 只作备用**

### 不要做的

- 不要急着"重启托管 DSH"——那会真的换端口和 token，把网络问题变成认证问题
- 不要改 `mem.py`、不要重建库

---

## 2. 引擎层：起不来 / 反复重启

| 现象 | 先看 |
|---|---|
| `status.sh` 说没有进程 | App 里连一次；仍没有就看 `~/.dsh-app-remote/web.log` 尾部 |
| `web.log` 里有异常栈 | 引擎启动失败，通常是 `~/.dsh` 残留或 Termux 被限制 |
| PID 一直在变 | 引擎被反复拉起，看 `web.log` 的时间与报错 |
| `dsh: not found` | PATH 问题，主机启动命令填绝对路径 |

清理残留（会把 App 的托管记录一起清掉，下次连接重新拉起）：

```bash
pkill -f "dsh web"; rm -f ~/.dsh-app-remote/web.*
```

---

## 3. 认证层：连上就断、日志有 401

Token 只对当前进程有效，**引擎每次重启都换**。

App 里：主机 → 编辑 → **重启托管的 DSH**（这是文档给的正式操作）。
还不行就删掉主机会话重新添加。

---

## 4. PC 侧的坑

| 坑 | 表现 | 处理 |
|---|---|---|
| **多行粘贴被拼成一条** | PowerShell 出现 `>>` | 一行一条，或用 `;` 连接 |
| **`ssh "..."` 里的引号被吃** | `grep "[d]sh web"` 变成 `grep dsh` | 用脚本文件，别在 `ssh "..."` 里塞引号 |
| **`Get-Content` 默认 GBK** | 中文变乱码、JSON 校验假报错 | `-Encoding UTF8`；校验请用 Python 或 `py -3` |
| **`.ps1` 里中文导致解析失败** | 报"字符串缺少终止符"、错误位置莫名其妙 | 文件必须存成 **UTF-8 with BOM**（PowerShell 5.1 无 BOM 时按 GBK 读）；`status.ps1` 文件头已注明 |
| **`>` 重定向写坏二进制** | 解出来的包打不开 | 用程序自己的 `-o`（如 `age -d -o`） |
| **ssh config 用 CRLF** | Git Bash 解析不到 Host | 写成 LF、无 BOM |
| **`ProxyCommand connect` 不存在** | `Connection closed by UNKNOWN port 65535` | 注释掉，直连或改 `ssh.github.com:443` |

---

## 5. 手机（Termux）侧的坑

| 坑 | 表现 | 处理 |
|---|---|---|
| **没有 `/tmp`** | scp 报 `dest open "/tmp/": Failure` | 用 `~/mingyue/tmp` 或 `$TMPDIR` |
| **`~` 在 scp 里不展开** | 传到相对路径、目录不存在 | 目标写 `主机:相对路径`，先用 ssh `mkdir -p` |
| **Ctrl+C 杀掉前台引擎** | App 连不上，但托管实例其实还活着 | 看清在杀谁；托管实例是 `nohup` 的后台进程 |
| **重启后引擎不自启** | 早上打开 App 才回来 | 已知问题，见 PLAN §4.10 |
| **默认 3080 端口** | `curl 3080` 连不上 | 托管启动用 `--port 0`，真实端口在 `web.log` |

---

## 6. 记忆层的坑

| 现象 | 原因 |
|---|---|
| `consolidate` 整批拒绝 | 某行缺 `reason` / `source` / `source_episode`，报行号 |
| `consolidate` 报 `episode id 已存在` | 抽取重跑/测试遗留撞了 id。**不要改库、不要删旧 episode（facts 有外键）**；把候选文件里的 id 改成唯一值（含时间后缀，如 `e-20261116-0412-02`）并同步 `source_episode`，再重跑 |
| 她"记得但看不见" | `facts` 有数据、`core` 是空的；渲染只读 `core`。跑 `core-refresh` + `render` |
| `search` 搜不到两字词 | trigram 限制，<3 字走 LIKE（已内置） |
| `ingest` 报"找不到 zstd" | Termux 用 `pkg install -y zstd`（bootstrap 已装）；PC/WSL 用 `apt install zstd` 或放个 `zstd.exe` 进 PATH。**不要**拿别的东西改名顶替 |
| `ingest` 报"不认识的会话格式版本" | 会话头 `version`/`sessionFormatVersion` 不是 4。先看 `zstd -dc <文件> \| head -1`；**不要删会话文件**，也不要当成空数据跳过 |
| `ingest` 输出 0 条 | 先看 stderr 的扫描/跳过计数：① `--workspace` 和会话头 `cwd` 不一致（App 工作目录是 `~/mingyue`）② 当天没有真人消息 ③ 当天只有定时任务会话（会被防自喂跳过）。**不要**为了凑数据手改过滤 |
| 抽出来的文本里混进 AGENTS.md / 任务提示词 | `ingest` 应该按 `data.source.kind=="user"` 过滤且跳过无真人消息的会话；再看任务会话的 `agentPreset` 是否命中记忆任务预设名（双保险） |
| 命令报「memory.db 是旧 schema」 | 引擎脚本升级过而库还没迁移：跑一次 `python3 ~/mingyue/scripts/mem.py init`（幂等，只 `ALTER TABLE`，不删数据），再 `check` |
| `init` 报 schema 版本比脚本新 | 库是更新版本脚本建的；不要用旧脚本动它——换回新脚本或从备份恢复 |
| `core-refresh` 后「最近」没变 | ① facts 为空 ② 内容和上次一样（`[NOOP]`）③ `core.auto` 的 origin 被手工改成了 `manual`（脚本不覆盖 manual）。先跑 `mem.py check` 看 schema/字数 |
| journal 报「不认识的审计记录版本」 | `journal.jsonl` 里某行 `v` 不是 1；**不要手改/删行**，先备份文件再排查是不是新版本脚本写的 |
| `decay` 把"觉得重要"的归档了 | 先看 `importance`：`>=0.8` 有保护、永不自动归档；`<0.8` 且长期没用到（`last_used` 为空按创建日算）就会归档。要留就 `pin`/提高 importance，别改脚本阈值 |
| 她说话不像人设 / 不主动检索记忆 | DSH 只自动注入 `AGENTS.md`。先跑 `python3 ~/mingyue/scripts/apply-manual.py --check`：手工区不一致就重拼一次；再确认 `persona.md` / `rules.md` 内容真的写清了「何时 search、搜不到不许编」 |
| 到点定时任务没动静 | ① 引擎没在跑（重启后要先开 App 连一次，见 PLAN §4.10）② 任务被 paused/ended（`schedule_list` 看）③ 时间/时区写错（rrule 用 `DTSTART;TZID=Asia/Shanghai:…`） |
| 定时任务会话里 bash 报沙箱不可用 | Android 没有沙箱后端，新会话默认权限要设成 `danger-full-access`（无人值守没人点确认），见 `schedules/SETUP.md` 前置 2 |
| 沉淀任务报"没有候选" | 抽取任务失败或没写 `tmp/mingyue-extract.jsonl`；去抽取那个会话里看 ingest/写入的报错，不要手动编候选 |
| 任务会话被第二天抽进记忆 | `ingest` 应跳过"当天无真人消息"的会话；确认任务都是 `target.kind=new`，且没有被改成投递到聊天会话 |
| 贴日志时带出 token | 贴之前把 `?token=…` 抹掉 |

---

## 7. 图片发不出去（Termux 原生库，2026-11-17 实测）

### 症状

手机 App 发图报「发送失败：AI 正忙，稍后再试」（错误码实际是 `session/agent-busy`）；
电脑浏览器打开主机网页发图只显示「重试」；
**文字一切正常，`web.log` 里没有任何错误**。

### 真因

主机 Termux 上 DSH 的图片处理依赖 `sharp`，而 `sharp` 没有 Android 预编译二进制：

```
sharp: FAIL -> Could not load the "sharp" module using the android-arm64 runtime
```

处理逻辑在**主机**里，所以**两个客户端都失败**，而且失败发生在日志之前。

### 30 秒确认

```bash
ssh mingyue "sh ~/mingyue/scripts/probe-image.sh"
```

看 `sharp:` 那一行。`FAIL` 就到此为止——不是 App 的问题，不是网络，不是模型。

> 顺带：`ws://127.0.0.1:9231/ingest` 报错、`*.js.map` 404 都是噪音（客户端里的开发残留），主机上根本没有 9231。

### 处理

**首选：从源码编 sharp（2026-11-17 实测成功）**

```bash
sh ~/mingyue/scripts/build-sharp.sh          # 一次跑完：备份 → 装依赖 → 放行版本闸门 → 编译 → 验证
sh ~/mingyue/scripts/build-sharp.sh --verify # 只验证
sh ~/mingyue/scripts/build-sharp.sh --rollback
```

成功标志：`OK bytes=96`（在 Android 上真的生成了一张 8×8 PNG）。

顺手记下踩过的五个坑，将来重编还会遇到：

| # | 坑 | 正解 |
|---|---|---|
| 1 | `npm rebuild sharp --build-from-source` | npm 26 不认这个参数 |
| 2 | `npm rebuild sharp` 空转 | sharp 0.35 **没有 install 脚本**，必须 `npm run build` |
| 3 | `SHARP_IGNORE_GLOBAL_LIBVIPS=0` | 源码里 `Boolean("0") === true`，**会禁用系统 libvips**，别设 |
| 4 | `'glib-object.h' file not found` | 缺 `xorgproto` 导致 `pkg-config --cflags vips` 整体失败；装 `xorgproto`，并把 cflags 显式塞进 `CXXFLAGS` |
| 5 | `libvips version 8.18.7+ is required` | Termux 仓库只有 8.18.0；把 `common.h` 的 `VIPS_MICRO_VERSION < 7` 改成 `< 0`（micro 级兼容） |

**维护负担（必须知道）**：`npm i -g @deepseek-ai/dsh` 升级会把 sharp 覆盖回坏的 → **升级后重跑一次脚本**。备份在 `~/.cache/mingyue/sharp-backup`。

**不想编也可以**：

| 做法 | 成本 | 说明 |
|---|---|---|
| 接受纯文字 | 0 | 对"她"够用 |
| 图片发链接 | 0 | 你把图传到图床，把 URL 发给她，`fetch.py` 去读 |
| 换 Linux 主机（云） | 中 | glibc 环境 sharp 开箱可用 |

### 未定位：sharp 修好之后附件/图片仍然失败（2026-11-17）

编好 sharp 后（`OK bytes=96`）**发图和附件仍然失败**，说明 sharp 不是主因。已排除与未决：

| 项 | 结论 | 依据 |
|---|---|---|
| sharp | 已排除 | 编通并验证；重启引擎后仍失败 |
| 网络 / Tailscale | 已排除 | 文字收发正常 |
| 模型 / 账号渠道 | 已排除 | API Key 渠道同样失败 |
| 客户端差异 | 已排除 | App 与网页都失败 |
| 附件目录缺失 | 已排除 | `mkdir ~/.dsh/attachments` 后重启仍失败 |
| HTTP body 上限 | 已排除 | `--dump-config` 的 webserver 无上限配置 |
| 会话争抢 | 已排除 | 关掉 App 后网页仍失败 |
| 服务端日志 | **没有任何错误** | `web.log` 只有启动行与模型列表 |

**关键缺口**：拿不到服务端返回的原始错误码。App 只显示「附件上传失败」（图片显示「AI 正忙」，错误码 `session/agent-busy`），网页只显示「重试」，`web.log` 干净，HAR 里没有上传请求（上传走主 WebSocket，帧不进 HAR）。

**待做的判别实验（30 秒，决定是 App 还是主机）**：

> 在新手机上切到**本机引擎**，新建对话发一个 .txt。
> - 能发 → App 没问题，问题在这台 Termux 主机（引擎在 Bionic 环境下的缺陷）
> - 不能发 → App 自身的 bug，值得报上游

**如果不想继续查**：接受"文字 + 链接"，见上面的替代方案；上云（Linux 主机）后大概率自然恢复。

### 不要做

- **不要**以为"两个客户端都挂 = 客户端有 bug"——处理逻辑在主机里
- **不要**为这个去重建引擎、换账号、换模型
- **不要**把它当成记忆系统故障——和 `mem.py` 完全无关
- `ws://127.0.0.1:9231/ingest` 报错、`*.js.map` 404 都是噪音，主机上没有 9231

---

## 8. 记录新坑的格式

发现新问题时，往对应小节加一行即可，写清四件事：

1. **症状**（别人搜什么关键词能找到）
2. **真因**
3. **怎么在 30 秒内确认**
4. **不要做什么**（防止"修 A 弄坏 B"）
