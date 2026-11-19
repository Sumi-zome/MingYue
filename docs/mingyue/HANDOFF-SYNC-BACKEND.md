# 交接：给 deepseek-chat 加同步后端，做多端共享（窗口 S）

> 目标：让 **PC / 新手机 / 旧手机浏览器访问同一个后端**，看到同一份会话、图片、搜索数据。
> 服务端跑在**旧手机 Termux**（24h 在线、Tailscale 可达），PC 和新手机只是浏览器客户端。

## 为什么需要后端（背景）

现在的 `deepseek-chat`（`D:\deepseek-chat-src`）是**纯静态前端**：数据存在浏览器的 IndexedDB。
所以不管从哪台设备打开，各设备都是**自己的一份数据**，换设备等于换库（IndexedDB 按 origin + 设备隔离）。

要"多端共享"必须把存储搬到服务端：前端改成调 API，服务端存数据。

## 现状

| 项 | 值 |
|---|---|
| 前端源码 | `D:\deepseek-chat-src`（fork 自官方 chat-demo v0.1.1，MIT，已改名 deepseek-chat） |
| 构建 | `pnpm install; $env:NODE_ENV='production'; npx rspack build -c rspack.config.ts` |
| 当前服务 | 临时 `python -m http.server 8090 --directory dist`（本地 PC） |
| 数据层 | `src/services/chat/db.ts`（idb 封装）、`store.ts`、`search.ts`、`history/`（导入导出 zip） |
| 设置层 | `src/services/settings.ts`（localStorage，含 API Key） |
| 旧手机 | Termux，Node v26.13.1，SSH 别名 `mingyue`，Tailscale IP `100.122.251.16`，剩余 135GB |

## 目标架构

```
旧手机（Termux，常驻）
┌────────────────────────────────────────────┐
│ node server.js                             │
│   GET  /                → dist 静态文件     │
│   /api/*                → 数据接口          │
│   数据目录 ~/deepseek-chat-data/            │
│     sessions/<id>.json    会话（含消息树）   │
│     files/<id>            附件原件          │
│     index.json            会话摘要索引      │
└───────────────┬────────────────────────────┘
                │ Tailscale（100.122.251.16:8090）
     ┌──────────┼──────────┐
     ▼          ▼          ▼
   PC 浏览器  新手机浏览器  旧手机浏览器
        （同一份服务端数据）
```

**鉴权**：必须。最简单：`Authorization: Bearer <token>`，token 存在服务端配置，前端首次输入后存 localStorage；服务只监听 Tailscale 网段（不裸露公网）。

## 实施步骤

### 1. 服务端（Node，零/少依赖）

新建 `D:\deepseek-chat-src\server\`：

- `server.js`：内置 `node:http` + `node:fs`，**不要用 better-sqlite3 之类的原生模块**（Termux 上编译风险大）；直接 JSON 文件存储即可，天然好备份
- 静态服务：把 `dist/` 原样提供（支持 SPA 回退到 index.html）
- API 设计（对应现有 db.ts 的操作）：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/sessions` | 会话摘要列表 |
| GET | `/api/sessions/:id` | 单个会话（含 messages） |
| PUT | `/api/sessions/:id` | 保存会话 + 新附件 |
| DELETE | `/api/sessions/:id` | 删除会话（清理孤儿附件） |
| POST | `/api/sessions/:id/rename` | 重命名 |
| GET | `/api/files/:id` | 取附件二进制 |
| POST | `/api/files` | 上传附件（multipart 或 raw body） |
| GET | `/api/search?q=` | **服务端全文搜索**（用 `search.ts` 的同一套逻辑，但跑在服务端，避免 1013 个会话逐个 HTTP 拉取） |
| GET | `/api/export` / POST `/api/import` | 可选：服务端整库导出/导入 zip |

- 写入要原子：先写 `xxx.tmp` 再 `rename`；索引文件同理
- 并发：同一会话的 PUT 串行化（简单内存锁）

### 2. 前端改造（保持上层代码不动）

`src/services/chat/db.ts` 是唯一数据入口，保持**函数签名不变**，内部改成 fetch：

```ts
// 旧：openDB('deepseek-chat', ...) → 现在：fetch('/api/...') + 内存缓存
export const loadSessionSummaries = () => apiGet('/api/sessions')
export const loadSession = (id) => apiGet(`/api/sessions/${id}`)
export const saveSession = (session, files) => apiPut(...)
...
```

- `src/services/chat/search.ts`：改成调 `/api/search`（服务端搜索），不再本地遍历
- `history/importArchive.ts`：客户端解析 zip 不变，只是落库走 saveSession API；**首次迁移就是在这里把 220MB 导进去**
- `settings.ts`：**保持 localStorage**（API Key 每台设备各自填，不传服务端）；新增 `serverUrl` + `serverToken` 两个设置项，未配置时退化为"本地模式"（可选，先不做）
- 所有请求带 `Authorization` 头，401 时提示重新输入 token

### 3. 部署到旧手机

```bash
# PC → 手机
scp -r D:\deepseek-chat-src\dist mingyue:~/deepseek-chat/
scp D:\deepseek-chat-src\server\server.js mingyue:~/deepseek-chat/
ssh mingyue 'cd ~/deepseek-chat && nohup node server.js --port 8090 > serve.log 2>&1 &'
```

- 监听 `0.0.0.0:8090`（或 `100.122.251.16:8090`），Tailscale 内网访问
- 开机自启：写进 `~/.termux/boot/server`（已有 wake-lock/sshd，追加一行）
- 数据目录 `~/deepseek-chat-data/`，**排除出 `export.sh` 备份包**或单独打包

### 4. 验证（多端）

1. PC 打开 `http://100.122.251.16:8090` → 输入 token
2. 导入 220MB 历史 zip → 等写完
3. 新手机浏览器（Tailscale 同网）打开同一地址 → **应看到同样的会话列表**
4. 在 PC 新建对话、发消息 → 新手机刷新能看到
5. 图片附件两端都能显示
6. 搜索在两端结果一致
7. 断网重连、服务重启后数据仍在（持久化验证）

### 5. 备份

```bash
tar -czf ~/backups/deepseek-chat-$(date +%F).tar.gz -C ~ deepseek-chat-data
```

保留最近 7 份；或者交给已有的备份脚本统一管理。

## 风险与取舍

| 风险 | 说明 |
|---|---|
| 性能 | 1013 个会话、220MB；服务端 JSON 文件读取要加缓存（内存 LRU），搜索用服务端扫描 |
| 并发写 | 单用户多设备，last-write-wins；同一会话同时编辑可能覆盖（先接受） |
| Termux 稳定性 | 和 DSH 引擎一样会被系统冻结；已有 wake-lock，但仍可能休眠（手机设置里关电池优化） |
| API Key | **不上传服务端**，每台设备自己填；服务端只存聊天数据 |
| 端口 | 8090 对旧手机是新的（DSH 引擎用 43703 之类随机端口，不冲突） |
| 迁移 | PC 浏览器里现在有 220MB 数据，切服务端后要**重新导入一次**（导出 zip 已有） |

## 不要做

- 不要用原生 sqlite 模块（Termux 编译风险）
- 不要把 API Key 传服务端
- 不要把服务端口暴露到公网（只 Tailscale）
- 不要动 `src/services/chat/types.ts` 的数据结构（服务端就存同样的 JSON）
- 不要把 `D:\official-page` 或用户聊天数据提交进 git

## 验收

一台设备发消息、另一台设备刷新能看到；新设备打开即可看到全部历史；服务重启数据不丢。
