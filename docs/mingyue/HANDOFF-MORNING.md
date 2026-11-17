# 交接：她随机主动找你（2c 第一刀）

> 交给新窗口：读这个文件，按「要做的事」执行。不要重做「已就绪」。

## 目标

**每个早上，她在 08:00–10:30 之间随机挑一个时刻主动说一句话**，而不是固定闹钟。

可加可选行为：**15% 概率那天不说**（更像活人）。第一版可以先不做，验证链路通畅后再加。

## 已就绪（别重做）

- 主机：旧手机 Termux，ssh 别名 `mingyue`，PC 已配免密
- 引擎：`dsh web` 由 App 托管；端口/token 每次重启变
- 她的家：`~/mingyue`（persona/rules/me/memory.db/journal.jsonl/AGENTS.md）
- 现有三条定时任务（`~/.dsh/storages/schedule.json`，均 `target.kind=new`）：04:00 抽取 / 04:10 沉淀 / 周一 04:20 反思
- `mingyue/schedules/morning-hello.md` 已写好（说话规范），需 scp 到主机
- 排障：`docs/mingyue/TROUBLESHOOTING.md`（**Termux 补丁见 §7，别动**）
- RPC 调用范例：`mingyue/scripts/probe-upload.sh`（token → cookie → POST /api/<method>）

## 架构（随机时间的做法）

```
每天 00:05  定时任务（target=new，隐藏）
            prompt: 运行 bash ~/mingyue/scripts/morning-schedule.sh
            └─ 脚本：随机挑今天 08:00–10:30 的一刻
                     → RPC schedule/create
                       kind: "at"（一次性）
                       target: {kind:"session", sessionId: <用户会话>}
                       prompt: 读 ~/mingyue/schedules/morning-hello.md，严格按里面的步骤执行。
              
随机时刻      一次性任务投递到用户会话 → 她按 morning-hello.md 说话
```

不需要 cron / 后台守护进程：定时任务由引擎负责，脚本只在 00:05 跑一次。

## 要做的事

1. **scp 两个文件到主机**：
   ```powershell
   scp mingyue/schedules/morning-hello.md mingyue/scripts/morning-schedule.sh mingyue:mingyue/
   ```
   （morning-schedule.sh 需要新写，见下面「实现要点」）

2. **确认 RPC 形状**（之前没有完全读完，必须自己核实）：
   - 引擎包：`~/../usr/lib/node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-schedule/lib/index.js`
   - 创建方法：`async create(request, actorSessionId, signal)`，`request = {title, prompt, timing, target}`
   - `target` 已知：`{kind:"session", sessionId}` ✓
   - **`timing` 的结构还没确认**：找 `createScheduleRecord` / `decodeScheduleRecord` 的定义（可能在本文件或 `dsh-schedule-core`），确认 `kind:"at"` 需要哪些字段（`at`? `scheduledAt`? `afterSeconds`?）
   - RPC 入口名：App 端用过 `schedule/catalog`、`schedule/update`、`schedule/edit`、`schedule/delete`，**创建大概率是 `schedule/create`**；用 `probe-upload.sh` 的 curl 流程直接试，拿 `ok:false` 的 `gateway/arguments-invalid` 反推字段名（这是最快的方法）

3. **确定目标会话 id**（用户正在聊的那个）：
   - App 里能看到会话 id，或从 `~/.dsh/sessions/*/` 目录名推断
   - 建议写成配置：`~/mingyue/morning.json`：`{"targetSessionId": "session-…", "windowStart":"08:00","windowEnd":"10:30","skipChance":0}`
   - 脚本提供一个 `--set-target <sessionId>` 子命令，避免手改 JSON

4. **写 `mingyue/scripts/morning-schedule.sh`**，要点：
   - 读 `~/mingyue/morning.json`
   - 用 `$RANDOM` 在窗口内取一个随机秒数，算出 `afterSeconds`
   - 从 `~/.dsh-app-remote/web.log` 取端口与 token（**不要打印 token**）
   - `curl -c jar "http://127.0.0.1:$PORT/?token=$TOKEN"` 换 cookie
   - `curl -b jar -H 'Content-Type: application/json' -X POST "http://127.0.0.1:$PORT/api/schedule/create" --data '{...}'`
   - 打印结果（成功打印任务 id + 计划时刻；失败打印原始响应体）
   - 幂等：如果今天已经建过（状态文件记录日期），直接退出

5. **注册 00:05 的隐藏任务**：
   - title：`溟月·安排早安`
   - prompt：`运行 bash ~/mingyue/scripts/morning-schedule.sh，只做这一件事，不要额外说话。`
   - rrule：`DTSTART;TZID=Asia/Shanghai:20261119T000500` + `RRULE:FREQ=DAILY`
   - target：`new`，cwd `~/mingyue`，preset `standard`
   - 注意：任务会话需要能跑 bash（已有 nightly 任务能跑 python，应该没问题；若沙箱拒绝，按 `schedules/SETUP.md` 前置 2 处理）

6. **立刻验证**（不要等到明早）：
   - 手动跑一次脚本：`bash ~/mingyue/scripts/morning-schedule.sh --dry-run` 看摇出的时间和请求体
   - 真跑一次，把窗口临时改成"5 分钟后"（或给脚本加 `--in N` 参数），确认用户会话里出现她的话
   - 验证后恢复窗口

7. **记录**：在 `docs/mingyue/TROUBLESHOOTING.md` 或 PLAN 进度里加一条；把脚本、配置格式、验证方式写清。

## 关键约束

- 每天**最多一条**
- 随机窗口固定 `08:00–10:30`（可配置）
- 消息短：一到三句（`morning-hello.md` 已写）
- 失败必须可见：脚本失败要打印原始响应，不要静默
- 不要 `git add .`
- 不要动 Termux 补丁、不要升级 DSH

## 已知风险

1. **引擎不自启**：夜里重启/退出，00:05 的规划任务不会跑 → 当天没有早安。先确认 `dsh web` 在跑。
2. **00:05 任务失败无人知**：脚本要写日志到 `~/mingyue/tmp/morning.log`，便于事后查。
3. **RPC 形状不确定**：先用 curl 试探（见第 2 步），不要凭猜写代码。
4. **会话归档**：target 会话 archived 会报 `schedule/target-archived`。

## 验收

某天早上 08:00–10:30 之间，她主动说话，且**时间不是固定的**（连着两三天时间不同）。
