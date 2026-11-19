# 三个工作区：溟月 / 聊天（Chat）/ 隐私（Private）

> 2026-11-18 落地。解决两个问题：**不是每次都想跟虎鲸娘聊天**、**有些对话不该进记忆**。

## 事实基础（先确认过）

主机上 88 个会话，会话头里的 `cwd` **全部**是 `/data/data/com.termux/files/home/mingyue`：

```
88  /data/data/com.termux/files/home/mingyue
```

也就是说：**默认工作区就是溟月**。App 里显示「未分组」只是没有选工作区，实际落点是 `~/mingyue`。

所以只需要额外建两个：**聊天（Chat）**（不装人设，也进记忆）和 **隐私（Private）**（不进记忆）。

## 三个边界的实际差别

| 维度 | 溟月（默认） | 聊天 / Chat | 隐私 / Private |
|---|---|---|---|
| 目录 | `~/mingyue` | `~/chat` | `~/private` |
| App 里怎么进 | 现有主机条目 | 新建主机条目「Chat」 | 新建主机条目「Private」 |
| `AGENTS.md` | 人设 + CORE 块 | 简洁助手口吻 | 简洁助手口吻 |
| 人设 | 虎鲸娘 | 无 | 无 |
| **进记忆抽取** | ✅ | ✅ | ❌ |
| **能读到 CORE（记忆注入）** | ✅ | ❌ | ❌ |
| 早安/分享定时消息投递到这 | ✅ | ❌ | ❌ |
| 会话落盘 | 是 | 是 | 是（可手动删） |
| 走 DeepSeek API | 是 | 是 | 是 |
| 典型用途 | 平常聊天、她主动找你 | 问技术、写代码、查资料 | 不想留痕的话 |

一句话概括：

- **溟月** = 有人设、有记忆、会被喂记忆
- **Chat** = 没有人设，但**你在这里说的话会进她的记忆**（她知道你在忙什么，但不参与）
- **Private** = 没有人设、**永不进记忆**

### 记忆是单向的

```
Chat 对话 ──→ 记忆库 ──→ 第二天 CORE ──→ 只在溟月工作区注入
Private 对话 ──✕ 不进记忆
```

Chat 里聊的事，溟月第二天会记得；但 Chat 自己**读不到** CORE，也不会用人设说话。

## 为什么 Chat 要进记忆

你在 Chat 里修 bug、查资料，这些是"你最近在做什么"。溟月第二天能问一句"昨天那个 attach 补丁搞定了吗"，
前提就是这些对话进了记忆。

## 记忆权重：日常聊天降一档（2026-11-18 定）

> 口径见 [MEMORY-WEIGHT-PLAN.md](MEMORY-WEIGHT-PLAN.md)；2026-11-18 阶段 2f 已实现，
> 实际行为见下面「实现」小节。

日常聊天里抽出来的记忆，不该和"对方认真说的事"一个分量。

| 来源 | 默认 importance | 说明 |
|---|---|---|
| 溟月里的日常闲聊（没有明确强调） | 0.3–0.4 | 比如"今天聊到某个 bug" |
| Chat / 聊天（没有明确强调） | 0.2–0.3 | 干活上下文，只用来"知道你在忙什么" |
| 任意来源，对方明确说"记住 / 重要 / 别忘" | 0.6–0.9 | 事实本身重要，不因来源降权 |

- 同一件事两处都出现：取高值（`consolidate` 现在就是 `max(importance)`）。
- 目的：0.3 左右的条目进不了 CORE「最近」（取 importance 前 8），`decay` 时也会更早归档；她不会拿闲聊里的事反复当谈资。
- 例外：涉及安全、承诺、时间点（答辩、面试、约定）的，不管在哪个工作区都按 0.6+ 记——权重降的是「闲聊」，不是「事实」。

### 实现（2026-11-18，阶段 2f）

三层都落到了代码里，不再靠提示词自觉：

1. **ingest 标来源**：会话头输出 `[会话 <id> @mingyue]` / `[会话 <id> @chat]`（其它工作区用目录名；会话头缺 `cwd` 时保持 `[会话 <id>]`）。
2. **抽取给 emphasis**：`schedules/night-extract.md` 要求每条候选带 `emphasis`；默认低，明确强调才 `true` + 0.6–0.9。
3. **consolidate 硬 clamp**（默认开）：按来源会话反查 `cwd` 得到工作区，未强调的 importance 压到上限，强调的封顶 0.9。

| 来源 | 未强调上限 | 强调上限 |
|---|---|---|
| `@mingyue` | 0.40 | 0.90 |
| `@chat` | 0.35 | 0.90 |
| 未知 / 其它工作区 | 0.40 | 0.90 |

- 压下来打 `[CLAMP]` 到 stdout；来源会话找不到 / 读不了 → `[WARN]` 并按未知来源，**不中断**整理。
- 旧候选没有 `emphasis` 字段 → 按未强调压；手动写高权重时 `consolidate` 加 `--no-clamp-daily`。
- 能解析到 `private` 来源的候选一律拒绝写入（和开关无关）；来源解析不到时按未知来源处理 `0.4`——真正的隐私边界是 `ingest` 的 `exclude`（见下面「配置：抽取范围」）。
- 只 clamp 当批新候选；合并已有条目仍是 `max()`，已写进去的高权重不会被降。
- `add-episode` / `import-profile` 不走 consolidate，不受影响（import-profile 仍 0.9）。
- 测试在 `selftest.py` 的 `test_32`–`test_34`；设计、回滚与实现记录见 [MEMORY-WEIGHT-PLAN.md](MEMORY-WEIGHT-PLAN.md)。
- 观测：第二天 `core-refresh` 后 CORE「最近」里闲聊类条目应减少；`decay` 会先把 0.3–0.4 的旧闲聊归档。

## 配置：抽取范围

`~/mingyue/memory-scopes.json`：

```json
{
  "include": ["~/mingyue", "~/chat"],
  "exclude": ["~/private"]
}
```

- `include` 是**白名单**：不在里面的工作区一律跳过
- `exclude` 在 include 之后再排除一层
- 缺文件 → 只抽 `~/mingyue`（旧行为）
- 配置里的目录不存在 → 告警并跳过；全都不存在 → 退出码 4
- 改完不用重启引擎，下次 04:00 抽取就按新范围走
- 代码：`mem.py` 的 `load_memory_scopes()`；实现口径见 [MEMORY.md](MEMORY.md) §3.1.1

## 在 App 里怎么建（两步，各 1 分钟）

现有主机条目保持不动（它就是溟月，工作目录 `~/mingyue`）。

1. **添加主机 → 「Chat」**
   - SSH 参数照抄现有那台（同一台手机、同一 Tailscale IP、端口 8022、同一用户、同一把密钥）
   - **工作目录**填 `~/chat`
2. **添加主机 → 「Private」**
   - 同上，**工作目录**填 `~/private`

> **不会起第二个引擎**：引导脚本会检测 `web.pid`，进程还活着就复用
> （`remote_bootstrap.dart` 第 98–110 行）。多个主机条目共享同一个 `dsh web`。

之后：想用哪个模式，就选哪个主机条目开新会话。

## 隐私模式的"彻底清理"

不进记忆 ≠ 不落盘。原始会话还在 `~/.dsh/sessions/--…-home-private--/`：

```bash
ls -1 ~/.dsh/sessions/                                   # 每个工作区一个编码目录
rm -rf ~/.dsh/sessions/*--home-private--*                # 删 Private 的全部会话（先确认路径）
```

也可以在网页版里逐个删会话。

**注意**：Private 只隔离"本地记忆和本地人设"。模型调用仍然经过 DeepSeek API，这一点无法绕过。

## 验证

```bash
# 1. 三个目录都在
ls -d ~/mingyue ~/chat ~/private

# 2. 抽取范围正确
cat ~/mingyue/memory-scopes.json

# 3. 手动跑一次抽取（看汇总行）
python3 ~/mingyue/scripts/mem.py ingest --day today 2>&1 >/dev/null | tail -1
```

在 Chat/Private 里各聊一句之后，"工作区 N" 的跳过数应该：Chat **不增加**、Private **增加**。

## 不要做

- 不要把 `~/chat` / `~/private` 的 `AGENTS.md` 删掉——没有它只是不注入人设，
  但明确写一句"不扮演人设"能避免模型自己脑补
- **不要把 `~/private` 加进 `include`**——那是这个设计唯一的防线
- 不要为了"临时"进记忆把 `ingest` 改成扫全部工作区：容易带进隐私目录
- 不要在 Private 工作区里让她跑 `mem.py` 的写子命令
