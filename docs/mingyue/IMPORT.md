# 溟月 · 历史语料导入

> 2026-11-16。配套 [PLAN.md](PLAN.md) 与 [MEMORY.md](MEMORY.md)。
> 目标：把你在 DeepSeek 网页端几年的聊天，变成**她记得的事**和**她的性格底色**。

---

## 0.1 两条线：存档（复刻）与记忆（蒸馏）

用户要的是**复刻聊天**，不是只要记忆。所以拆成两条独立的路：

| | **2d-a 存档线（复刻）** | **2d-b 记忆线（蒸馏）** |
|---|---|---|
| 目标 | 完整保真，能翻、能搜、能引用原话 | 提炼成她"记得"的条目 |
| 保留什么 | **全部**：REQUEST / RESPONSE / **THINK** / TOOL_* / FILE / 附件图片 | 只 REQUEST / RESPONSE 正文 |
| 产物 | `~/archive/`：`archive.db`（FTS5 全文索引）+ 按会话渲染的 Markdown + 附件原图 | `memory.db` 的 episodes / facts |
| 模型调用 | **0 次**（纯转换 + 建索引） | 每会话一次蒸馏，要花钱 |
| 她能用来干嘛 | `archive.py search "关键词"` 找回原话；`archive.py show <会话>` 读完整对话 | 日常聊天时自然想起"你去年说过…" |
| 依赖 | 无（先做） | 依赖 2d-a 的解析器 + 阶段 2f 的权重策略 |

**为什么存档要保留 THINK / TOOL / FILE**：那是"当时到底发生了什么"的完整现场——
她想了什么、搜了什么、你发了什么图。丢掉就不是复刻了。

**为什么记忆线要丢掉它们**：34,207 条消息里 21,910 条是 THINK、17,451 条是工具调用，
全塞进记忆只会把 `facts` 淹掉。记忆要的是"事实"，不是"过程"。

**硬限制**：旧聊天不能变成 DSH 会话（引擎私有格式，见 §0 表格）。但"复刻"不需要会话——
存档 + 全文检索已经能让她随时翻到原话。

---

## 0. 先说清楚：不是导入会话，是导入记忆

| | 能不能做 | 说明 |
|---|---|---|
| **把旧会话变成 DSH 里的会话** | ❌ 做不到 | DSH 没有会话导入接口，会话是引擎私有格式。硬做要改引擎，等于长期跟着上游打补丁 |
| **把旧会话变成她的记忆** | ✅ 就是这篇 | 抽取成 `episodes`（聊过什么）、`facts`（关于你的事实）、`arcs`（那阵子的主题） |

所以导入的产物是 **`memory.db` 里的条目**，不是会话列表里多出几百个对话。你要翻旧聊天，看 `archive/` 里的 Markdown；要她"记得"，靠记忆库。

---

## 1. 数据从哪来（2026-11-18 实测真实格式）

**不是 Markdown**，是 `deepseek_data-YYYY-MM-DD.zip`（实测样本 220 MB，`manifest.json` 里
`export_format_version: 3`）：

```
deepseek_data-2026-11-18.zip
├─ manifest.json              {"export_format_version": 3}
├─ user.json                  账号信息（user_id/email/mobile/oauth_profiles）⚠️ 永不导入
├─ chat_session_index.json    数组，每项 {id, title, pinned, message_count, inserted_at, updated_at}
└─ chat_sessions/
   ├─ <uuid>.json             每个会话一个文件
   └─ <uuid>_files/           该会话的附件（图片等）
```

**会话 JSON**：

```json
{"id","title","pinned","current_message_id","inserted_at","updated_at",
 "messages":[{"id","parent_id","role","status","thinking_enabled","search_enabled",
              "accumulated_token_usage","inserted_at",
              "fragments":[{"type","content"}]}]}
```

`role ∈ {USER, ASSISTANT}`；`inserted_at` 是 **UTC ISO8601**（`2026-05-12T12:42:26.259Z`），
入库前要换成 `Asia/Shanghai` 的本地日期。

**fragment 类型**（全量 1013 个会话实测计数）：

| type | 条数 | 字段 | 导入时怎么处理 |
|---|---|---|---|
| `REQUEST` | 16,714 | content | ✅ 用户说的话 → 正文 |
| `RESPONSE` | 17,137 | content | ✅ 助手说的话 → 正文 |
| `THINK` | 21,910 | content, elapsed_secs | ❌ 思维链，丢弃 |
| `TOOL_SEARCH` | 4,870 | queries, results, status | ⚠️ 压成一行「搜了 X」或不进正文 |
| `TOOL_OPEN` | 12,581 | title, url, snippet, site_name, published_at | ⚠️ 同上，最多留标题 |
| `CONTENT_RISK` | 2,243 | content, style | ⚠️ 被审查替换的内容，标出来别当事实 |
| `FILE` | 372 | files | ⚠️ 只记「发过图/文件」，不解析图片 |
| `TEMPLATE_RESPONSE` | 102 | content | ❌ 模板拒答（"暂时无法回答"），丢弃 |
| `TOOL_IMAGE_SEARCH` / `TOOL_FIND` | 4 / 2 | — | ❌ 丢弃 |

**规模（实测）**：1013 个会话、34,207 条消息（USER 16,791 / ASSISTANT 17,416）、
正文合计约 **60.5 MB**；单个会话最多 485 条消息。

> 上表"导入时怎么处理"是**记忆线（2d-b）**的处理方式。
> **存档线（2d-a）全部保留**，包括 THINK / TOOL_* / FILE 和附件图片。

**解析器以这段规格为准**，不要按"Markdown 分隔符"去猜。

---

## 2. 流水线（离线批处理，不实时）

```
zip（只读，不解到记忆目录）
  → ① 遍历 chat_sessions/*.json（user.json 永不读）
  → ② 每会话按 messages[].inserted_at 换算本地日期分组（一个会话可能跨天）
  → ③ 去重：sha256(title + 前几条正文) 存 import_state.json，重跑跳过
  → ④ 脱敏：API Key / 手机号 / 身份证 / 密码 打码
  → ⑤ 过滤：THINK / TEMPLATE_RESPONSE / 纯 TOOL_* 丢弃；
        轮数太少（<3 轮真人往返）、纯寒暄的只计数不蒸馏
        ↓
  → ⑥ 每个"会话-天"蒸馏一次（模型）：产出
        {summary, topics[], facts[], emotional_tone, importance}
  → ⑦ 主题聚类：把 topics 聚成主题线（"考研"、"毕设"、"找工作"）
  → ⑧ 稳定事实：跨对话重复出现的事实 → facts，evidence_count = 出现次数
  → ⑨ 写库：episodes / facts 全部 source_type='import'，confidence 0.5（schema 需先对齐，见 §8）
  → ⑩ 生成初始 me.md + narrative 草稿（**给你确认后才进 core**）
```

**为什么分两步（⑥ 蒸馏 → ⑧ 事实）**：单条对话里说的事只进 `episodes`；只有跨对话反复出现的才升级成 `facts`。这正好复用 [MEMORY.md](MEMORY.md) §11.1 的 `evidence_count` 门控——**几年的聊天天然带证据**，不用另发明规则。

---

## 2.1 存档线（2d-a）：实现规格

目标：**零模型调用**，把 zip 变成可检索、可翻阅的完整档案。

### 位置（主机上）

```
~/archive/                              ← 不在 ~/mingyue 里，备份要排除
├─ deepseek_data-2026-11-18.zip         原包保留（220 MB，只读不删）
├─ archive.db                           SQLite：会话/消息/片段 + FTS5 全文索引
├─ rendered/<session-id>.md             每个会话渲染成 Markdown（含思考/工具/图片引用）
└─ files/<session-id>/<filename>        附件原图（按需从 zip 解出）
```

### `archive.db` 表结构（建议）

```sql
sessions(id TEXT PRIMARY KEY, title TEXT, pinned INT, inserted_at TEXT, updated_at TEXT, message_count INT)
messages(id TEXT PRIMARY KEY, session_id TEXT, seq INT, role TEXT, inserted_at TEXT, status TEXT)
fragments(message_id TEXT, ord INT, type TEXT, content TEXT, meta TEXT)   -- meta: 工具参数/结果/文件列表
files(fragment_message_id TEXT, ord INT, name TEXT, path TEXT)            -- 指向 files/<session-id>/
archive_fts(content, session_id, message_id)                              -- FTS5 tokenize='trigram'（中文）
```

### `mingyue/scripts/archive.py` 子命令

| 命令 | 作用 |
|---|---|
| `init --zip <path>` | 解析 zip → archive.db（幂等：按 session id + 内容 hash 跳过已导入） |
| `stats` | 会话数 / 消息数 / 片段数 / 附件数 / 时间跨度 |
| `search "关键词" [-k 8]` | FTS5 检索，返回 `[会话标题 · 日期] 角色: 片段`（≤N 条，每条截断） |
| `show <session-id> [--thinking]` | 打印完整会话；默认折叠 THINK，`--thinking` 展开 |
| `render <session-id>` | 生成 `rendered/<id>.md`（含 THINK 折叠块、TOOL 调用、图片相对路径） |
| `export-md` | 批量渲染全部会话（可选，占空间） |

### 她怎么用（接进 `rules.md`）

问"你还记得我去年说过 X 吗 / 那时候我们聊的啥"时：

1. 先 `python3 ~/mingyue/scripts/mem.py search "关键词"`（提炼过的记忆，快）
2. 没有再 `python3 ~/mingyue/scripts/archive.py search "关键词"`（原文档案）
3. 引用时可以说"翻到当时的记录了"，但**不许编造**没搜到的内容

### 体积与备份

- 正文约 60.5 MB，加上 THINK/TOOL 全量后文本可能 **150–200 MB**；FTS5 trigram 索引再 +1.5×
- 手机还剩 135 GB，放得下
- **`export.sh` 必须排除 `~/archive/`**——否则每次备份都多几百 MB
- 隐私：`user.json` 永不导入；`archive.db` 里只有聊天内容，没有账号信息

### 她能继续聊（接续旧会话）

存档不只是"看"，还要能**接着聊**。做法：

```
archive.py resume <session-id> [--tail N | --full | --summary] [--thinking]
  → 用引擎 RPC 新建一个 DSH 会话（cwd=~/mingyue，preset=standard，人设/记忆照常）
  → 把这段旧对话作为第一条消息灌进去：
      「以下是我们以前在 DeepSeek 上的一段对话（2026-05-12 起，共 37 轮）。
        把它当成我们已经聊过的历史，不要总结、不要复述，只回一句表示接上了。」
      + 历史正文（按模式截取）
  → 她在那个会话里回一句，上下文就落进 DSH 会话了
  → 你在 App 的会话列表里找到它，直接接着聊
```

**三种模式**（按旧会话大小选）：

| 模式 | 内容 | 适用 |
|---|---|---|
| `--tail N`（默认 40） | 最后 N 条消息逐字 | 长会话（几百轮），保住最近的语境 |
| `--summary` | 先蒸馏一段摘要 + 最后 10 条逐字 | 超长会话（几十万 token 那种）；多一次模型调用 |
| `--full` | 全部正文 | 短会话（≤50 轮）；要确认上下文预算（deepseek-flash 窗口 1M token） |
| `--thinking`（附加） | 连 THINK 一起灌 | 想让"她当时怎么想的"也保留；token 会涨很多 |

**限制（说清楚）**：

- **图片带不回去**：旧对话里的图要你看时从存档翻，或重新发一次
- **不是同一个会话**：新会话 id 是新的，旧的只读留在档案里
- **超长会话必须摘要**：485 条消息那种整段灌进去会超预算，脚本要先估算 token 再决定模式
- **只影响这一个新会话**：其他会话、她的记忆、人设都不变

实现要点：引擎 RPC 用和 `probe-upload.sh` 一样的认证（`GET /?token=` 换 cookie → `POST /api/<method>`）；
建会话后**必须发一次 prompt** 上下文才进会话历史（这一步会有一次模型调用，成本很低）。

## 2.2 能不能直接导入成 DSH 会话？（2026-11-18 讨论）

**先说结论**：网页导出的 JSON 和 DSH 会话**不是同一层东西**，但"合成会话"值得做一次实验，
成功就是真正的"直接导入、直接继续"。

### 为什么不是"兼容一下"就行

| | DeepSeek 网页导出 | DSH 会话 |
|---|---|---|
| 本质 | 聊天产品的**消息数据** | 引擎的**事件日志**（`session.v4.jsonl.zstd` 多帧 zstd） |
| 内容 | 消息 + fragments（思考/搜索/文件） | `user/message`、`assistant/message`、`tool/call`、`turn/end` 等事件流 + turn/step 边界 + 请求 header |
| 附带状态 | 无 | 会话锁、投影缓存（`storages/session_projcache`）、重启后的重放校验 |
| 使用方 | 网页聊天服务 | DSH 引擎（工具、预设、权限、沙箱） |

同一家公司，但是两条产品线。类比：微信聊天记录导出不能直接塞进 Slack。

### 实验方案（先验证，再决定要不要实现）

**目标**：不 patch 引擎，而是生成一个**合成会话文件**，看引擎接不接受。

```
旧对话 → 生成 session.v4.jsonl.zstd（header + 逐条 user/message、assistant/message 事件）
       → 放进 ~/.dsh/sessions/<工作区>/session-<uuid>/
       → 验证三点：session/list 认不认 → App 能不能打开 → 能不能接着聊
```

**隔离要求（必须照做）**：

1. 用一次性工作区（如 `~/synth`），不碰 `~/mingyue` 的会话
2. 先拿**最小真实会话**（5–10 条消息）试，不要拿 485 条那种
3. 失败就删掉整个目录，不留半成品
4. 不修改引擎任何文件（只往会话根写一个会话目录）

**判定标准**：

| 结果 | 结论 |
|---|---|
| App 能列出、能打开、能接着聊 | ✅ 做 `archive.py import-session`，这才是真正的"直接导入直接继续" |
| 能列出但打不开/显示乱 | ⚠️ 事件结构还差东西，需要对着真实会话 diff |
| 列表里根本不出现 | ❌ 引擎有校验，放弃合成，退回 `resume`（新会话 + 历史作开局） |

**风险**：① 引擎可能校验 seq/turn 边界，合成不对会被拒或显示异常
② DSH 升级后要重新验证（和 Termux 补丁同一性质）
③ 写坏可能影响会话存储，所以必须隔离 + 可一键删除

### 两种方案的取舍

| | 合成会话导入 | `resume` 接续 |
|---|---|---|
| 体验 | 旧消息一条条在会话里，最像"原生继续" | 新会话，旧历史作为开局一条大消息 |
| 风险 | 中（依赖引擎内部格式） | 低（只用公开 RPC） |
| 维护 | 每次升级要复验 | 基本不用 |
| 先做哪个 | **先实验，成功再实现** | 兜底，随时可用 |

### 最小事件序列（从真实会话 + 仓库测试夹具反推）

2026-11-18 实测一个真实小会话，事件顺序是：

```jsonc
{"type":"session","version":4,"id":"session-…","createdAt":1794903323467,
 "cwd":"/data/data/com.termux/files/home/mingyue","isSeeded":false,"delegationDepth":0,"agentPreset":"standard"}
{"type":"permission/preset","seq":0,"time":…,"data":{"preset":"danger-full-access"}}
{"type":"sandbox/mode","seq":1,"time":…,"data":{"mode":"danger-full-access"}}
{"type":"approval/policy","seq":2,"time":…,"data":{"policy":"never"}}
{"type":"session/title","seq":3,"time":…,"data":{"title":"…","source":{"kind":"user"}}}
{"type":"model/selection","seq":4,"time":…,"data":{"provider":"deepseek-account","model":"deepseek-flash","reasoningEffort":"high"}}
// 每个来回：
{"type":"turn/start","seq":5,"time":…,"data":{"turn":1}}
{"type":"step/start","seq":6,"time":…,"data":{"turn":1,"step":1}}
{"type":"user/message","seq":7,"time":…,"data":{"content":[{"type":"text","text":"…"}],
  "source":{"kind":"user","rpcId":"…"},"role":"user","id":"<uuid>"},"surfaceOp":"append"}
{"type":"assistant/message","seq":8,"time":…,"data":{"turn":1,"step":1,
  "message":{"role":"assistant","content":[{"type":"text","text":"…"}]}},"surfaceOp":"append"}
{"type":"step/end","seq":9,"time":…,"data":{"turn":1,"step":1}}
{"type":"turn/end","seq":10,"time":…,"data":{"turn":1,"reason":{"kind":"completed"}}}
```

要点：

- `seq` 从 0 连续递增；`time` 是毫秒时间戳
- 头部 `isSeeded:false`（`isSeeded:true` 表示 fork/子代理的会话，不能用）
- **不需要**伪造 `system/message`（系统提示由下一次真实 turn 自己生成）
- 参照实现：`app/test/chat/fixtures/*.py` 里有合成会话头的现成写法；
  `packages/dsh_client/test/fixtures/follow_*.jsonl` 有完整事件流样本
- 写完用 `zstd` 压成**单帧**即可（引擎读多帧/单帧都行）

其余事件（`agent/inbox/spliced`、`tool/call`、`request/header`、投递回执）**不属于最小集**，
先不造；缺了它们最多是某些统计字段为空，不影响打开和继续聊——**这正是实验要验证的**。

---

## 3. 规模与成本（按实测数据估算）

素材：1013 会话 / 34,207 消息 / 正文约 60.5 MB（≈ 2000 万 token）。

| 规模 | 做法 | 成本 |
|---|---|---|
| 先跑最近 12 个月 | 按 `updated_at` 过滤，先做近半年的会话 | 小，先验证流水线 |
| < 200 个会话 | 逐会话蒸馏 | 几分钱 |
| 200–1000 个会话 | 每批 50，断点续跑 | 几块钱 |
| 全量 1013 个 | **分三批**：近 12 个月 → 再往前 → 剩下只留一句话摘要 | 可控，分批跑 |

**断点续跑**是必须的：用 `import_state.json` 记 `{session_id: done|failed}`。

**别把 60 MB 一次性喂模型**：每个会话先截断（只保留首尾 + 高信息量段落，比如每会话 ≤ 4000 字）。
`THINK` 和 `TOOL_*` 已经是最大头（21,910 + 17,451 条），先扔掉能省掉一半以上体积。

---

## 4. 幂等与重跑

- 每段对话的 hash 存在 `import_state.json`，重跑跳过已完成的。
- 新增的对话（导出后你又聊了新的）下次导入只处理增量。
- 想推翻重来：`--reset` 只删 `source_type='import'` 的条目，不动日常积累的记忆。

---

## 5. 隐私

- **导出文件不上传**：整个流水线在旧手机（或 PC）本地跑。
- 脱敏在**蒸馏之前**做，不是之后——避免密钥进模型上下文。
- 导入产生的 `episodes` 里只存摘要，**不存原始对话全文**；原文留在 `archive/` 里，你自己保管。
- `archive/` 不进备份包（太大且敏感），只备份 `memory.db` + `me.md`。

---

## 6. 人工确认（这一步不能省）

导入跑完后，只给你看两样东西：

1. **`me.md`**（她对你形成的初始画像，20–40 行）
2. **top 20 条 `facts`**（按 `evidence_count` 排序）

你只需要做两件事：

- 删掉不对的（"他没说过这个"）
- 圈出要进 core 的（3–5 条）

**在这之前，导入的事实不进 `core`、不进 `AGENTS.md`。** 否则她第一天就会用一堆二手概括跟你说话，很别扭。

---

## 7. 验收

1. 导入后 `mem.py search "某个只有旧对话里才有的事"` 能命中。
2. 她第一次对话时**不会**主动背诵你的历史（说明没进 core）。
3. 同一个事实在多条对话里出现时，`evidence_count > 1`。
4. 重跑导入不产生重复条目。
5. 随便挑 3 条 `episodes`，能在导出文件里找到对应原文。
6. 脱敏生效：`grep` 一遍 `memory.db`，没有任何 Key/手机号残留。

---

## 8. 和 MEMORY 的接口

> ⚠️ **开工前必须先对齐**（2026-11-18 对照真实 schema v2）：
> 现在**没有 `arcs` 表**、**没有 `facts.source_type` 列**，`episodes.kind` 只允许
> `chat / reading / event`。下表的 `kind='import'`、`source_type='imported'` 都不存在。
> 要么加 schema v3（附迁移脚本 + 回滚），要么降级成现有列能表达的形式——
> 这个决定必须在写解析器之前定，否则导入完发现落不下去。

| 导入产物 | 落到哪 | 之后怎么用 |
|---|---|---|
| 每条对话的摘要 | `episodes`（`kind='import'`） | 周反思时会被重新读一遍，可能提升出新事实 |
| 跨对话的稳定事实 | `facts`（`source_type='imported'`） | 和日常记忆同权，但 `confidence` 起始 0.5 |
| 主题簇 | `arcs`（`status='closed'`） | 她说"你考研那阵子"就有依据了 |
| 初始画像 | `me.md` → 你确认 → `core.user` | 她一开始就认识你 |

导入完成后跑一次 `mem.py report --all`，你会看到"共 1432 条情景、87 条事实、9 条主题线"——这就是她的家底。

---

## 9. 一句话

**不要试图把旧对话变成会话，把它变成记忆。**
几年的聊天是"证据丰富"的数据，用 `evidence_count` 门控，反复出现的才沉淀——这比一次性全塞进去更像人。
