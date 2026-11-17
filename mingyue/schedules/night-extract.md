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
   - importance 给 0.3–0.9（<0.3 的会被衰减掉，别写）。
   - 每条都要 `reason`（依据是什么）；fact / intention 必须有 `source_episode`。
   - `source` 用会话文本里 `[会话 <id>]` 的 id：`"source": "session:<id>"`。
   - **episode id 必须唯一**：用 `e-YYYYMMDD-HHMM-01` 格式，HHMM 取你这次运行的时间
     （例如 04:12 → `e-20261116-0412-01`）。**不要照抄示例里的固定 id**；
     同一天重跑时把 `-01` 改成 `-02`、`-03`。

4. 如果 ingest 报错（找不到 zstd / 不认识的会话版本 / 找不到会话目录），**什么都不要写**，
   直接报告错误原文；不要自己回忆昨天聊了什么。

5. 写完只回复一行：`已写入 N 条候选`。不要把会话原文贴出来。

## 格式（严格 JSON Lines）

```
{"type":"episode","id":"e-20261116-0412-01","at":"2026-11-16T21:00:00+08:00","kind":"chat","text":"一句话说发生了什么","source":"session:<会话id>","importance":0.6,"reason":"对方明确说了"}
{"type":"fact","text":"对方宿舍晚上断电","source_episode":"e-20261116-0412-01","when":"2026-11-16","importance":0.6,"reason":"对方明确说了"}
{"type":"intention","text":"问他毕业设计选了哪个题目","source_episode":"e-20261116-0412-01","due":"2026-11-17","reason":"他说还没定"}
```
