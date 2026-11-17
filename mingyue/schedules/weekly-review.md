# 溟月 · 周反思（每周一 04:20）

> 定时任务用，对应 [SETUP.md](SETUP.md) 第 3 条。每次在新会话里执行；**不要和任何人聊天**。

## 步骤

1. 运行统计：

   ```
   python3 ~/mingyue/scripts/mem.py report --week
   ```

2. 运行衰减归档（`importance>=0.8` 的永远不会动）：

   ```
   python3 ~/mingyue/scripts/mem.py decay
   ```

3. **只读**检查最近 7 天（不要自己改库）：看 `report` 输出，用 `mem.py search` 或只读
   `sqlite3 ~/mingyue/memory.db "SELECT …"` 抽查。找三类问题：

   - **矛盾**：两条不能同时成立；
   - **重复**：同一件事说了多遍；
   - **失效**：明显过时的（毕业季结束之类）。

4. 用 **≤5 行**写"这周我记住了什么"（给主人看的）。如果发现该改的，最后加一行 `建议：…`。

5. 只回复这段总结 + decay 的归档条数；**不要自己 supersede / archive / pin**，改库由主人确认后手动做。
   不要贴会话原文。
