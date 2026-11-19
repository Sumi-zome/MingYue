# 溟月 · 每日抽取（每天 04:00）

> 定时任务用，对应 [SETUP.md](SETUP.md) 第 1 条。每次在新会话里执行；**不要和任何人聊天**。
> 凌晨跑的是"刚过去的昨天"，所以 `--day` 用 `yesterday`（白天手动跑也用它，抽的是昨天）。

## 步骤

1. 运行下面命令，拿到**昨天**的会话纯文本（Tool 结果可能很长，直接读，**不要贴出来**）：

   ```
   python3 ~/mingyue/scripts/mem.py ingest --day yesterday
   ```

2. 从这段文本里提炼候选记忆，用 write 工具写到 `~/mingyue/tmp/mingyue-extract.jsonl`（覆盖旧文件，
   先确保 `~/mingyue/tmp` 存在）。一行一条 JSON；**顺序：先 episode，后引用它的 fact / intention**。

3. 只写对方明确说过、或你亲眼看到的事：

   - 宁可少写，不许推测；不确定的不要写。
   - 上限：episode ≤3 条、fact ≤5 条、intention ≤2 条。
   - importance 按下面「权重」一节给；每条都要 `emphasis`（默认 `false`）。
   - 每条都要 `reason`（依据是什么）；fact / intention 必须有 `source_episode`。
   - `source` 用会话文本里 `[会话 <id> @<来源>]` 的 id：`"source": "session:<id>"`（不要带 `@` 后缀）。
   - **episode id 必须唯一**：用 `e-YYYYMMDD-HHMM-01` 格式，HHMM 取你这次运行的时间
     （例如 04:12 → `e-20261116-0412-01`）。**不要照抄示例里的固定 id**；
     同一天重跑时把 `-01` 改成 `-02`、`-03`。

4. 如果 ingest 报错（找不到 zstd / 不认识的会话版本 / 找不到会话目录），**什么都不要写**，
   直接报告错误原文；不要自己回忆昨天聊了什么。

5. 写完只回复一行：`已写入 N 条候选`。不要把会话原文贴出来。

## 权重（2026-11-18 起）

会话头 `[会话 <id> @<来源>]` 里的 `@mingyue` / `@chat` 是这段对话的来源（别的工作区名按来源未知处理）。

- 默认 importance：
  - `@mingyue` 日常闲聊：0.3–0.4
  - `@chat` 干活上下文：0.2–0.3
- 只有下面这些才给 0.6–0.9，并写 `"emphasis": true`：
  - 对方明确说「记住 / 重要 / 别忘」
  - 安全、承诺、时间点（答辩 / 面试 / 约定）
  - `reason` 必须引用能支撑的原话
- 其余一律 `"emphasis": false`。**每条 episode / fact / intention 都必须带 `emphasis` 字段。**
- 别想着写高：`consolidate` 会按来源硬压（未强调：mingyue ≤0.4、chat ≤0.35、未知 ≤0.4；
  强调 ≤0.9），压下来会打 `[CLAMP]` 日志。
- `source` 保持 `session:<id>` 形式，脚本靠它反查会话头判断来源；写成别的就按未知来源压到 0.4。

## 格式（严格 JSON Lines）

```
{"type":"episode","id":"e-20261116-0412-01","at":"2026-11-16T21:00:00+08:00","kind":"chat","text":"对方随口聊到宿舍晚上断电","source":"session:<会话id>","importance":0.3,"emphasis":false,"reason":"对方随口提到"}
{"type":"fact","text":"对方周五要答辩","source_episode":"e-20261116-0412-01","when":"2026-11-16","importance":0.8,"emphasis":true,"reason":"对方说「记住，周五答辩」"}
{"type":"intention","text":"周五答辩前一天提醒他","source_episode":"e-20261116-0412-01","due":"2026-11-20","emphasis":false,"reason":"他说还没改完论文"}
```
