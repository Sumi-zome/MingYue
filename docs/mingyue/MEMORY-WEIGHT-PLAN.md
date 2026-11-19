# 记忆权重实现方案（日常聊天降权）

> 状态：**已实现**（2026-11-18，阶段 2f）。§0–§6 是定稿设计；实现记录见下面「实现记录」。
> 需求来源：2026-11-18「有可能会从我日常聊天提取记忆，我希望这部分记忆权重小一点」。
> 口径文档：[WORKSPACES.md](WORKSPACES.md) §记忆权重。

## 实现记录（2026-11-18，阶段 2f）

- **实际改动行数**（`git diff --numstat`；不含另一任务并发修改的 `docs/mingyue/IMPORT.md`）：
  - `mingyue/scripts/mem.py` **+136 / −11**：ingest 标 `@来源`、`session_workspace()`、`DAILY_CAPS` / `EMPHASIS_MAX`、`clamp_daily()`、`--no-clamp-daily`、三个 `plan_*` 接来源、`add-episode` 显式 `clamp=False`。
  - `mingyue/scripts/selftest.py` **+147 / −7**：test_14 / test_19 / test_20b 改期望；test_24–27 显式 `--no-clamp-daily` 保住原数字；新增 test_32–34（§5 全部用例）。
  - `mingyue/schedules/night-extract.md` **+21 / −5**：权重规则 + `emphasis` 字段 + 示例。
  - `docs/mingyue/WORKSPACES.md` **+22 / −4**：新增「记忆权重：实现」小节。
  - `docs/mingyue/MEMORY.md` **+4 / −4**：§3.1.1 一句、§3.1 输出行、§7.2 两条命令。
- **测试结果**：
  - 手机 Termux（Python 3.14.10）：`python3 ~/mingyue/scripts/selftest.py` → **38 tests，OK，退出码 0**（zstd 端到端用例真跑）。
  - PC Windows（Python 3.13.7，本机无 zstd）：`py -3 mingyue/scripts/selftest.py` → **38 tests，OK，4 skipped（zstd 用例），退出码 0**。
  - 真机验证（不碰真库）：`ingest --day yesterday` → 9 个会话头全 `@mingyue`；`--day today` → 22 个 `@mingyue` + 1 个 `@chat`。临时 home + 两个真实会话 id 跑 `consolidate`：chat 0.80→**0.35**、mingyue 0.60→**0.40**、强调 0.95→**0.90**、未知来源 0.90→**0.40** + `[WARN]`、fact 经本批 episode 0.80→**0.35**；`add-episode` 0.90 原样；`--no-clamp-daily` 0.80 原样；`mem.py check` 真实库全绿（RC=0）。临时库已删。
- **与设计的有意偏差**：
  1. `session_workspace()` 复用 `read_session_lines()` 读整个会话文件取头（每天 ≤10 次，够用），没单独实现「只解压第一行」。
  2. `--no-clamp-daily` 只关权重 clamp；`private` 来源拒绝**不受开关影响**（隐私边界优先于调参）。`plan_intention` 也调 `clamp_daily(..., enabled=False)`：intentions 表没有 importance 列，调用只做 private 拒绝与数值校验（否则会打出无意义的 `[CLAMP]`）。
  3. 没有实现可选的 `--clamp-daily`：默认就是开，只提供 `--no-clamp-daily`。
- **独立评审**（2026-11-18，只读）：无高/中严重度问题。4 条低严重度：① intention 的 `importance` 现在也会被校验（intentions 表没有这列；正常抽取给合法数字，记为已知限制）；② 整批被拒时 `[CLAMP]` 已先打到 stdout（诊断信息，库未改）；③ 「private 一律拒绝」措辞过强（已按「能解析到来源时拒绝」修正文档，硬边界仍是 `ingest` 的 `exclude`）；④ 方案里的 `--clamp-daily` 已删（只留 `--no-clamp-daily`）。
- **部署**：手机备份 `~/mingyue/lab/mem.py.bak-20261118` 与 `night-extract.md.bak-20261118`；三个运行文件已 scp 到 `~/mingyue`（sha256 与仓库一致）。未 commit / 未 push。

## 0. 一句话

三层：**ingest 标来源**（确定性）→ **抽取给 emphasis**（模型判断）→ **consolidate 硬 clamp**（确定性兜底）。
不改 schema，不动人设。

## 0.1 已定参数（2026-11-18，用户确认）

| 项 | 定值 |
|---|---|
| 非强调条目上限 | **聊天 0.35 / 溟月 0.4** |
| 强调条目上限 | **0.9** |
| clamp 默认 | **开**（手动写入用 `--no-clamp-daily` 关） |
| 降权范围 | **溟月闲聊 + 聊天都降，聊天更低** |

实现时把这四个值写成常量（`DAILY_CAPS`、`EMPHASIS_MAX`、argparse 默认值），以后要调只改常量表，不改逻辑。**本方案已定稿，可直接交给实现窗口。**

## 1. 现状（代码位置，2026-11-18）

| 位置 | 行为 |
|---|---|
| `mem.py` `cmd_ingest`（L1231）/ `extract_session`（L1018） | 按 `memory-scopes.json` 过滤工作区，输出 `[会话 <id>]`，**不带来源工作区** |
| `mem.py` `format_session`（L1059） | 拼 `[会话 id]` + 消息行 |
| `schedules/night-extract.md` | 让模型自己给 importance 0.3–0.9，没有来源规则 |
| `mem.py` `plan_episode`（L632）/ `plan_fact`（L667）/ `plan_intention`（L769） | 解析候选的 importance；L639 / L674 |
| 合并 | 已有条目取 `max(importance)`（L693 / L712 / L749），只会升不会降 |
| `core-refresh`（L1658） | 取 importance 前 8 条 facts（L1666）写 CORE「最近」 |
| `decay`（L1735） | `strength = importance × exp(-days/30)`，`importance>=0.8` 不自动归档 |

**问题**：抽取模型分不清一段对话来自溟月还是聊天工作区，所以「日常闲聊降权」现在只能靠提示词自觉。

## 2. 设计

### 2.1 ingest 标来源（确定性，~15 行）

- `extract_session` 返回的 dict 加 `"workspace": workspace_of(header)`（L934 已有函数）。
- `format_session` 输出改成：
  ```
  [会话 session-xxxx @chat]
  [会话 session-yyyy @mingyue]
  ```
  label 规则：`home/mingyue` → `mingyue`；`home/chat` → `chat`；其它 → 目录 `basename`。
- `include/exclude` 逻辑不动（private 仍然在 ingest 前就被排除）。

### 2.2 抽取给 emphasis（模型判断，改 prompt）

`schedules/night-extract.md` 加一段：

```text
## 权重（2026-11-18 起）

- 会话头里的 @mingyue / @chat 是来源。
- 默认 importance：
  - @mingyue 日常闲聊：0.3–0.4
  - @chat 干活上下文：0.2–0.3
- 只有下面这些才给 0.6–0.9，并写 "emphasis": true：
  - 对方明确说「记住 / 重要 / 别忘」
  - 安全、承诺、时间点（答辩 / 面试 / 约定）
  - reason 必须引用能支撑的原话
- 其余一律 "emphasis": false。
- 每条 episode / fact / intention 都必须带 emphasis 字段。
```

示例行同步更新（episode 带 `"emphasis": false`）。

### 2.3 consolidate 硬 clamp（确定性兜底，~40 行）

- 新参数：`--no-clamp-daily`（默认开；没有反向的 `--clamp-daily`，默认开就够）。
- 解析候选前先给每条候选补 `_workspace`：
  - **episode**：`source` 形如 `session:<id>` → 用 `<id>` 查会话头 cwd（见 2.4）。
  - **fact / intention**：按 `source_episode` 找来源：
    1. 本批已规划的 episode（建 `planned_episode_workspace` 映射；抽取顺序本来就是先 episode）
    2. 否则查 DB：`SELECT source FROM episodes WHERE id=?`，再按 session 查 cwd
  - 解析不到 → `_workspace=None`。
- clamp 规则（在 L639 / L674 / L769 解析完 importance 后调用）：

  ```python
  DAILY_CAPS = {"mingyue": 0.4, "chat": 0.35}
  EMPHASIS_MAX = 0.9

  def clamp_daily(cand, workspace):
      value = to_float(cand.get("importance", 0.5), "importance")
      if workspace == "private":
          raise MemError("候选来自 private 工作区，拒绝写入")
      if cand.get("emphasis") is True:
          return min(value, EMPHASIS_MAX)    # 明确强调，不降，但封顶 0.9
      cap = DAILY_CAPS.get(workspace, 0.4)   # 未知来源按日常处理
      return min(value, cap)
  ```

- 打日志（可选但推荐）：`[CLAMP] e-… 0.8 -> 0.35（chat，未强调）`，便于第二天查。
- **只 clamp 新候选**；合并已有条目仍用 `max()`，不会把旧的高权重条目降下来。

### 2.4 session id → workspace（~25 行）

```python
def session_workspace(session_id, cache):
    if session_id in cache: return cache[session_id]
    pattern = os.path.join(str(sessions_root()), "*", session_id, "session.v4.jsonl.zstd")
    paths = glob.glob(pattern)
    if not paths: return cache.setdefault(session_id, None)
    with zstd 解压第一行 → json → header:
        ws = workspace_of(header)
    cache[session_id] = ws
    return ws
```

- 会话根固定 `~/.dsh/sessions`（`sessions_root()` 本身没有 home 参数；`--home` / `$MINGYUE_HOME` 只管记忆库家目录）。
- 失败（找不到 / 解压失败 / 头坏）→ `None` + 打一行 `[WARN]`，**不中断** consolidate。
- 性能：每天候选 ≤10 条，最多读 10 个会话头，可接受。

## 3. 改动清单

| 文件 | 改什么 |
|---|---|
| `mingyue/scripts/mem.py` | `extract_session` 带 workspace；`format_session` 加 `@label`；`session_workspace()`；`--no-clamp-daily`；三个 `plan_*` 调 `clamp_daily()` |
| `mingyue/scripts/selftest.py` | 新增单测 + 集成用例（§5） |
| `mingyue/schedules/night-extract.md` | 权重规则 + `emphasis` 字段 + 示例 |
| `docs/mingyue/WORKSPACES.md` | 新增「记忆权重：实现」一节，写清实际行为（文件里没有旧的状态段可改） |
| `docs/mingyue/MEMORY.md` | §3.1.1 同步一句 |
| `mingyue/schedules/night-consolidate.md` | 默认开，不用改（没有 `--clamp-daily`，只有 `--no-clamp-daily`） |

## 4. 边界与兼容

- **旧候选没有 emphasis**：默认开 → 会被 clamp 到 0.4。手动写高权重候选时加 `--no-clamp-daily`。
- **已有事实**：不降权；`max()` 只升不降。
- **private**：ingest 已排除；这里再拒一次（防御纵深）。
- **同一事实两处出现**：取 max，符合「事实本身重要」。
- **未知来源**：按 0.4 cap + WARN，不中断。
- **decay 副作用**：0.35 的条目约 17 天后 strength < 0.2 被归档——这是想要的「日常闲聊会淡掉」；如果不想这么快，调 `DECAY_TAU_DAYS` 或 cap，不要在 clamp 里加特例。
- **add-episode / import-profile**：不走 consolidate，不受影响（import-profile 仍是 0.9）。
  **注意**：`add-episode` 内部会调 `plan_episode`，实现时必须显式关掉 clamp（传 `clamp=False`），
  否则默认开会把手动写入的 importance 压到 0.4；测试必须覆盖这两条不受影响（§5 用例 5/6）。

## 5. 测试

`selftest.py` 新增：

1. **ingest 标注**：临时 home + 三个工作区的合成 session 文件（mingyue / chat / private）；跑 `ingest --day`，断言输出含 `@mingyue`、`@chat`，private 会话不出现。
2. **clamp 单测**：
   | workspace | emphasis | 输入 | 输出 |
   |---|---|---|---|
   | chat | false | 0.8 | 0.35 |
   | mingyue | false | 0.6 | 0.4 |
   | mingyue | true | 0.8 | 0.8 |
   | chat | true | 0.95 | 0.9 |
   | None | false | 0.9 | 0.4 |
   | private | any | 0.5 | 报错 |
3. **consolidate 集成**：临时 DB + 合成候选；断言 episode/fact 实际写入的 importance；private 候选被拒；未知来源 0.4。
4. **合并**：已有 fact 0.7 + 新 chat 候选 0.3 → 仍 0.7。
5. **add-episode 不受影响**：`add-episode --importance 0.9` → 库里的 importance 必须是 0.9（不被 clamp）。
6. **import-profile 不受影响**：导入的 facts 仍是 0.9（现有 `test_28` 已断言）；另测旧候选（没有
   `emphasis` 字段）在默认开下被压到上限、`--no-clamp-daily` 时原样保留。

回归：

```bash
python3 mingyue/scripts/selftest.py        # 退出码 0
python3 ~/mingyue/scripts/mem.py check
```

真机验证（不碰真库）：

```bash
# 看 @ 标注
python3 ~/mingyue/scripts/mem.py ingest --day today | head -20

# 临时 home 跑整合
MINGYUE_HOME=$(mktemp -d) python3 ~/mingyue/scripts/mem.py init
# 写入合成候选后 consolidate，查 DB importance
```

## 6. 发布与回滚

- 不需要重启引擎；脚本和 prompt 下次 04:00 定时任务生效。
- 发布前备份：`cp ~/mingyue/scripts/mem.py ~/mingyue/lab/mem.py.bak-<日期>`。
- 回滚：恢复 mem.py + night-extract.md；**没有 schema 变更**，已写入的 importance 不回滚（可接受）。
- 观察点：第二天 `core-refresh` 后 CORE「最近」里闲聊类条目应减少；`decay` 日志里 chat 来源条目会更早出现。

（参数表已在 §0.1 定稿，这里不再重复。）
