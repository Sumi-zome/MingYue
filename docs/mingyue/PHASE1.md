# 阶段 1 部署与维护记录：App 连接旧手机后端

> 2026-11-16 实机完成，对应 [PLAN.md](PLAN.md) §5（前置复核对应 §4.9–§4.10、§11.3）。
> 本文记录**实际怎么连上的**、**踩了哪些坑**、**验收证据**、**日常怎么维护**。
> 承接 [PHASE0.md](PHASE0.md)：旧手机后端（Termux + 补丁版 dsh 0.2.2-rc.1 + sshd 8022 + Tailscale）已在阶段 0 立好。

---

## 0. 一句话

新手机（华为 P60 Art）安装**官方 DSH Go 1.1.0 arm64 APK**，加一台 SSH 主机 `u0_a45@100.122.251.16:8022`（托管启动，启动命令 `dsh web`，工作目录 `~/mingyue`），通过 App 的 SSH 隧道连上旧手机的 `dsh web`——会话列表、新建对话、杀 App 重连三条验收全过。

**关键认知**：这条链路 = **新手机 Tailscale → 旧手机 sshd:8022 → App 托管起/复用 `dsh web` → SSH 隧道 → HTTP API + SSE**。任何一层断掉，表现都可能是“没有响应”，所以排查顺序固定为：Tailscale/ssh 本身 → 端口/用户名/密码 → dsh 路径 → 华为后台 → 引擎 token。

---

## 1. 最终状态清单

| 项 | 值 |
|---|---|
| 新手机 | 华为 P60 Art（HarmonyOS，具体版本未记录） |
| App | **官方 DSH Go v1.1.0**（arm64 APK，`dsh-go-1.1.0-arm64.apk`，231,458,868 字节） |
| App 安装来源 | 官方下载桶 `https://dl.dshtui.com/download/1.1.0/dsh-go-1.1.0-arm64.apk`（GitHub 在宿舍网不通） |
| 主机名（App 内） | `旧手机`（自定义） |
| 主机 / 端口 | `100.122.251.16` / `8022`（旧手机 Tailscale 节点 `lio-an00`） |
| 用户名 / 密码 | `u0_a45` / Termux 里 `passwd` 设的（**不写文档**） |
| 实例管理 | **托管启动** |
| 启动命令 | `dsh web`（App 会自动追加 `--host 127.0.0.1 --port 0 --no-open`） |
| 工作目录 | `/data/data/com.termux/files/home/mingyue` |
| SSH 压缩 | 默认开启（与服务器协商，不支持时回落未压缩） |
| 主机指纹（ED25519） | `SHA256:89x1v9sdp+ElADmxMOl1bgIOn6EE7wPZExA9fao3fQI` |
| 主机指纹（RSA / ECDSA） | `SHA256:b0gLcWygg/EJuQxbogbmZiBXSingf+81/4dQ1o63RUI` / `SHA256:l2MkO54uM0Ja+KG88WgtUC84lxzzKxPQv6z8kGmg3Tw` |
| App 托管状态文件（旧手机） | `~/.dsh-app-remote/`：`web.pid` / `web.log` / `web.cmd` |
| PC 侧维护入口 | `ssh -p 8022 u0_a45@100.122.251.16`（密码登录；PC Tailscale 节点 `100.67.78.34`） |
| 旧手机手动引擎 | 已停；`~/bin/dsh-web.sh` / 3080 端口的手动实例**不再使用** |

---

## 2. 新手机侧前置（华为）

1. **安装 App 前**：暂时关闭 Google Play 保护机制的扫描
   （Play 商店 → 右上头像 → Play 保护机制 → 右上齿轮 → 关闭「使用 Play 保护机制扫描应用 / 扫描应用以查找威胁」）。
   否则侧载 APK 会被 Play Protect 直接拦下，没有「仍要安装」入口。
2. **Tailscale**：登录**和旧手机 / PC 同一个账号**，确认状态 Connected、设备列表里能看到旧手机（`lio-an00`）；点旧手机 Ping 应有延迟。
3. **华为四项**（和 PHASE0 §2 给旧手机做的一样，新手机也要做一遍）：
   应用启动管理 → Tailscale（及 DSH Go）→ 手动管理，自启动 / 关联启动 / 后台活动全开；
   电池 → 应用耗电管理 → 允许后台活动；关掉“锁屏后清理后台”；不使用一键清理，保留通知。
   建议：设置 → 更多连接 → VPN → 允许并「始终开启 VPN」。
4. 允许浏览器/文件管理器安装未知来源应用（首次安装 APK 时按系统提示允许）。

> 本次为安装临时关闭了 Play Protect 扫描；装完可以恢复，恢复后它可能再次提示 DSH Go 有风险，属启发式误报（App 自带 Linux 运行时/自更新）。

---

## 3. 实际步骤（含前置复核）

### 3.1 §4.9 四项复核

| 项 | 本次结论 |
|---|---|
| 旧手机重启后 ~2 分钟内可 ssh | **采用 PHASE0 记录**（解锁后约 60s），本次未重测 |
| 关 WiFi 只留流量仍可 ssh | 用户报阶段 0 已验过，本次未重测 |
| 锁屏 30 分钟后仍可 ssh | **采用 PHASE0 记录**（单次抽样），本次未重测 |
| `dsh web` 能打印带 token 的地址 | **本次实测通过**（见 3.3） |

> 实测口径补充：Android Direct Boot 会限制重启后首次解锁前的普通 App（Termux/Tailscale），所以“重启后 2 分钟”= **解锁一次后**约 60s 内。

### 3.2 基线连通（PC → 旧手机）

```powershell
ssh -o ConnectTimeout=10 -o PreferredAuthentications=password -o PubkeyAuthentication=no -p 8022 u0_a45@100.122.251.16 "whoami; date"
```

- 输出 `u0_a45` + 正确时间 → 密码登录路径可用（App 用的就是这条）
- `/proc/uptime` 读不了（`Permission denied`）是 Android 内核限制，不是故障；要计时改用 `~/boot.log`

### 3.3 清掉阶段 0 残留引擎 + 验证 `dsh web`

旧手机 Termux 里：

```sh
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3080/   # 是 401 说明有旧引擎
ps -ef | grep -F 'dsh web' | grep -v grep                               # 找到 PID（本次 14332）
kill 14332
curl -s -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:3080/   # 应为 000
dsh web --host 127.0.0.1 --port 3080 --no-open                          # 应打印 dsh web: http://127.0.0.1:3080/?token=…
```

看到 token 行即通过，**Ctrl+C 停掉**（token 不写文档、不外发）。确认工作目录存在：

```sh
mkdir -p /data/data/com.termux/files/home/mingyue && ls -ld /data/data/com.termux/files/home/mingyue
```

### 3.4 App 里填主机

远程主机 → 添加 SSH 主机，字段见本文 §1 表 → **测试连接**：

1. App 经 SSH 登录、读取主机指纹，首次连接弹窗核对（对上 §1 的 ED25519 指纹）
2. 按启动命令执行 `dsh web --host 127.0.0.1 --port 0 --no-open`（`nohup` 常驻，端口由系统挑空闲的），从 `~/.dsh-app-remote/web.log` 取 token
3. 经 SSH 本地转发连上 `127.0.0.1:<port>`，测试通过 → **保存** → 在主机列表**选中它**

### 3.5 §5.2 验收

见 §8。

---

## 4. 踩的坑与修复（本次真实遇到）

| 现象 | 根因 | 处理 |
|---|---|---|
| PHASE0 文档里的主机指纹和 PC `known_hosts` 对不上（少一段 `6EE`） | 抄写漏字 | 以 PC `known_hosts` 为准修正（另一个窗口已改 PHASE0）；App 核对指纹时用修正后的值 |
| 新手机没装 DSH Go | 阶段 0 只管旧手机 | 装官方 v1.1.0 arm64 APK；这台 PC 没有 Flutter/Android SDK，无法自建 fork 包 |
| `github.com` / Release 资源在宿舍网不通、超时 | 网络 | 用官方下载桶 `dl.dshtui.com`（可达，约 110–150 KB/s，231 MB 约 25–40 分钟） |
| 安装被 Google Play 保护机制拦截 | Play Protect 启发式（App 带 Linux 运行时、侧载） | 关闭「扫描应用以查找威胁」后重装成功 |
| App 报 `100.122.251.16:8022 没有响应` | 新手机 Tailscale 未就绪（未连接/未登录）→ 没有 `100.x` 路由 | 新手机装/登录 Tailscale，Connected、设备列表能看到旧手机后复测通过 |
| 旧手机上 `dsh web` 报 `EADDRINUSE` / `2 required plugins did not activate` | 阶段 0 遗留引擎占着 3080 | `kill <PID>` 后再起；不是 dsh 坏了 |
| `cat /proc/uptime: Permission denied` | Android 内核不让普通 App 读 | 计时改用 `tail -5 ~/boot.log` |
| PowerShell 5.1 里 `ssh … 'pkill -f "$P web"; …'` 报 `pkill: only one pattern can be provided`、`curl` 参数错乱 | PowerShell 5.1 传给原生程序时会吞掉内嵌双引号 | 远程命令里避免内嵌双引号（用单引号包整条，或改用 Termux 交互式执行） |
| 杀 App 重开后提示「复用已在运行的 DSH（端口 xxxx）」 | §4.10 设计：托管引擎 `nohup` 常驻 | 正常，无需处理 |

---

## 5. 日常操作

- **连接**：打开 App → 主机列表选「旧手机」。托管启动会自动**复用**上次的引擎；没有存活实例时自动拉起。
- **旧手机重启后**：需要先**解锁一次**（Direct Boot），约 60s 后台恢复 sshd/Tailscale，然后**打开 App 连一次**——引擎不会自启（§4.10 方案 A）。
- **看托管引擎状态**（旧手机 Termux 或 PC ssh）：

  ```sh
  ls -l ~/.dsh-app-remote/
  tail -20 ~/.dsh-app-remote/web.log    # 含当前端口和 token，别外发
  ps -ef | grep -F 'dsh web' | grep -v grep
  ```

- **停掉托管引擎**（需要时，例如排障）：

  ```sh
  kill "$(cat ~/.dsh-app-remote/web.pid)"
  ```

- **PC 维护**：`ssh -p 8022 u0_a45@100.122.251.16`；不要再用 `~/bin/dsh-web.sh` 或手动 `dsh web` 起第二个实例。
- **PC 浏览器看引擎（可选）**：从 `~/.dsh-app-remote/web.log` 取端口和 token，`ssh -N -p 8022 -L <port>:127.0.0.1:<port> u0_a45@100.122.251.16`，再开 `http://127.0.0.1:<port>/?token=…`。日常不需要。

---

## 6. 故障排查对照表

| 现象 | 归类 | 处理 |
|---|---|---|
| App「测试连接」报没有响应 / 超时 | 网络层 | 新手机 Tailscale 是否 Connected；旧手机 Tailscale 是否在线；Ping 旧手机 100.122.251.16 |
| App 报用户名或密码不对 | 认证层 | 用户名必须是 `u0_a45`；密码是 Termux `passwd` 设的（不是锁屏密码） |
| App 报“主机上没有 dsh” | dsh 路径 | 启动命令改 `/data/data/com.termux/files/usr/bin/dsh web` |
| 托管启动失败 / 拿不到 token | 引擎层 | 旧手机 `tail -20 ~/.dsh-app-remote/web.log`；`ps -ef` 看是否已有实例 |
| 提示“远端托管 DSH 仍在运行，但启动命令不同或缺少有效启动日志” | 共享实例保护 | 旧手机手动引擎残留：`ps -ef \| grep 'dsh web'` 找 PID 后 kill，再重试 |
| SSH 能连但引擎起不来 / 连上后断 | 华为后台 | 旧手机 §4.3 四项、Termux 通知别清；必要时重新解锁后重试 |
| 主机指纹弹窗与预期不一致 | 指纹 | 以 PC `known_hosts` 为准；确认手机没重装/换过 host key；App 里可重置指纹（仅确认重装/换机时） |
| 会话里工具报“沙箱后端不可用” | Android 无沙箱（PHASE0 §5.4） | 会话发 `/permission danger-full-access`；新会话默认权限在引擎 Web UI → 设置 → 通用里改 |
| 更新/重装 App | 签名 | 官方包签名固定；换自建包（不同签名）必须卸载重装一次 |

---

## 7. 已知限制 / 未验证

- **引擎不自启**（PLAN §4.10 方案 A）：重启后、未开 App 期间“她”不在线；阶段 2 的定时任务依赖引擎常驻，这是已知取舍。方案 B（Termux 自启脚本 + 伪装 `~/.dsh-app-remote` 状态）**未验证**。
- **重启 / 关 WiFi / 锁屏 30 分钟**三项本次未重测，采用 PHASE0 的单次采样证据，不能保证每次都不被华为清后台。
- **App 是官方 v1.1.0 包，不是 fork（溟月）构建**：功能零改动满足阶段 1；阶段 3 改名/图标需要自建 APK（这台 PC 目前无 Flutter / Android SDK），且签名不同需卸载重装一次（对话在主机上，不受影响）。
- **Android 上没有可用沙箱**：默认 `workspace-write` 下 bash 工具会失败，须用 `danger-full-access`（PHASE0 §5.4）；本记录阶段 1 只验证纯对话，未改默认权限。
- **新手机侧华为后台四项/VPN 常开**：本次只是能连上，长期是否会被清后台需观察；ntfy 推送（阶段 2）也会依赖它。
- **Play Protect**：为安装临时关闭扫描；是否恢复、恢复后是否再次提示，本次未验证。

---

## 8. 验收证据（§5.2）

| 验收项 | 结果 |
|---|---|
| 会话列表能拉出来（空列表也算成功） | ✅ 能拉出，能看到本次新建的会话 |
| 能新建对话并收到回复（说明 DeepSeek Key 配对了） | ✅ 收到回复：「你好！有什么可以帮你的？」 |
| 杀掉 App 再打开，主机还在、还能连 | ✅ 重开后主机保留，能重新连接并复用托管引擎 |

补充证据：

- 旧手机 `dsh web` 实测打印 `dsh web: http://127.0.0.1:3080/?token=…`（token 已随进程结束作废，不记录）。
- App 主机指纹与 PC `known_hosts` 的 ED25519 指纹一致（见 §1）。
- 旧手机 `~/mingyue` 存在（2026-11-16 16:47 创建，owner `u0_a45`）。

---

## 9. 阶段 2 交接参数

| 字段 | 值 |
|---|---|
| 主机 | `100.122.251.16` |
| 端口 | `8022` |
| 用户名 | `u0_a45` |
| 密码 | 手机上 `passwd` 设的（不写文档） |
| 指纹（ED25519） | `SHA256:89x1v9sdp+ElADmxMOl1bgIOn6EE7wPZExA9fao3fQI` |
| 实例管理 | 托管启动 |
| 启动命令 | `dsh web`（not found 时用 `/data/data/com.termux/files/usr/bin/dsh web`） |
| 工作目录 | `/data/data/com.termux/files/home/mingyue` |
| App 托管状态 | 旧手机 `~/.dsh-app-remote/` |
| App 构建 | 官方 v1.1.0 arm64；尚未自建 溟月 包 |

**下一步**（PLAN §12 窗口 B 起）：

- 先做 §5.4 的权限预设：引擎 Web UI → 设置 → 通用 → 新建会话的默认权限 = `danger-full-access`（或在会话里发 `/permission danger-full-access`）。
- 阶段 2a：人设 + 六层记忆（`mem.py` + `schema.sql` + 三个整理任务），材料 = PLAN §6.2–6.4 + MEMORY.md 全文。
- 阶段 2b（内容理解 skill）、2c（ntfy 推送）见 PLAN §6.5–6.7。
