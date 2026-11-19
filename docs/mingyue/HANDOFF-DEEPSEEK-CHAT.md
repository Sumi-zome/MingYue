# 交接：把 deepseek-chat（fork 自官方 chat-demo）复刻成官方 DeepSeek 网页端（窗口 U）

> 用户评价：「感觉还是差了很多」——需要继续做像素级对齐。
> 本文件是完整交接：环境、已完成的、参考材料、方法、待办。

## 一句话目标

让 `http://127.0.0.1:8090` 打开的页面，**看起来和官方 chat.deepseek.com 一致**（个人自用，不商用）。
功能已经齐全（历史导入/分支/搜索/对话），现在只差**视觉细节**。

## 环境与固定项

| 项 | 值 |
|---|---|
| 源码 | `D:\deepseek-chat-src`（fork 自 deepseek-ai/chat-demo v0.1.1，MIT） |
| 构建 | `cd D:\deepseek-chat-src; pnpm install; $env:NODE_ENV='production'; npx rspack build -c rspack.config.ts` |
| 服务 | `py -3 -m http.server 8090 --bind 127.0.0.1 --directory D:\deepseek-chat-src\dist`（后台） |
| 访问 | `http://127.0.0.1:8090` |
| 原版备份 | `D:\deepseek-chat-release`（官方预编译 release，未改） |
| 本地提交 | `3b878af`（最新）：`git -C D:\deepseek-chat-src log --oneline` |

**⚠️ 端口必须保持 8090**：用户的历史数据在浏览器 IndexedDB 里，按 origin 隔离。

**每次改完**：重建 → 重启 8090 服务 → 让用户 `Ctrl+Shift+R` 硬刷新。

## 已完成的改动

见 [DEEPSEEK-CHAT.md](DEEPSEEK-CHAT.md) 的「本地改动」表。摘要：

1. 侧栏 logo：官方 `web-logo.svg` 原件（143×23）
2. favicon：官方 `favicon.svg`（纯鱼形），文件名 `favicon-deepseek.svg`（绕开浏览器 favicon 缓存）
3. 欢迎页：官方鱼形 SVG（viewBox 35×26）+ **5 条官方问候语按时段随机轮换**
4. 历史搜索：顶栏放大镜 → 居中浮层 + 背景模糊（按用户截图对齐：13vh 位置、圆角 18、阴影加重、关闭按钮左侧竖线）
5. 侧栏：新建对话按钮右侧 `Ctrl + J` 提示，并**真的实现**该快捷键
6. 标题栏 `DeepSeek`

## 关键参考材料（一定要用）

### 1. 用户保存的官方页面（最有价值）

```
D:\official-page\DeepSeek - 探索未至之境.htm                 官方渲染后 DOM（186KB）
D:\official-page\DeepSeek - 探索未至之境_files\
    main.dc093a796f_Kn51.css                                 官方完整应用 CSS（296KB）
    main.1994c85c88_Kn51.js                                  官方主 JS（1.6MB）
```

**官方用的是 CSS Modules 哈希类名**（如 `_77cefa5`），但**所有规则都在那份 CSS 里**。
方法：从 `.htm` 里找目标元素的 class → 在 CSS 里 grep 那个类 → 抄精确数值。

已经挖到的类名对照（不要重复挖）：

| 元素 | 官方类名 | 官方样式 |
|---|---|---|
| 侧栏 logo | `e066abb8` | `width:143px;height:23px`，`svg{width:100%;height:100%}` |
| 欢迎区外层 | `_9a2f8e4` | `max-width:840px`（窄屏 712）、`padding:0 32px 64px`、flex 居中 |
| 欢迎语行 | `_5758a85 ._6c7e7df` | flex 居中换行、`margin-bottom:21px`、24px/600/32px |
| 问候鱼形 | `_5758a85 .ce41ed1b` | `34×25`、`margin-right:10px`、`transform:scale(.88)` |
| 新对话按钮 | `dc1f7bee` / `_4bcc731` / `_5a8ac7a` / `a084f19e` | `_5a8ac7a` 有 hover 阴影、`:after{content:"⌘ J";right:11px}`、`a084f19e:after{content:"Ctrl + J"}` |
| 侧栏列表区 | `_3586175` | `flex:1;min-height:0;margin-top:24px` |
| 输入框容器 | `_77cefa5` | `font-size:16px;line-height:24px;border:1px solid var(--dsw-alias-border-l2-darkmode-thin);background:var(--dsw-specific-input-major);border-radius:24px` |

全局令牌：官方与 DSH 共用 `--dsw-alias-*` / `--dsw-specific-*`；`--sider-width:261px`。

### 2. 官方静态资源（公开可直连）

| 用途 | URL |
|---|---|
| favicon（纯鱼） | `https://fe-static.deepseek.com/chat/favicon.svg` |
| 侧栏 logo（鱼+文字） | `https://fe-static.deepseek.com/chat/static/web-logo.svg` |
| 官方主 CSS | `https://fe-static.deepseek.com/chat/static/main.dc093a796f.css` |
| 官方主 JS | `https://fe-static.deepseek.com/chat/static/main.1994c85c88.js` |

> 说明：**不能**登录用户账号（没有浏览器控制权）。要更多官方状态，让用户再保存页面到
> `D:\official-page\`（例如打开搜索框时保存、鼠标悬停会话项时保存）。

### 3. 用户提供的官方截图（描述）

- 侧栏：logo 左、右侧两个图标（🔍 搜索、收起）；下面「开启新对话」胶囊按钮（右侧 Ctrl+J）；分组「置顶 / 昨天 / 7 天内…」，分组标题右侧有个小列表图标；分组之间有分隔线；底部有用户头像区
- 欢迎语 5 条（用户已提供全部文字）
- 搜索：点顶栏 🔍 → 居中浮层（宽约 640）、输入「搜索对话内容…」、右侧细竖线 + X、背景整体模糊变暗

## 待办（按优先级）

1. **侧栏结构对齐**（差距最大）：
   - 顶部：logo + 搜索 + 收起 的间距、按钮尺寸
   - 「开启新对话」按钮的尺寸/圆角/阴影/内边距
   - 分组标题行：右侧分组菜单图标、分组间分隔线
   - 会话项：高度、圆角、hover/active 背景、标题字号
   - 底部：官方有用户头像区，我们的版本是「设置」——决定是否改造
2. **搜索浮层**：结果项样式、键盘提示、空状态；对照官方截图再微调
3. **欢迎页**：鱼和文字的垂直对齐、整体垂直位置（官方偏上一点）
4. **输入框**：官方是 24px 圆角、16px 字号、切换按钮（深度思考/智能搜索）胶囊样式
5. **消息气泡/正文排版**：字号、行高、引用角标（官方样式可从 CSS 挖）

## 工作方法（重要）

1. **先要截图**：让用户发「官方 vs 我们」的同位置截图，一次只改 1–2 处
2. **从官方 CSS 抄数值，不靠感觉**：在 `.htm` 找类名 → 在 CSS grep 规则
3. 每轮：改 → 构建 → 重启服务 → 让用户硬刷新 → 截图对比
4. 每次改完 `git -C D:\deepseek-chat-src commit`（本地提交，不推 GitHub）
5. 不要动 `src/services/**` 的数据逻辑（导入/对话/分支已验证可用）

## 约束

- 个人使用，不商用；保留 MIT LICENSE 与仓库 NOTICE
- 不要把 `D:\official-page\` 的内容提交进仓库（**含用户登录态页面的私密内容**）
- 不要改用户的历史数据；不要清 IndexedDB
- 不要用端口以外的 origin（会丢历史）
- 不要 commit 到 GitHub；本地提交即可
- 提交前 `git status` 确认没有把个人数据/截图加进去

## 验收

用户看着新页面说「像官方了」。具体可量化的：

- 侧栏整体宽度 261px、logo 143×23、各分组间距与官方一致
- 欢迎页问候语鱼 34×25（scale .88）+ 24px/600 文字、下边距 21
- 搜索浮层位置/宽高/阴影与截图一致
