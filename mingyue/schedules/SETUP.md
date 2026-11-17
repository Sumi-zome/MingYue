# 定时任务重建（迁移后必做）

定时任务存在引擎里，不在文件里。恢复备份/换机后，把下面整段贴给**新主机**上的 agent，它会按内容建三条任务。

## 时间约定（为什么是凌晨）

| 任务 | 时间（Asia/Shanghai） | 处理哪一天 |
|---|---|---|
| 抽取 | 每天 **04:00** | 刚过去的**昨天**（`--day yesterday`） |
| 沉淀 | 每天 **04:10** | 昨天（`--day yesterday`） |
| 周反思 | **每周一 04:20** | 过去 7 天 |

凌晨跑时不抢晚上的聊天，但**"今天"已经是新的一天**——所以抽取/沉淀都处理"昨天"。
白天手动跑也一样用 `--day yesterday`（就是昨天）；要抽今天就把参数加成 `--day today` 临时改。

## 前置检查（30 秒）

1. 主机上 `command -v zstd` 有输出（`ingest` 要用）；`python3 ~/mingyue/scripts/selftest.py` 全绿。
2. **新会话默认权限 = `danger-full-access`**：Android 上没有可用沙箱，`workspace-write` 会让 bash 工具失败；
   定时任务无人值守，失败时没人点确认。在引擎 Web UI → 设置 → 通用 → 新建会话的默认权限，选 `danger-full-access`。
   （验证：新开一个对话让它执行 `date`，能返回时间即成功。）
3. **凌晨引擎必须在跑**：手机重启后引擎不会自启（PLAN §4.10 方案 A），要开一次 App 连上；华为清后台也会让任务错过。
   接受这个限制再挂任务；错过了不影响数据，第二天手动补跑即可（用 `--day` 指定补哪一天）。
4. 三条任务都投递到**新会话**（`target.kind = new`），互不打扰；`ingest` 会跳过"当天没有真人消息"的会话，
   所以任务自己的会话不会反过来被抽取（双保险）。

> `agentPreset: "mingyue-memory"` 的第二道锁：需要主机上已注册这个 preset（复制 standard 建一个即可）。
> 没注册就**不要**给任务加 `agentPreset`，否则新会话创建会失败；两道锁（`source.kind` 过滤 + 空会话跳过）已经实测有效。

## 贴给主机 agent 的一段

```
这台主机上有一个自用项目「溟月」，目录在 ~/mingyue。请用 schedule_create 建五条定时任务，
一条一条建：每建完一条先用 schedule_list 确认时间/时区/target，再建下一条。全部建完把五条的 id/下次时间贴给我。

统一要求：
- 时区 Asia/Shanghai；target 一律是 {"kind":"new","create":{"cwd":"/data/data/com.termux/files/home/mingyue"}}。
- 都是"新会话"任务，不会和你现在的对话混在一起；不需要你回复用户，按 prompt 执行即可。
- 如果主机上已经注册了 agent preset "mingyue-memory"，在 create 里加上 "agentPreset":"mingyue-memory"；
  没有就别加（不要为了这个去改配置）。

1) title: 溟月·每日抽取
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T040000
          RRULE:FREQ=DAILY
   prompt: 读 ~/mingyue/schedules/night-extract.md，严格按里面的步骤执行。

2) title: 溟月·每日沉淀
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T041000
          RRULE:FREQ=DAILY
   prompt: 读 ~/mingyue/schedules/night-consolidate.md，严格按里面的步骤执行。

3) title: 溟月·周反思
   rrule: DTSTART;TZID=Asia/Shanghai:20261123T042000
          RRULE:FREQ=WEEKLY;BYDAY=MO
   prompt: 读 ~/mingyue/schedules/weekly-review.md，严格按里面的步骤执行。

4) title: 溟月·安排早安
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T000500
          RRULE:FREQ=DAILY
   prompt: 运行 bash ~/mingyue/scripts/morning-schedule.sh，只做这一件事，不要额外说话。

5) title: 溟月·安排分享
   rrule: DTSTART;TZID=Asia/Shanghai:20261118T001000
          RRULE:FREQ=DAILY
   prompt: 运行 bash ~/mingyue/scripts/share-schedule.sh，只做这一件事，不要额外说话。
```

> rrule 是两行（DTSTART + RRULE）。`DTSTART` 只要是一个已经存在的本地时刻即可，引擎从"创建后的下一次"开始投递；
> 每次投递都新建会话（target new）。周反思放 04:20 是为了避开 04:00 的每日抽取。
>
> **第 4、5 条是"规划任务"**：它们只跑 shell 脚本，脚本再建一条**一次性任务投递到你的聊天会话**（target 是 `session`）。
> 建完别忘了在这台主机上跑 `bash ~/mingyue/scripts/morning-schedule.sh --set-target <会话id>`，
> 把目标设成你正在聊的会话（详见 [docs/mingyue/PROACTIVE.md](../../docs/mingyue/PROACTIVE.md)）。

## 没有"立即运行"按钮时：手动跑一遍（也是验收用）

1. 新开对话，发：`读 ~/mingyue/schedules/night-extract.md，严格按里面的步骤执行`
   - 如果 bash 工具报沙箱不可用：先发 `/permission danger-full-access` 再重试，并把新会话默认权限改掉（见前置 2）。
2. 检查候选文件：`ls -l ~/mingyue/tmp/mingyue-extract.jsonl`（不要贴正文）。
3. 新开对话，发：`读 ~/mingyue/schedules/night-consolidate.md，严格按里面的步骤执行`
4. 新开对话问："昨晚我们聊了什么？"——她应该先 `mem.py search`，再说出具体关键词；说不出就说记不清。

## 建完之后核对

- [ ] 三条夜间任务时间/时区正确（04:00、04:10、周一 04:20，Asia/Shanghai）
- [ ] 两条规划任务时间正确（00:05、00:10，Asia/Shanghai）
- [ ] 五条 target 都是 `kind = new`（每次新会话）
- [ ] 手动跑一次，日志没有报错；失败时不会静默跳过（能在会话/日志里看到原因）
- [ ] "立即运行"如果可用，每条各点一次，看会话里的输出
- [ ] 早安/分享的目标会话已设置：`bash ~/mingyue/scripts/morning-schedule.sh --status`
      （`share-schedule.sh --status` 同理），并跑一次 `--dry-run` 看窗口和请求体

## 迁移/重装后

任务不在备份包里，恢复后按本文件重贴一次即可。任务 id 会变，不需要记。
`~/mingyue/morning.json` / `share.json` 也不在备份包里，重建后跑一次 `--set-target` 再补其余字段。

## 本机部署记录（2026-11-17，旧手机）

- 已挂三条：**溟月·每日抽取 04:00 / 溟月·每日沉淀 04:10 / 溟月·周反思 周一 04:20**（Asia/Shanghai，`target.kind=new`，cwd=`/data/data/com.termux/files/home/mingyue`，standard preset）。
- 到点投递已验证：建了一条 16:39:00 的一次性测试任务，16:39:02 自动新建会话并回复时间；验证后已删除。任务 id 是引擎状态，不写死在这里。
- **无人值守权限已验证**：测试任务会话里真的执行了 bash `date`（输出 `Tue Nov 17 16:39:02 CST 2026`），说明调度新会话拿到的是 `danger-full-access` 级别、能跑脚本。
- `agentPreset="mingyue-memory"` 第二道锁**未启用**（主机上没有该 preset）；防自喂靠已实测的两道：`source.kind` 过滤 + 当天无真人消息会话跳过。
- 每日 04:00 抽"昨天"（`--day yesterday`）；白天手动补跑也用它。
- **阶段 2c（同日）**：已挂 **溟月·安排早安 00:05 / 溟月·安排分享 00:10**。目标会话 = `session-12508eb5…`；
  到点投递实测 19:58:17（投递 19:58:17.2）、20:07:00（投递 20:07:00.1），都进了用户会话。
  详见 [docs/mingyue/PROACTIVE.md](../../docs/mingyue/PROACTIVE.md) §6。
