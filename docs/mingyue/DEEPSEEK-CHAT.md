# 本地复刻的 DeepSeek 网页端（deepseek-chat）

> 2026-11-18。个人使用、不商用。基于官方开源前端 [deepseek-ai/chat-demo](https://github.com/deepseek-ai/chat-demo)（MIT，v0.1.1）。

## 它是什么

DeepSeek 官方 App/网页端的 **1:1 开源复刻**：静态 React 应用，浏览器直连 `api.deepseek.com`。
官方支持导入 `deepseek_data-日期.zip`（`export_format_version: 3`）——**你导出的历史会完整还原**：
消息树、分支、思维链、搜索步骤、网页阅读记录、附件图片。

**它和 DSH 的分工**：

| 前端 | 用途 |
|---|---|
| **deepseek-chat**（本文） | 复刻网页端：历史浏览、分支切换、正经问答（走 DeepSeek API） |
| **DSH / 溟月 App** | 溟月本人：人设、记忆、主动说话、图片/文件、定时任务 |

## 部署位置

| 项 | 值 |
|---|---|
| 源码 | `D:\deepseek-chat-src`（唯一分支，本地提交 `b422bb9`） |
| 构建产物 | `D:\deepseek-chat-src\dist` |
| 访问地址 | `http://127.0.0.1:8090`（本地静态服务） |
| 预编译包备份 | `D:\deepseek-chat-release`（官方 release，未改） |

**启动服务**（重启电脑后要重跑）：

```powershell
py -3 -m http.server 8090 --bind 127.0.0.1 --directory D:\deepseek-chat-src\dist
```

> 端口必须保持 **8090**：历史数据存在浏览器的 IndexedDB 里，按 **origin** 隔离，换端口等于换库。

## 本地改动（相对官方 v0.1.1）

| 文件 | 改了什么 |
|---|---|
| `src/assets/deepseek-web-logo.svg` | **官方侧边栏 logo 原件**（143×23，鱼+文字，`#3964FE`，取自 `fe-static.deepseek.com/chat/static/web-logo.svg`） |
| `src/assets/deepseek-favicon.svg` | **官方 favicon 原件**（纯鱼形，`#4D6BFE`） |
| `src/components/base/Logo.tsx` + `.module.css` | 侧边栏渲染官方 logo，保持原生 143×23 比例 |
| `src/components/base/BrandMark.tsx` + `.module.css` | 纯鱼形标志组件（官方 favicon 原件，28px），用于欢迎页 |
| `src/components/session/Welcome.tsx` + `.module.css` | 欢迎页对齐官方：鱼形标志（官方 viewBox 35×26 原件）+ 轮换问候语；参数取自官方 CSS（下边距 21、24px/600、max-width 840/712、padding 0 32 64） |
| `src/components/session/greeting.ts` | **问候语轮换**：5 条官方原文，按时间段挑候选再随机；每次新对话都不同 |
| `src/components/sider/Sider.tsx` | **Ctrl/Cmd + J** 快捷键新建对话；按钮右侧显示快捷键提示（官方同款）；列表间距恢复官方 24px |
| `src/index.html` | 标题 `DeepSeek`，favicon 用官方鱼形标志 |
| `rspack.config.ts` | `.svg` 走 `asset/source`；复制官方 favicon 到 dist |
| `src/services/chat/search.ts` | **历史全文搜索**：会话标题 + 用户消息 + 助手正文/思考，按更新时间倒序，最多 50 条，每会话最多 3 条 |
| `src/components/sider/SearchDialog.tsx` + `.module.css` | **官方样式搜索浮层**：位置在视口 13% 高度、圆角 18px、背景模糊 2px + 浅遮罩、较重阴影、深色搜索图标、关闭按钮左侧竖线；方向键选择、Enter 打开、Esc/点遮罩关闭 |
| `src/components/sider/Sider.tsx` | 顶栏加搜索图标（logo 右侧、收起按钮左侧）；原内联搜索框已移除；顶栏与列表间距按官方调整 |
| `src/i18n/{zh,en}.ts` | 欢迎语「你好，让我们开始聊天吧」；输入框占位「给 DeepSeek 发送消息」；搜索相关文案；appName 改为 `DeepSeek` |

## 重新构建

```powershell
cd D:\deepseek-chat-src
pnpm install                      # 首次或依赖变化时
$env:NODE_ENV='production'
npx rspack build -c rspack.config.ts
```

> 官方 `pnpm build` 脚本里的 `rm -rf dist` 在 Windows 上不可用，所以手动删 `dist` 再用 `npx rspack build`。

## 已知限制

- 搜索是**子串匹配**（中英文都行），没有分词/模糊；量大时首次搜索要扫 IndexedDB（已按更新时间倒序并提前停止）
- 点搜索结果只**打开会话**，不会滚动定位到那条消息（可后续加）
- 导入的回复不能"续写"（官方设计 `prefix: false`），但可以接着发新消息
- 浏览器数据只在本机；换浏览器/清缓存会丢，**重要对话定期用它的"导出"备份**
