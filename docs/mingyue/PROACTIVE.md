# 溟月 · 主动说话（阶段 2c）

> 2026-11-17 上线并实测。两种主动行为共用一套"随机时刻投递"机制：
> **随机早安**（每天 08:00–10:30 随机一刻）+ **主动分享**（12:00–14:00 / 21:00–23:00 各一次）。
> 配套：[PLAN.md](PLAN.md) §6.6 / §12（窗口 D）、[TROUBLESHOOTING.md](TROUBLESHOOTING.md) §9、
> 交接原文 [HANDOFF-MORNING.md](HANDOFF-MORNING.md) / [HANDOFF-SHARE.md](HANDOFF-SHARE.md)。

---

## 1. 机制：定时任务投递到"你正在聊的那个会话"

```
每天 00:05  定时任务「溟月·安排早安」（target=new，cwd=~/mingyue）
            prompt: 运行 bash ~/mingyue/scripts/morning-schedule.sh
            └─ ping.py 在 08:00–10:30 里随机挑一刻
                 → RPC schedule/create
                   timing: {"kind":"at","at":"2026-11-18T09:12:33+08:00"}
                   target: {"kind":"session","sessionId":"<用户会话>"}
每天 00:10  定时任务「溟月·安排分享」（同上，share-schedule.sh）
            └─ 12:00–14:00、21:00–23:00 各挑一刻（每个窗口 15% 概率跳过）

随机时刻      一次性任务把 prompt 投递到**用户会话**里 → 她按行为规范说话
```

**为什么必须是 `session` target**：`target.kind = new` 会让每次投递新建一个会话，她在那里面自言自语，你在聊天里根本看不到。这是本阶段最容易踩的坑。

**一天最多几条**：早安 1 条；分享每个窗口最多 1 条（窗口 15% 概率整段跳过），所以一天最多 2 条。他不回，她不追问、不补发。

**为什么需要 00:05 的规划任务**：引擎的 `schedule/create` 只接受严格未来的时刻，不能提前一天写好"随机时间"；每天零点后现算现建，一次性任务到点即 `ended`，第二天重新建一条。

---

## 2. 文件

| 文件 | 作用 |
|---|---|
| `mingyue/scripts/ping.py` | 全部逻辑：读配置、随机取时刻、换 cookie、`schedule/create`、幂等、日志 |
| `mingyue/scripts/morning-schedule.sh` | 早安入口（`ping.py --config morning.json`） |
| `mingyue/scripts/share-schedule.sh` | 分享入口（`ping.py --config share.json`） |
| `mingyue/scripts/bili-read.sh` | 读 B 站视频的公开信号：元数据 + 弹幕采样 + 热评（免登录、只读） |
| `mingyue/schedules/morning-hello.md` | 早安的行为规范（说什么、禁止什么） |
| `mingyue/schedules/share-moment.md` | 分享的行为规范（先搜再说话、去重、写法、失败怎么办） |
| `~/mingyue/morning.json` | 运行期配置（目标会话、窗口、跳过概率），**不进仓库** |
| `~/mingyue/share.json` | 同上，分享用 |
| `~/mingyue/tmp/morning-state.json` / `share-state.json` | 幂等标记：当天已规划就不再建 |
| `~/mingyue/tmp/morning.log` / `share.log` | 每次规划的结果与原始错误 |
| `~/mingyue/reads/index.md` | 她读过/分享过的索引；分享后追加一行，去重靠它 |

## 3. 配置

```json
{
  "targetSessionId": "session-12508eb5-449c-4689-a1a2-0bb47247c26f",
  "title": "溟月·早安",
  "prompt": "读 ~/mingyue/schedules/morning-hello.md，严格按里面的步骤执行。",
  "windows": [["08:00", "10:30"]],
  "skipChance": 0
}
```

- `targetSessionId`：**App 里你正在聊的那个会话**。换了主聊天会话就要重设（见下）。
- `windows`：可多个窗口；`skipChance` **按窗口**独立掷一次（分享用 0.15）。
- `title` / `prompt` 由配置给，连定时任务列表里显示的名字一起可改。

## 4. 常用命令（主机上）

```bash
bash ~/mingyue/scripts/morning-schedule.sh --status        # 配置 + 今天安排 + 日志尾部
bash ~/mingyue/scripts/morning-schedule.sh --dry-run       # 只算时间、打印请求体
bash ~/mingyue/scripts/morning-schedule.sh                 # 规划今天（幂等）
bash ~/mingyue/scripts/morning-schedule.sh --force         # 忽略今天的幂等标记
bash ~/mingyue/scripts/morning-schedule.sh --in 180        # 测试：now+180 秒投递（不写幂等标记）
bash ~/mingyue/scripts/morning-schedule.sh --set-target session-…   # 换目标会话（会先校验存在）

bash ~/mingyue/scripts/share-schedule.sh --dry-run         # 分享同理
bash ~/mingyue/scripts/bili-read.sh "https://www.bilibili.com/video/BV…"  # 手动读一个 B 站视频
```

脚本永远不打印 token；失败会打印原始原因并退出非 0。

## 5. 迁移 / 重建（定时任务不在备份包里）

按 [SETUP.md](../../mingyue/schedules/SETUP.md) 的前置检查做完后，把下面这段贴给主机上的 agent：

```
这台主机上有一个自用项目「溟月」，目录在 ~/mingyue。请用 schedule_create 建两条"规划任务"，
一条一条建，每建完一条先用 schedule_list 确认时间/时区/target，再建下一条。

统一要求：
- 时区 Asia/Shanghai；target 一律是 {"kind":"new","create":{"cwd":"/data/data/com.termux/files/home/mingyue"}}。
- 都是"新会话"任务，不会和你现在的对话混在一起；不需要你回复用户，按 prompt 执行即可。

1) title: 溟月·安排早安
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T000500
          RRULE:FREQ=DAILY
   prompt: 运行 bash ~/mingyue/scripts/morning-schedule.sh，只做这一件事，不要额外说话。

2) title: 溟月·安排分享
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T001000
          RRULE:FREQ=DAILY
   prompt: 运行 bash ~/mingyue/scripts/share-schedule.sh，只做这一件事，不要额外说话。
```

然后在新主机上写 `~/mingyue/morning.json` / `share.json`（`--set-target` 会帮你写第一项），
跑一次 `--dry-run` 确认窗口和请求体，再 `--in 180` 做一次真实投递验证。

## 6. 2026-11-17 实测记录（旧手机）

- **RPC 形状**（从引擎源码 `@deepseek-ai/dsh-schedule/lib/index.js` 核实，并用 curl 实打）：
  `POST /api/schedule/create`，信封
  `{"type":"client-request","rpcId":"…","method":"schedule/create","payload":{"args":{"request":{…}}}}`；
  `timing` 是 `{"kind":"at","at":"<RFC3339 带显式时区偏移>"}`；`target` 是 `{"kind":"session","sessionId":…}`。
  成功返回 catalog entry（含 `id` / `scheduledAt`），失败是 HTTP 200 + `result.ok=false`。
- **随机窗口**：20:06–20:14 窗口摇到 20:07:00；多窗口 dry-run 各摇一个、互不影响。
- **到点投递**：19:58:17 的任务在 19:58:17.2 投递进用户会话，`lastDelivery.targetSessionId` 正确；她当轮回复。
- **她按规范说话**：morning-hello.md 缺失时她如实报"文件不存在，没步骤可跑"（没有编）；补齐后照规范回了 1–3 句。
- **联网工具**（分享前置验证）：在她的会话里 `web_search` + `web_fetch` 真实调用、返回真实来源，无凭证错误。
  部分 URL 的 DeepSeek fetch 会 404，随后自动走 `web-fetch-http` 成功。
- **分享端到端**（临时会话，不打扰用户）：读 share-moment.md → 查 CORE/记忆 → `web_search` → `web_fetch` →
  写出"为什么发你" + 链接 + 自己的判断 → 往 `reads/index.md` 追加一行。
- **B 站读取**：`bili-read.sh` 实测拿到 122 KB 弹幕（采样 40 条）+ 热评（77 万赞等真实数据），全程免登录。

## 7. 已知限制

1. **引擎不自启**：手机重启后 `dsh web` 不会自己起来（[PLAN.md](PLAN.md) §4.10）。00:05/00:10 没跑 → 当天没有早安/分享；
   晚上断网也会影响投递。接受这个限制，别为了它加重试。
2. **目标会话会变**：这个机制投递到**指定的会话 id**。你在 App 里换了新的主聊天会话，就要在主机上
   `--set-target <新会话id>`（或者把配置里的 `targetSessionId` 改掉），否则她还在旧会话里说话。
3. **跳过不是失败**：窗口整段过去（引擎晚起/手动补跑）就跳过那个窗口，日志里写"已经过去"。
4. **分享靠她当次真的读**：网页接口会变、会限流；`share-moment.md` 写死了"没读过不许发"，失败就跳过这次。
5. **`morning.json` / `share.json` 是运行期文件**，不进备份包也不进仓库；重建主机时按 §5 重写。

## 8. 排障

先看 `TROUBLESHOOTING.md` §9；30 秒定位：

```bash
bash ~/mingyue/scripts/morning-schedule.sh --status   # 今天安排了什么
tail -n 20 ~/mingyue/tmp/morning.log                  # 规划失败原因（原始响应）
python3 - <<'PY'                                      # 到点到底投递了没有
import json, os
d = json.load(open(os.path.expanduser('~/.dsh/storages/schedule.json')))
for t in d['tables']['tasks'].values():
    if t['record'].get('title') in ('溟月·早安', '溟月·分享'):
        print(t['status'], t['record']['scheduledAt'], t.get('lastDelivery'))
PY
```
