# 溟月 · 跟上上游（DSH Go）的更新

> 2026-11-16。配套 [PLAN.md](PLAN.md)。
> fork 的日常问题：上游一直在动，我改的东西怎么不被冲掉、又怎么吃到上游的修复。

---

## 0. 一句话

**你的改动全在新目录里**（`docs/mingyue/`、`mingyue/`），上游不会碰这些路径——所以现在同步几乎零冲突。冲突风险留到改 App 源码（改名、Chat/Work 模式）之后。

---

## 1. 远端怎么摆

| 名字 | 指向 | 用途 |
|---|---|---|
| `origin` | `git@github.com:Sumi-zome/MingYue.git` | **你的 fork**，日常推这里 |
| `upstream` | `git@github.com:ccch1mneyyy/dsh-go.git` | 原作者仓库，只读，用来拉更新 |

一次性整理（HTTPS 在国内常被掐，改走 SSH）：

```powershell
git remote set-url origin git@github.com:Sumi-zome/MingYue.git
git remote set-url upstream git@github.com:ccch1mneyyy/dsh-go.git
git remote remove fork          # 如果之前建过这个临时名字
git remote -v
```

> 公开仓库用任意有效 SSH key 都能读，不需要对方授权。

验证：

```powershell
git fetch --all
```

---

## 2. 同步上游（推荐流程）

```powershell
git fetch upstream
git log --oneline HEAD..upstream/main        # 上游多了什么
git diff --stat HEAD...upstream/main         # 会动哪些文件
```

看清楚了再动手。**别在主分支上直接合**：

```powershell
git switch -c sync/upstream-202612
git merge upstream/main
# 有冲突就解决（见 §5），没有就构建/试跑
git switch main
git merge sync/upstream-202612               # 确认没问题再回主分支
git branch -d sync/upstream-202612
git push origin main
```

优点：合崩了 `git switch main` 就回到干净状态，临时分支直接删掉。

---

## 3. merge 还是 rebase

| | 适合 | 代价 |
|---|---|---|
| **merge（默认选它）** | 自己的 fork、只自己用 | 历史多几条合并提交，但**不重写历史**、最安全 |
| rebase | 想要一条直线 | 变基后必须 force push，错一步就麻烦 |

**在你想清楚 force push 的风险之前，一律 merge。**

---

## 4. 升级前的三件事

```powershell
git tag mingyue-stable-20261116      # 打个可回退的点
git status -sb                       # 工作区必须干净
git log --oneline -3 --decorate      # 记住现在在哪
```

工作区不干净就别动——先 commit 或 stash。

---

## 5. 冲突了怎么办

```powershell
git status -sb          # 会列出 both modified 的文件
```

打开那些文件，找 `<<<<<<<`、`=======`、`>>>>>>>` 三段标记：

- 上面是你原来的，下面是上游的
- 改成你要的最终内容，**把三个标记全删掉**
- 然后：

```powershell
git add <冲突文件>
git commit              # merge 会自己带 message
```

想放弃这次合并：`git merge --abort`。

---

## 6. 版本耦合：这个仓库不是普通 App

它**钉死了引擎版本**（`runtime/locks/dsh-0.2.2-rc.1`）和补丁链（`runtime/patches/pins.json`）。所以升级要分清改的是什么：

| 上游改了什么 | App 要不要重建 | 旧手机后端要不要动 |
|---|---|---|
| 界面 / 文档 / 插件 | 看情况 | ❌ 不用 |
| 引擎版本号（如升到 0.2.3） | 要（APP 内嵌的客户端契约可能变） | ✅ `npm i -g @deepseek-ai/dsh@新版本` |
| `dsh-go-bridge` 协议 | 要 | ⚠️ 我们没装桥接，暂时无关 |

**好消息**：后端是**独立安装的原版 DSH**，不依赖这个仓库的补丁。所以"App 升级"和"后端升级"是解耦的——这是当初选 Termux 而不是 App 内置运行时的好处之一。

---

## 7. 升级后的验收（10 分钟）

- [ ] `flutter analyze` 能过（如果改到 App）
- [ ] App 能连上旧手机，能新建对话并收到回复
- [ ] `~/mingyue/scripts/export.sh` 还能跑
- [ ] 定时任务还在、还能触发
- [ ] 她的记忆文件没被动过（`ls -l ~/mingyue`）

任何一条不通过：`git reset --hard mingyue-stable-20261116`（**确认没有未提交改动再用**）。

---

## 8. 节奏建议

- **不用追每个提交**。一个月看一次，或遇到 bug 时才看。
- 上游大版本（引擎号变化）**先等两周**，看有没有人报问题。
- 每次升级前打 tag，升级后写一行记录到 `docs/mingyue/PHASE*.md` 或本文末尾。

---

## 9. 常见错误对照

| 报错 | 原因 | 处理 |
|---|---|---|
| `fatal: not a git repository` | 不在仓库目录 | `cd D:\MingYue` |
| `unrecognized argument: --online` | 拼错 | 是 `--oneline` |
| `schannel: server closed abruptly` | HTTPS 连 GitHub 被掐 | 改 SSH 远端，或 `git config --local http.proxy http://127.0.0.1:7890` |
| `Connection closed by UNKNOWN port 65535` + `CreateProcessW failed` | **不是网络**：`~/.ssh/config` 里 `ProxyCommand`（如 `connect`）程序不在 PATH | `ssh -T git@github.com` 确认；注释掉 ProxyCommand，或改用 `ssh.github.com:443` |
| `Could not read from remote repository` | 先分清网络还是本地 | 跑 `ssh -T git@github.com`：成功后失败 = 本地工具问题；失败 = 网络/认证问题 |
| `! [rejected] ... non-fast-forward` | 远端有你本地没有的提交 | `git pull --rebase origin main` 后再推 |
| 终端出现 `>>` | 命令没写完（多行粘贴，PS 5.1 不支持带格式粘贴） | 一行一行粘，或用 `;` 连接，或 Ctrl+C 重来 |

---

## 10. 升级记录（自己往里加）

| 日期 | 从 → 到 | 做了什么 | 结果 |
|---|---|---|---|
| 2026-11-16 | f5fa9256 → 7fed0370 | 首次提交溟月文档与脚本 | ✅ 已推 origin |
