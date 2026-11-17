# 交接：她会主动找来东西跟你讨论（2c 第二刀）

> 交给新窗口。**先做完 `docs/mingyue/HANDOFF-MORNING.md`（随机早安）再做这个**——
> 两者共用同一套"随机时刻投递"机制，早安那条会把机制跑通。

## 目标

她每天 **1–2 次**，随机时刻主动分享她**真的搜到并读过**的内容（视频 / 新番 / 游戏 / 资料），
并给出**自己的看法**，能接着跟你讨论。

不是转发机器：关键是"她为什么觉得你会感兴趣"。

## 已就绪

- 主机引擎自带联网工具（`--dump-config` 已确认）：
  - `web-search-deepseek`（搜索）
  - `web-deepseek-api`（fetch，走 DeepSeek fetch）
  - `web-fetch-http`（fetch，HTTP 兜底）
- `~/mingyue/reads/` 目录 + `reads/index.md`（她读过/分享过的索引，已在人设里被引用）
- 记忆系统：`python3 ~/mingyue/scripts/mem.py search/add-episode/...`
- 随机投递机制：见 `HANDOFF-MORNING.md`（`morning-schedule.sh` 可扩展成通用 `random-ping.sh`）

## 前置验证（必须先做）

在 App 里让她**真的搜一次**（例如「搜一下最近有什么新番」），确认：

1. 她调用了搜索工具（不是凭训练数据编）
2. 没报凭证错误

| 结果 | 处理 |
|---|---|
| 正常 | 继续 |
| 报错/空 | 引擎 web 工具缺凭证（账号登录未必带 API key）。查 `web-deepseek-api` 的 key 配置，必要时单独配一个 DeepSeek API key；`web-fetch-http` 可作兜底 |
| 不调用工具 | 行为规范里必须写死「分享前必须 web_search + web_fetch，没读过不许发」 |

## 能力实测（2026-11-17，已经跑过）

主机已装 `yt-dlp`（`pip3 install yt-dlp`），实测：

| 能力 | 结果 | 命令/说明 |
|---|---|---|
| 视频元数据 | ✅ | `yt-dlp --skip-download --print "标题: %(title)s" <url>` |
| **弹幕** | ✅ 122 KB XML | `yt-dlp --skip-download --write-subs --sub-langs danmaku -o ...` |
| **热评** | ✅ 免登录 | `curl "https://api.bilibili.com/x/v2/reply?type=1&oid=<aid>&sort=2&ps=3"` |
| aid/bvid 互查 | ✅ | `curl "https://api.bilibili.com/x/web-interface/view?bvid=<BV号>"` |
| B站搜索（yt-dlp `bilisearch:`） | ❌ HTTP 412 风控 | 改用她的 `web_search`，或 curl `x/web-interface/search/type`（主机实测 200） |
| CC 字幕 | ⚠️ 看视频 | 有 AI 字幕的视频需登录 cookie（SESSDATA）才能取；没有就只拿弹幕 |
| 真看画面 | ❌ 不做 | 要下载+抽帧+视觉模型，手机扛不住也没必要 |

现成探针：`mingyue/scripts/probe-bilibili.sh`、`mingyue/scripts/probe-bilibili-search.sh`。

**弹幕是这里的关键信号**：它反映观众在笑什么、哪段最好看、有没有被坑，比"标题"可靠得多，而且**完全免登录**。

## 隐私红线（用户明确要求）

- **不给她 B 站账号**，不写自动评论、自动登录、自动互动
- 她只做：读（元数据/弹幕/热评）→ 判断 → 发链接给用户
- 如果将来要接登录 cookie，必须由用户自己在主机上写，不经过任何脚本参数或聊天记录

## 架构

复用早安那套随机投递：

```
每天 2 个窗口（例：12:00–14:00、21:00–23:00）
  └─ 每个窗口随机挑一刻 → 一次性任务投递到用户会话
       prompt: 读 ~/mingyue/schedules/share-moment.md，严格按里面的步骤执行。
```

- 也可以一天只跑一个窗口，验证通了再加第二个
- 需要 `~/mingyue/share.json`：窗口、每日次数、目标会话、跳过概率

## 行为规范 `schedules/share-moment.md`（新写）

要点：

1. **先搜再说话**：`web_search` 找候选 → `web_fetch` 读到实际内容 → 才能分享。
   没读到就只能说"看到一个标题，还没细看"，不许描述没读过的内容。
2. **挑的时候想你**：CORE 记忆 + 最近对话里的偏好（游戏/番/领域）优先。
3. **去重**：先看 `reads/index.md`，最近 2 周发过的不再发（除非有新进展）。
4. **写法**：
   - 一句话说"为什么发你"（她的理由，不是介绍）
   - 给链接
   - 一句她自己的判断/期待/吐槽
   - 三到五句封顶
5. **记录**：分享后往 `reads/index.md` 追加一行（日期、标题、链接、她的一句话看法）。
6. **讨论**：用户回应后，把他的态度写进记忆（`add-episode` 或 fact）——喜欢什么、无感什么。
7. **频率自适应**：连续几次用户无感，就降频（隔天/降概率）；用户主动问就多找。

## 关键约束

- **不许编造内容**：所有分享必须来自当次真实的 search + fetch
- **不许重复**：`reads/index.md` 是硬约束
- **不许刷屏**：一天最多 2 条；用户没回应也**不追问**
- 链接只发真实抓到的 URL，不发猜的
- 失败要留痕：`~/mingyue/tmp/share.log`

## 已知风险

1. **B 站搜索被风控（412）**：不要用 `yt-dlp bilisearch:`。用她的 `web_search`，或 curl `x/web-interface/search/type`（要带 `User-Agent` + `Referer: https://www.bilibili.com`）。
2. **字幕多半拿不到**：没有登录 cookie 时只有弹幕。判断"有没有意思"主要靠 **标题 + 弹幕 + 热评**，别指望字幕。
3. **接口会变/会限流**：脚本要限速（每次分享最多 3 个视频的查询），失败就跳过，不要重试轰炸。
4. **引擎不自启**：早上那条同理。
5. **口味偏差**：一开始她挑的东西可能不合口味——把她收到的每条反馈都记进记忆，两周后应该明显变准。

## 验收

- 连着几天，她发来的东西里**至少一半你会想点开**
- 她说的"为什么发你"能让你觉得"她确实知道我喜欢什么"
- 没有重复、没有编造、没有一天三条以上
