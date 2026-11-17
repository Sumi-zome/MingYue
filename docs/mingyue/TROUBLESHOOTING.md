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

### 已解决：真正的根因是 Android 拒绝两个系统调用（2026-11-17）

sharp 只是第一层。继续往下挖，发现**四处**上游 DSH 在 Android 上的不兼容，全都表现为"发图片/附件失败，日志里什么都没"：

| # | 根因 | 症状指纹 | 修法 |
|---|---|---|---|
| ① | `sharp` 无 android-arm64 预编译包 | `Could not load the "sharp" module using the android-arm64 runtime` | 从源码编译（见上一节） |
| ② | 落盘前**向上 fsync 到文件系统根**，撞上不可读的 `/data/data` | `EACCES: permission denied, open '/data/data'` | `syncDirectory` 遇 EACCES/EPERM/ENOENT 时跳过（尽力而为） |
| ③ | 内容寻址用**硬链接**去重，Android 拒绝 `link()` | `EACCES ... link '…/tmp/…' -> '…/file-objects/…'` | 硬链接失败退化为 `copyFile` |
| ④ | 错误被 `catch` 吞掉，只回 `gateway/internal` / `ATTACHMENT_WRITE_FAILED` | 日志干净、客户端只看到笼统错误 | 在 catch 里 `console.error` 打出底层错误 |

**一条命令修全部（幂等，带备份）**：

```bash
bash ~/mingyue/scripts/fix-termux.sh          # 应用/修复全部补丁
bash ~/mingyue/scripts/fix-termux.sh --check  # 只检查
```

`status.sh` 已经接了这个检查，每次看状态就能知道补丁还在不在。

**升级必读**：`npm i -g @deepseek-ai/dsh` 会覆盖 `node_modules` 里的**补丁和 sharp 编译产物**——升级后必须重跑一次 `fix-termux.sh`，否则附件又会坏。

升级操作顺序：

```bash
bash ~/mingyue/scripts/status.sh                # 升级前：确认现在是好的
npm i -g @deepseek-ai/dsh@<目标版本>             # 升级（注意 App 的版本耦合，见 UPSTREAM.md）
bash ~/mingyue/scripts/fix-termux.sh --check    # 升级后：看缺了哪些
bash ~/mingyue/scripts/fix-termux.sh            # 一条命令补齐
# 然后在 App 里重启托管的 DSH，发一张图验证
```

两个安全设计：

- **补丁是"认字符串"的**：上游改了那几行代码，脚本会**中止并还原**，不会留下半截状态。真中止了就把输出贴出来，补丁要跟着改。
- **备份按版本隔离**（`~/.cache/mingyue/*-backup-<版本>`）：升级后不会误把旧版本文件还原进新版本。

**怎么走到这里的（值得记住的方法）**：

1. 客户端日志、`web.log`、HAR 全都沉默 → 别猜，**直接打 HTTP 端点**（`probe-upload.sh`）拿原始错误码
2. 错误码被归类后仍不透明 → **在 catch 里加日志**（patch ④），让底层错误说话
3. 每修一层都会露出下一层——**不要因为"修了还不行"就否定方向**，要看错误有没有变化

### 不要做

- **不要**以为"两个客户端都挂 = 客户端有 bug"——处理逻辑在主机里
- **不要**为这个去重建引擎、换账号、换模型
- **不要**把它当成记忆系统故障——和 `mem.py` 完全无关
- `ws://127.0.0.1:9231/ingest` 报错、`*.js.map` 404 都是噪音（客户端里的开发残留），主机上没有 9231
- **不要**只改 `node_modules` 就以为万事大吉——升级后重跑 `fix-termux.sh`

---

## 8. 主动说话（阶段 2c）的坑

> 机制与日常命令见 [PROACTIVE.md](PROACTIVE.md)。这里只记踩过的坑。

### 8.1 到点了，她的消息没出现在聊天里

| 症状 | 真因 | 30 秒确认 |
|---|---|---|
| 定时任务列表里有「溟月·早安/分享」，到点后会话里没有消息 | `target.kind` 被建成了 `new`：她在一个新会话里自言自语，你在聊天里看不到 | 读 `~/.dsh/storages/schedule.json`：任务的 `target.kind` 必须是 `session` 且 `sessionId` 是你正在聊的那个 |

```bash
python3 - <<'PY'
import json, os
d = json.load(open(os.path.expanduser('~/.dsh/storages/schedule.json')))
for t in d['tables']['tasks'].values():
    r = t['record']
    if r.get('title') in ('溟月·早安', '溟月·分享'):
        print(r['title'], t['status'], r['scheduledAt'], t['target'], (t.get('lastDelivery') or {}).get('targetSessionId'))
PY
```

`lastDelivery` 不为空就说明**投递成功**（别翻聊天记录判断）。`target` 是 `new` 就把当天那条删掉、按
`PROACTIVE.md` §4 用 `--set-target` 重建。

### 8.2 定时任务会话整轮失败：`no adapter registered for provider "amazon-bedrock"`

- **症状**：到点投递进去了，但那一轮没有任何回复；会话日志里是 `NO_ADAPTER`。手动聊天正常（App 里选过模型）。
- **真因**：profile 的默认模型（`~/.dsh/profiles/web/cordis.patch.yml` 的 `agent-default-model`）被设成了
  `amazon-bedrock / anthropic.claude-fable-5-1`，主机没有 bedrock 适配器。聊天没事是因为 App 给每个会话显式选了模型；
  **定时任务新建的会话走默认模型**，整轮失败。
- **修**：`sh ~/mingyue/scripts/fix-default-model.sh`（改成 `deepseek-account / deepseek-flash`，带备份），
  再在 App 里重启托管的 DSH 让配置生效。验证：建一条 `--in 120` 的测试任务，看它真的回了话。

### 8.3 她收到提醒却回"文件不存在，没步骤可跑"

- **真因**：`~/mingyue/schedules/morning-hello.md` / `share-moment.md` 没 scp 到主机（仓库里有、主机上没有）。
- **修**：`scp mingyue/schedules/*.md mingyue:mingyue/schedules/`。
- **这其实是正确行为**：她没编，如实报了缺文件。以后改行为规范记得同步到主机。

### 8.4 手动重跑 `morning-schedule.sh` 什么都不做

- **症状**：输出"今天已经安排过：… 跳过"。
- **真因**：`~/mingyue/tmp/morning-state.json` 记了今天（幂等，防重复）。
- **修**：要重排就加 `--force`；只是看看就用 `--dry-run`；测试投递用 `--in 180`（不写幂等标记）。

### 8.5 `web_fetch` 偶发 `DeepSeek API error (HTTP 404)`

- **症状**：`tool/result` 里是 `Error: DeepSeek API error (HTTP 404): failed to fetch URL`，同一轮后面又成功了。
- **真因**：`web-deepseek-api` 的 fetch 端点对个别 URL 404；工具会自动走 `web-fetch-http` 兜底。
- **处理**：换候选或再试一次即可；连续失败就按"没读到"处理（`share-moment.md` 已写死"没读过不许发"）。
  凭证错误是另一回事（会明确报 `WEB_PROVIDER_CREDENTIAL_MISSING`）；**正常路径不要求单独配 API key**——
  会话模型是 `deepseek-account/…` 时，搜索/对话用账号登录态。

### 8.6 B 站弹幕只解析出一条

- **真因**：弹幕 XML 整篇是一行，`sed` 的贪婪匹配只会命中最后一条。
- **修**：先 `sed 's|</d>|</d>\n|g'` 断行再逐条取（`bili-read.sh` 已这么写）；不要改用下载视频再抽帧，手机扛不住。

### 8.7 不要做的

- 不要为了"一定能说上话"加多重试/兜底投递——宁少勿多，失败留痕即可。
- 不要把 `target.kind` 改成 `new_once` 来"复用会话"：那会绑到第一次投递的会话，反而更偏。
- 不要给她 B 站账号 / 登录 cookie：分享只读公开接口（弹幕、热评、元数据），登录 cookie 由用户自己决定、绝不进脚本参数或聊天。
- 不要用 `yt-dlp bilisearch:` 搜 B 站（412 风控）；搜索用她的 `web_search` 工具。

---

## 9. 记录新坑的格式

发现新问题时，往对应小节加一行即可，写清四件事：

1. **症状**（别人搜什么关键词能找到）
2. **真因**
3. **怎么在 30 秒内确认**
4. **不要做什么**（防止"修 A 弄坏 B"）
