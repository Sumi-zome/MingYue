# 定时任务重建（迁移后必做）

定时任务存在引擎里，不在文件里。恢复备份后，把下面这段贴给**新主机**上的 agent，它会按内容建三条任务。

> 提示词正文放在同目录的 `*.md` 里（阶段 B 会补齐 `night.md` / `weekly.md` / `speak-*.md`）。
> 现在还没有那些文件也没关系：先建目录、先把机制跑通。

```
这台主机上有一个自用项目「溟月」，目录在 ~/mingyue。
请按以下规格用 schedule_create 建三条自动化任务，一次建一条，建完告诉我结果：

1) 每天 23:40 —— 记忆抽取
   提示词：读今天的会话，输出 JSONL（type/text/importance/when），
   只写对方明确说过或你亲眼看到的事，不确定的不要写。
   产出写到 /tmp/mingyue-extract.jsonl。

2) 每天 23:50 —— 沉淀落库
   提示词：运行 python3 ~/mingyue/scripts/mem.py consolidate --day 今天
   --jsonl /tmp/mingyue-extract.jsonl；失败就报告错误，不要改数据，不要自己编。

3) 每周日 22:00 —— 周反思
   提示词：读最近 7 天的 episodes 与 facts，提出「矛盾 / 重复 / 失效」三类提案，
   交给 python3 ~/mingyue/scripts/mem.py report --week 处理；
   然后把「这周我记住了什么」压缩到 5 行以内，用 ~/mingyue/scripts/push.sh 发出去。

约束：三条任务都要写清楚时区；失败要留日志；不要自动删除任何记忆条目。
```

## 建完之后核对

- [ ] 三条任务的**时间**和**时区**正确
- [ ] 手动「立即运行」一次，看日志有没有报错
- [ ] 失败时任务不会静默跳过（要能在日志里看到原因）
