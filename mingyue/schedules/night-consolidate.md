# 溟月 · 每日沉淀（每天 04:10）

> 定时任务用，对应 [SETUP.md](SETUP.md) 第 2 条。每次在新会话里执行；**不要和任何人聊天**。
> 凌晨跑的是"刚过去的昨天"，所以 `--day` 用 `yesterday`。

## 步骤

1. 如果 `~/mingyue/tmp/mingyue-extract.jsonl` 不存在或为空：回复 `昨天没有候选`，结束。

2. 运行：

   ```
   python3 ~/mingyue/scripts/mem.py consolidate --day yesterday --jsonl ~/mingyue/tmp/mingyue-extract.jsonl --reason "日整理"
   ```

   - 退出码非 0（候选不合法 / 缺字段）：把错误原文报告出来，**不要改数据**，不要自己重写候选。
   - 如果报 `episode id 已存在`：说明这个 id 以前用过（补跑/测试遗留）。不要改数据库；
     把候选文件里冲突的 id 改成唯一值（例如 `e-20261116-0412-02`，并把 fact / intention 的
     `source_episode` 一起改），再重跑本步。只改候选文件，不改库。

3. 成功后依次运行：

   ```
   python3 ~/mingyue/scripts/mem.py core-refresh
   python3 ~/mingyue/scripts/mem.py render
   ```

4. 只回复三行：consolidate 的统计 / core-refresh 的统计 / render 是否 OK；有错误就贴错误原文。
   不要贴会话原文，也不要展开记忆条目内容。
