# 阶段 0 部署与维护记录：旧手机后端

> 2026-11-16 实机完成，对应 [PLAN.md](PLAN.md) §4。
> 本文记录**实际怎么搭起来的**、**为什么有 5 处本地修补**、**升级 dsh 怎么办**、**重装怎么办**。
> 环境：旧手机华为 Mate30 Pro（HarmonyOS 4.2，Android 兼容层 12，aarch64，Termux 用户 `u0_a45`）。

---

## 0. 一句话

旧手机 = **Termux + Node 26 + npm 全局 `@deepseek-ai/dsh@0.2.2-rc.1` + 5 处 Android(bionic) 本地修补 + sshd + Tailscale**。
新手机/PC 通过 SSH（`100.122.251.16:8022`）连它；引擎由 `dsh web --host 127.0.0.1 --port 3080` 起在本机回环。

**关键认知**：npm 上的 dsh 只发布 darwin/linux/win32 的原生预编译件，**Android(bionic) 没有任何现成包**。所以这不是"装个 npm 包"那么简单，下面的 5 处修补是必须的。

---

## 1. 最终状态清单

| 项 | 值 |
|---|---|
| Termux 用户 | `u0_a45` |
| Home | `/data/data/com.termux/files/home` |
| Node | **26.13.1**（`modules=147`、`napi=10`、`platform=android`） |
| npm 源 | `https://registry.npmmirror.com` |
| Node 头文件 | `$PREFIX/include/node`（Termux nodejs 包自带） |
| dsh | `0.2.2-rc.1`（全局装在 `$PREFIX/lib/node_modules/@deepseek-ai/dsh`） |
| 引擎端口 | `127.0.0.1:3080`（**只回环**，外部靠 SSH 隧道） |
| sshd | `8022`，密码登录；host key 指纹 `SHA256:89x1v9sdp+ElADmxMOl1bgIOn6EE7wPZExA9fao3fQI`（ED25519） |
| Tailscale | 旧手机节点 `lio-an00` = `100.122.251.16`；PC 节点 `100.67.78.34` |
| 工作区 | `/data/data/com.termux/files/home/mingyue` |
| DeepSeek Key | 已存在旧手机 `~/.dsh/`（浏览器里配的，**不在仓库、不在文档**） |
| 常驻脚本 | `~/bin/dsh-web.sh`、`~/bin/fix-dsh-native.py`、`~/.termux/boot/server` |

---

## 2. 系统侧前置（华为）

1. **关闭纯净模式**：设置 → 系统和更新 → 纯净模式 → 退出（否则 APK 装不上）。
2. 安装未知来源：首次装 APK 时允许浏览器/文件管理器安装。
3. **应用启动管理**：设置 → 应用和服务 → 应用启动管理 → Termux / Termux:Boot / Tailscale 全部「手动管理」，**自启动、关联启动、后台活动** 三个全开。
4. **电池**：应用耗电管理 → 同上三个 App → 允许后台活动。
5. 关掉「锁屏后清理后台」类开关；不用一键清理；Termux/Tailscale 的通知保留。
6. 电池 → 更多电池设置 → **休眠时始终保持网络连接** 开启。
7. **Tailscale 建议开「始终开启 VPN」**（设置 → 更多连接 → VPN），减少重启后不重连的概率。

### 已知限制：重启后必须解锁一次

Android **Direct Boot**：手机重启后、首次解锁前，普通 App（Termux/Tailscale 都不是 directBootAware）收不到开机广播、VPN 也起不来。
- 所以 §4.9「重启后 2 分钟内 SSH」的正确口径是：**重启 → 手机解锁一次 → 约 60s 内 PC 可 SSH**。
- 实测：解锁后 tailnet 约 51s 恢复、sshd 约 60s 就绪（`~/boot.log` 有 `=== boot` 时间戳 + `sshd exit: 0`）。
- 如果确实要"完全无人值守"，只能取消锁屏密码（安全取舍，未采用）。

---

## 3. 从零重装流程（手机重置/换机时照抄）

### 3.1 装 App

- **Termux**、**Termux:Boot**：F-Droid（不要 Play 版；Termux:Boot 装完**必须打开一次**）。
- **Tailscale**：官网 Universal APK（`pkgs.tailscale.com/stable`，不用 F-Droid 构建）。
- 依次做 §2 的系统设置。

### 3.2 Termux 环境

```bash
termux-change-repo                     # Main repository → Mirrors in China（TUNA 等）
pkg update -y && pkg upgrade -y
pkg install -y nodejs openssh python curl clang make binutils cmake
node -v                                # 需要 ≥22.19 或 ≥24；本机实际 26.13.1
npm config set registry https://registry.npmmirror.com
```

> `clang/make/python` 是 node-gyp 编译 `node-pty`、`koffi` 用的；`cmake` 是 koffi 的 cnoke 构建器用的。

### 3.3 装 dsh

**关键：npm 11 默认拦截依赖的安装脚本**（`install-scripts ... blocked`），必须显式放行，否则 `koffi`/`node-pty` 的构建脚本不会跑。

```bash
export npm_config_disturl=https://npmmirror.com/mirrors/node   # node-gyp 下 headers 走国内镜像
npm i -g --foreground-scripts \
  --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs \
  @deepseek-ai/dsh@0.2.2-rc.1
dsh --version                          # 0.2.2-rc.1
```

> `npm warn Unknown env config "disturl"` 是噪音：npm 不认识这个环境变量，但 node-gyp 自己会读，可忽略。

### 3.4 打本地修补（见 §4）

```bash
python ~/bin/fix-dsh-native.py         # 脚本见附录 A；首次需先创建
```

### 3.5 sshd 与开机自启

```bash
passwd                                 # 设 SSH 密码（自己记住，不写文档）
whoami                                 # u0_a45
sshd                                   # 默认 8022
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/server <<'EOF'
#!/data/data/com.termux/files/usr/bin/sh
LOG=/data/data/com.termux/files/home/boot.log
exec >>"$LOG" 2>&1
echo "=== boot $(date) ==="
termux-wake-lock
sshd
echo "sshd exit: $?"
EOF
chmod +x ~/.termux/boot/server
```

> shebang 必须是 `/data/data/com.termux/files/usr/bin/sh` 绝对路径。
> `boot.log` 是排错关键：它证明 Termux:Boot 有没有跑、sshd 起没起。

### 3.6 Tailscale

- 旧手机与 PC/新手机登录**同一账号**，允许 VPN；记下旧手机的 `100.x.y.z`。
- 管理后台对该节点 **Disable key expiry**（否则 180 天后静默掉线）。

---

## 4. 五处本地修补（核心内容）

> 这 5 处**不在仓库里**，全部由 `~/bin/fix-dsh-native.py` 幂等管理；每处都有 `.bak` 可回滚。
> 其中 **koffi / require-builtin / flock 是我们为 Termux 自创的最小修复**；**jsonl / fs-local 是照 fork 的 Android 补丁做的等价最小复刻**（fork 的完整补丁系列还含 DSH-Go 专用功能补丁，远端主机不需要）。

### 4.1 koffi：`statx()` 在 bionic 未声明

- **症状**：`npm i -g dsh` 编译 koffi 时报
  `base.cc: cannot initialize a member subobject of type '__u32' with an lvalue of type 'const char *'`。
- **根因**：Termux 的 target API level 下 bionic 只有 `struct statx`，没有 `statx()` 函数声明；C++20 把 `statx(...)` 解析成聚合初始化。
- **做法**：回移 koffi 3.3.0 的上游修法 —— 把 `statx(fd, pathname, ...)` 改成 `syscall(__NR_statx, fd, pathname, ...)`（`base.cc` 已 include `<sys/syscall.h>`）。
- **生效方式**：改源码后必须 `npm rebuild -g ... --allow-scripts=koffi`。
- **何时可以不需要**：koffi ≥ 3.3.0 上游已修。判断：
  ```bash
  grep -c 'syscall(__NR_statx' $PREFIX/lib/node_modules/@deepseek-ai/dsh/node_modules/koffi/lib/native/base/base.cc
  ```

### 4.2 `node-addon-require-builtin`：npm 没有 android-arm64 预编译包

- **症状**：`dsh web` 启动即挂：
  `host preparation failed: No usable native binding found for node-addon-require-builtin-android-arm64`。
- **根因**：`node-addon-require-builtin@0.1.9` 的 optionalDependencies 只有 darwin/linux/win32；loader 还会找 **local-build 路径** `build/napi/napi-v9-android-arm64/require_builtin.node`（它会校验 `product=require-builtin`、`backend=napi`、`abi=napi-v9`）。
- **做法**：从固定源码编一个 napi-v9 绑定放进去（与 fork 给 iOS/OpenHarmony 的做法一致）。
  - 源码：<https://codeload.github.com/deepseek-ai/dsh-node-addon-require-builtin/tar.gz/a58d3599a2e551d7d706d1ff796c9fd4bbaff63c>
    （SHA-256 `286616f15e4f12013988e45ad27a69b4968a9f059c8bd351e412505230577948`，147,144 字节）
  - node-addon-api 头文件 8.9.2（放 `~/narb-build/node_modules/node-addon-api`）
  - 编译宏：`-DNAPI_VERSION=9 -DNARB_BACKEND=1 -DNARB_PRODUCT=1 -DNODE_ADDON_API_DISABLE_CPP_EXCEPTIONS`
  - 输出：`…/node-addon-require-builtin/build/napi/napi-v9-android-arm64/require_builtin.node`
  - 验证：`node -e "console.log(Object.keys(require('<该文件>')))"` → `[ 'requireBuiltin', 'isAllowedInternalId', 'getNativeBindingInfo' ]`
- **不依赖 libnode**：addon 运行时用 `dlsym` 从 Node 可执行文件找内部符号。Termux 的 Node 26.13.1 只导出 8 个必需符号中的 6 个，但**够用**：缺的两个只属于 untagged（Node ≤24）分支和可选快速路径；Node ≥26 走 tagged 分支，有 `SlowGetAlignedPointerFromEmbedderDataEit` 即可。
- **何时可以不需要**：上游若发布 `node-addon-require-builtin-android-arm64` 可选包。

### 4.3 flock：`node-addon-system` 只有 darwin/linux 预编译包

- **症状**：对话"本轮运行失败：`flock is not supported on android-arm64`"。
- **根因**：`@deepseek-ai/node-addon-system@0.1.2` 的 `lib/flock.js` 只允许 `platform` 为 linux/darwin，Android 直接抛 `ERR_FLOCK_UNSUPPORTED_PLATFORM`。
- **做法**（= 照 fork 对 OpenHarmony 的做法）：
  1. 用包自带的 `src/flock.c` 编 android 版：`clang -std=c11 -O2 -fPIC -shared -fvisibility=hidden -DNAPI_VERSION=8 -I$PREFIX/include/node src/flock.c -o ~/lib/system.node`；
  2. 在 `lib/flock.js` 的 `loadBinding()` 里、平台检查**之前**插入：
     ```js
     if (platform === 'android') {
         const require = createRequire(import.meta.url);
         binding = require('/data/data/com.termux/files/home/lib/system.node');
         return binding;
     }
     ```
- **验证**：`node -e "console.log(Object.keys(require(process.env.HOME+'/lib/system.node')))"` → `[ 'tryLock' ]`。

### 4.4 会话持久化 jsonl：`link()` 被 EACCES 拒绝

- **症状**：一轮对话报 `EACCES: permission denied, link '…/session.v4.jsonl.zstd.<tmp>' -> '…/session.v4.jsonl.zstd'`。
- **根因**：Android SELinux 拒绝硬链接（EACCES），而 `@deepseek-ai/dsh-session-persistence-jsonl` 的原子发布只用 `link()` 且不把 EACCES 当"硬链接不可用"处理。
- **做法**：照 fork 的 `jsonl-materialize-rename.diff` 最小复刻 —— `link(tmp, finalPath)` 失败且错误码为 `EACCES`/`EPERM` 时，若目标不存在则改用 `rename(tmp, finalPath)`（保 no-replace 语义）。
- **文件版本对照**：0.2.2-rc.1 原包 `index.js` SHA-256 = `69efef5f84dddf947032bc1425067878fa610416c8885acde2ded9b01230c9b7`；打完本最小补丁 = `c71e6c2a3fcfe684061067f0e53a9ab6171969e16846c7af5dfcd40b5bdffb4f`（fork 完整系列的 after 是 `8066d9ad…`，其中含 DSH-Go 专用补丁，不必追）。

### 4.5 dsh-fs-local：同一硬链接问题的写文件路径

- **症状**：引擎/工具写文件时可能报同样的 EACCES link（会话外）。
- **做法**：照 fork 的 `fs-create-exclusive.diff` + `fs-create-link-denial.diff` 合并最小复刻 —— `createIfAbsent` 的硬链接失败且错误码 ∈ `["EACCES","EPERM","EXDEV","ENOTSUP","EMLINK"]` 时，回退到 `open("wx")` 独占创建 + 写入 + fsync；并同步改错误文案 `temp close failed` → `file close failed`。
- **验证哈希**：0.2.2-rc.1 原包 `index.js` = `d6d3115d4584a236746929d654ede98a0bc365fa4247567ba110971657fd7f90`；只打 fork 的 exclusive 补丁 = `ef9b2078…`（与 `runtime/patches/pins.json` 一致）；再加 EACCES = `2dd32b188b25583b693d0e82968f2be1daee8160528cc7cae9f4764523e87680`。

---

## 5. 日常操作

### 5.1 启动引擎（手机端）

```bash
~/bin/dsh-web.sh          # nohup 后台起，URL 写到 ~/dsh-web.url
cat ~/dsh-web.url         # 查看当前带 token 的 URL
tail -20 ~/dsh-web.log    # 日志
```

- `dsh web` 的 token **每次启动都会变**，且没有固定 token 的参数。
- 同一进程存活期间，浏览器用 URL 登录一次后靠 cookie，不用反复输 token。
- 检查引擎是否活着：
  ```bash
  ps -ef | grep -F 'dsh web' | grep -v grep
  curl -s -o /dev/null -w 'HTTP %{http_code}\n' "http://127.0.0.1:3080/"
  # 401 = 活着（裸访问没带 token）；000 = 没进程在监听
  ```

### 5.2 PC 访问（SSH 隧道）

```powershell
# 终端 A：隧道（保持窗口，关掉即断）
ssh -N -p 8022 -L 3080:127.0.0.1:3080 u0_a45@100.122.251.16

# 终端 B：取当前 URL
ssh -p 8022 u0_a45@100.122.251.16 "cat ~/dsh-web.url"
```

浏览器打开返回的 URL（必须是**最新**的；旧 token 会 401）。

### 5.3 重启后的流程

1. 手机**解锁一次**（Direct Boot 限制）；
2. 等约 1 分钟（Tailscale + sshd 自动恢复，`~/boot.log` 可查）；
3. `~/bin/dsh-web.sh` 起引擎；
4. PC 开隧道 + 用新 URL。
   > 阶段 1 后由新手机 App 的「托管启动」自动完成 3、4 步；第 1、2 步仍然需要。

### 5.4 沙箱不可用 → 切 `danger-full-access`（必读）

Android/Termux 上**没有可用的沙箱后端**：bubblewrap 需要非特权 user namespace（Android 内核通常关闭），Landlock 也不可用。所以引擎默认的 `workspace-write` 模式在 bash 工具上会被拒绝：

```
一个当前限制 刚才尝试执行 date 命令时失败了——这台机器上沙箱后端不可用
（缺 bubblewrap 或合适的内核支持），所以默认模式下无法运行 shell 命令。
```

这不是故障，是真机环境限制（fork 自己的 Ubuntu guest 也一样：`GuestSetup.kt` 的系统提示里就要求模型直接用 `danger-full-access`）。处理：

1. **当前会话**：在聊天输入框发送
   ```
   /permission danger-full-access
   ```
   （底层是 `setPermissionPreset`；之后 bash 工具以 `u0_a45` 身份直接执行，**无沙箱**。）
2. **新会话默认**（推荐设一次）：Web UI → **设置 → 通用（General）→ 新建会话的默认权限** → 选 `danger-full-access`。
3. **验证**：让它执行 `date`，能返回时间即成功。

> 安全含义：`danger-full-access` = 她能以 Termux 用户身份执行任意命令、读写 `~` 下文件。旧手机是自用后端，这是可接受的取舍；但不要把无关的敏感数据放在这台机器上。

---

## 6. 升级 dsh：固定三步

**先记版本**：`dsh --version`；升级 = 换 `@deepseek-ai/dsh@<新版本>`（PLAN 里锁定的是 `0.2.2-rc.1`，非必要不升级）。

```bash
# ① 装新版本，先跳过所有安装脚本（避免 koffi 用未打补丁的源码编译失败）
npm i -g --ignore-scripts @deepseek-ai/dsh@<新版本>

# ② 打本地修补（幂等；会自动重编 flock / narb，必要时补丁 koffi/jsonl/fs-local）
python ~/bin/fix-dsh-native.py

# ③ 用补丁后的源码重跑安装脚本
export npm_config_disturl=https://npmmirror.com/mirrors/node
npm rebuild -g --foreground-scripts \
  --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs
```

### 6.1 看 fix 脚本的输出

| 输出 | 含义 / 动作 |
|---|---|
| `koffi : already patched` | 新版本仍钉 koffi 3.1.x，补丁沿用 |
| `koffi : patched (needs npm rebuild)` | 照第 ③ 步跑 rebuild |
| `flock : system.node compiled` / `flock.js patched` | 正常 |
| `narb : source/node-addon-api missing, skip` | 编译源码被清（升级只会替换 npm 包，`$PREFIX/tmp` 里通常还在）；缺了就重新下载源码 + `node-addon-api@8.9.2`，见附录 A 脚本头部说明 |
| `jsonl : anchor not found` / `fs-local : anchor not found` | **新版本源码变了**，需要按 §4.4/§4.5 的思路重新定位、人工适配（把这两个补丁当"上游若已修就不需要"处理：先判断报错是否还在） |
| 全 already | 无需 rebuild，直接起引擎 |

### 6.2 升级后验收（照 PLAN §4.9 + 阶段 1 的接口）

```bash
dsh --version
~/bin/dsh-web.sh                          # 能打印 URL = 引擎骨架 OK
# PC 隧道 + 浏览器打开 URL
# 1) 能新建会话并收到回复（Key 保留在 ~/.dsh，不用重配）
# 2) 能发 2~3 轮（验证 jsonl / fs-local 补丁仍生效，不报 EACCES link）
# 3) 会话权限是 danger-full-access，让它跑 date 能返回（验证 §5.4 设置仍在）
# 4) 锁屏 30 分钟后 ssh 仍通
```

### 6.3 回滚

```bash
npm i -g --ignore-scripts @deepseek-ai/dsh@0.2.2-rc.1
python ~/bin/fix-dsh-native.py
npm rebuild -g --foreground-scripts --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs
```

（`~/lib/system.node`、`~/narb-build`、`$PREFIX/tmp/dsh-node-addon-require-builtin-*` 不要删，升级/回滚都靠它们省重下载。）

---

## 7. 故障排查对照表（本次真实遇到的）

| 现象 | 归类 | 处理 |
|---|---|---|
| `npm warn install-scripts ... blocked` | npm 11 策略 | 用 `--allow-scripts=...` 或 `npm rebuild -g --allow-scripts=...` 重跑 |
| `Error: CMake does not seem to be available`（koffi） | 缺构建工具 | `pkg install -y cmake` |
| `statx ... __u32 ... const char*`（koffi 编译） | bionic 兼容 | §4.1 补丁 + rebuild |
| `No usable native binding found for node-addon-require-builtin-android-arm64` | 原生缺失 | §4.2 自编 napi 绑定 |
| `flock is not supported on android-arm64` | 原生缺失 | §4.3 自编 + 补 JS |
| `EACCES ... link '.../session.v4.jsonl.zstd...'` | Android 硬链接 | §4.4 补丁 |
| 报 `sandbox backend unavailable` / 提到缺 bubblewrap | Android 无沙箱后端 | 会话发 `/permission danger-full-access`，并把新会话默认权限设为它（§5.4） |
| 浏览器 `127.0.0.1:3080` 连不上 | 隧道没开 | PC 重开 `ssh -N -L 3080:...` |
| 手机 `curl` 得 `HTTP 000` | 引擎没进程 | `~/bin/dsh-web.sh`；看 `~/dsh-web.log` |
| 手机 `curl` 得 `HTTP 401` | 正常 | 裸访问没 token；用带 token 的 URL |
| URL 用旧 token 打不开/401 | token 过期 | `cat ~/dsh-web.url` 用最新的 |
| 重启后 PC 连不上 | 未解锁 / 未起引擎 | 先解锁一次；再起引擎（§5.3） |
| `npm config set disturl` 报 not a valid option | npm 11 | `disturl` 是 node-gyp 的**环境变量**：`export npm_config_disturl=...` |
| `tail -40 ... --host` 报错 | 命令粘连 | 逐条分开执行 |

---

## 8. 已知限制 / 未验证

- **重启需解锁一次**（Direct Boot），解锁后约 60s 恢复 SSH。
- **引擎不自启**：重启后 `dsh web` 是停的（PLAN §4.10 方案 A），阶段 1 由 App「托管启动」拉起；`~/boot.log` 只证明 sshd 起了。
- **`sharp`（图片编解码）未验证**：npm 只发 glibc 预编译，Android 上若加载会失败。纯文字聊天不受影响（懒加载），发图片/附件可能报错。
- **bash 工具没有沙箱**：Android 上 bwrap/Landlock 都不可用，默认 `workspace-write` 会被拒绝；必须用 `danger-full-access`（§5.4）。这意味着命令以 `u0_a45` 身份直接执行，**没有文件系统隔离**。
- **Tailscale 走蜂窝数据**时是 direct（实测 43ms），但流量会产生；长期看需要留意套餐。
- **测 C（锁屏 30 分钟）已过**，但属于单次抽样，不能保证每次都不被华为清后台。

---

## 9. 备份与迁移

需要在 PC 上留备份的（手机丢了/重置后照 §3 重装时用）：

```powershell
mkdir $env:USERPROFILE\phase0-backup
scp -P 8022 u0_a45@100.122.251.16:bin/fix-dsh-native.py  $env:USERPROFILE\phase0-backup\
scp -P 8022 u0_a45@100.122.251.16:bin/dsh-web.sh         $env:USERPROFILE\phase0-backup\
scp -P 8022 u0_a45@100.122.251.16:.termux/boot/server    $env:USERPROFILE\phase0-backup\boot-server.sh
```

（路径相对 `~`；`scp` 端口是大写 `-P`。`~/.dsh` 里有会话/凭据，迁移价值有限，按需自己决定。）

---

## 10. 阶段 1 交接参数

| 字段 | 值 |
|---|---|
| 主机 | `100.122.251.16` |
| 端口 | `8022` |
| 用户名 | `u0_a45` |
| 密码 | 手机上 `passwd` 设的（不写文档） |
| 指纹 | `SHA256:89x1v9sdp+ElADmxMOl1bgIOn6EE7wPZExA9fao3fQI` |
| 实例管理 | 托管启动 |
| 启动命令 | 先默认 `dsh web`；若报 not found 用 `/data/data/com.termux/files/usr/bin/dsh web` |
| 工作目录 | `/data/data/com.termux/files/home/mingyue` |

> **指纹以 `ssh-keygen -lf` 的实测输出为准，不要手抄。** PC 上复核命令：
>
> ```powershell
> ssh-keygen -F "[100.122.251.16]:8022" -f "$env:USERPROFILE\.ssh\known_hosts"
> ```
>
> 2026-11-16 实测三种主机 key 的指纹（known_hosts 权威值）：
>
> | 类型 | 指纹 |
> |---|---|
> | ED25519 | `SHA256:89x1v9sdp+ElADmxMOl1bgIOn6EE7wPZExA9fao3fQI`（App 通常协商这个） |
> | RSA | `SHA256:b0gLcWygg/EJuQxbogbmZiBXSingf+81/4dQ1o63RUI` |
> | ECDSA | `SHA256:l2MkO54uM0Ja+KG88WgtUC84lxzzKxPQv6z8kGmg3Tw` |
>
> 备注：本文早期版本在 §1/§10 两处把 ED25519 指纹漏抄了 `6EE` 三个字符，已按上述实测值更正。

---

## 附录 A：`~/bin/fix-dsh-native.py`

```python
#!/usr/bin/env python
# fix-dsh-native.py - Termux/Android(bionic) 上 dsh 的本地兼容补丁（幂等）
# 用法: python ~/bin/fix-dsh-native.py
# 升级流程: npm i -g --ignore-scripts <dsh@版本> -> 本脚本 -> npm rebuild（见 §6）
#
# narb 编译依赖:
#   $PREFIX/tmp/dsh-node-addon-require-builtin-*/   (源码, commit a58d3599…)
#   ~/narb-build/node_modules/node-addon-api/       (8.9.2)
# 缺失时脚本跳过并在输出里说明；重新准备:
#   cd $PREFIX/tmp && curl -L -o narb.tar.gz "https://codeload.github.com/deepseek-ai/dsh-node-addon-require-builtin/tar.gz/a58d3599a2e551d7d706d1ff796c9fd4bbaff63c" && tar -xzf narb.tar.gz
#   mkdir -p ~/narb-build && cd ~/narb-build && npm init -y && npm i node-addon-api@8.9.2
import glob, io, json, os, re, subprocess

PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
HOME = os.environ.get("HOME", "/data/data/com.termux/files/home")
NM = os.path.join(PREFIX, "lib/node_modules/@deepseek-ai/dsh/node_modules")
NODE_INC = os.path.join(PREFIX, "include/node")
LIBDIR = os.path.join(HOME, "lib")
report = []

def read(p):
    with io.open(p, encoding="utf-8") as f: return f.read()
def write(p, s):
    with io.open(p, "w", encoding="utf-8", newline="") as f: f.write(s)
def first(pat):
    hits = sorted(glob.glob(os.path.join(NM, pat)))
    return hits[0] if hits else None

# 1) koffi: bionic 不声明 statx() -> 回移 koffi 3.3.0 的 syscall 修法
p = first("koffi/lib/native/base/base.cc")
if not p:
    report.append("koffi     : not found, skip")
elif "syscall(__NR_statx" in read(p):
    report.append("koffi     : already patched")
else:
    s = read(p)
    s2 = s.replace("if (statx(fd, pathname, stat_flags, stat_mask, &sxb) < 0)",
                   "if (syscall(__NR_statx, fd, pathname, stat_flags, stat_mask, &sxb) < 0)")
    if s2 == s:
        report.append("koffi     : anchor not found")
    else:
        write(p + ".bak", s); write(p, s2)
        report.append("koffi     : patched (needs npm rebuild)")

# 2) flock: 编 android system.node + 给 flock.js 加 android 分支
fl = first("node-addon-system/lib/flock.js")
if not fl:
    report.append("flock     : not found, skip")
else:
    pkg = os.path.dirname(os.path.dirname(fl))
    src = os.path.join(pkg, "src/flock.c")
    out = os.path.join(LIBDIR, "system.node")
    os.makedirs(LIBDIR, exist_ok=True)
    if not os.path.exists(src):
        report.append("flock     : no src/flock.c, skip compile")
    elif os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
        report.append("flock     : system.node up-to-date")
    else:
        subprocess.run(["clang", "-std=c11", "-O2", "-g0", "-fPIC", "-shared",
                        "-fvisibility=hidden", "-DNAPI_VERSION=8", "-I" + NODE_INC,
                        src, "-Wl,-soname,system.node",
                        "-Wl,-rpath," + os.path.join(PREFIX, "lib"), "-o", out], check=True)
        report.append("flock     : system.node compiled")
    s = read(fl)
    if "platform === 'android'" in s:
        report.append("flock     : flock.js already patched")
    else:
        anchor = "    const { platform, arch } = process;\n"
        if anchor not in s:
            report.append("flock     : flock.js anchor not found")
        else:
            add = anchor + ("    if (platform === 'android') {\n"
                            "        const require = createRequire(import.meta.url);\n"
                            "        binding = require(" + json.dumps(out) + ");\n"
                            "        return binding;\n"
                            "    }\n")
            write(fl + ".bak", s); write(fl, s.replace(anchor, add, 1))
            report.append("flock     : flock.js patched")

# 3) require-builtin: 没有 android 预编译包 -> 从固定源码编 local-build 绑定
narb = first("node-addon-require-builtin/lib/index.js")
if not narb:
    report.append("narb      : not found, skip")
else:
    pkgdir = os.path.dirname(os.path.dirname(narb))
    dst = os.path.join(pkgdir, "build/napi/napi-v9-android-arm64/require_builtin.node")
    api = os.path.join(HOME, "narb-build/node_modules/node-addon-api")
    srcs = sorted(glob.glob(os.path.join(PREFIX, "tmp/dsh-node-addon-require-builtin-*")))
    if os.path.exists(dst):
        report.append("narb      : binding exists")
    elif not srcs or not os.path.isdir(api):
        report.append("narb      : source/node-addon-api missing, skip")
    else:
        native = os.path.join(srcs[0], "packages/native")
        gyp = json.load(open(os.path.join(native, "binding.gyp")))
        t = gyp["targets"][0]
        files = [os.path.join(native, x) for x in t["sources"] + t["conditions"][0][2]["sources"]]
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        subprocess.run(["clang++", "-std=c++17", "-O2", "-fPIC", "-shared", "-pthread",
                        "-fno-exceptions", "-fvisibility=hidden",
                        "-DNAPI_VERSION=9", "-DNARB_BACKEND=1", "-DNARB_PRODUCT=1",
                        "-DNODE_ADDON_API_DISABLE_CPP_EXCEPTIONS",
                        "-DNODE_GYP_MODULE_NAME=require_builtin",
                        "-I" + NODE_INC, "-I" + api, *files, "-ldl",
                        "-Wl,-soname,require_builtin.node",
                        "-Wl,-rpath," + os.path.join(PREFIX, "lib"), "-o", dst], check=True)
        report.append("narb      : require_builtin.node compiled")

# 4) jsonl: link 被 EACCES/EPERM 拒绝时改用 rename（保住 no-replace 语义）
p = first("dsh-session-persistence-jsonl/lib/index.js")
if not p:
    report.append("jsonl     : not found, skip")
else:
    s = read(p)
    if "await rename(tmp, finalPath)" in s:
        report.append("jsonl     : already patched")
    elif "await link(tmp, finalPath);" not in s:
        report.append("jsonl     : anchor not found")
    else:
        m = re.search(r'import \{([^}]*)\} from "node:fs/promises";', s)
        if m:
            names = [x.strip() for x in m.group(1).split(",")]
            if "rename" not in names:
                names.append("rename")
                s = s[:m.start(1)] + ", ".join(names) + s[m.end(1):]
        pat = re.compile(r"([ \t]*)await link\(tmp, finalPath\);")
        def repl(mm):
            ind = mm.group(1); i1 = ind + "\t"; i2 = i1 + "\t"
            return "\n".join([
                ind + "try {",
                i1 + "await link(tmp, finalPath);",
                ind + "} catch (error) {",
                i1 + 'if (error?.code !== "EACCES" && error?.code !== "EPERM") throw error;',
                i1 + "const existing = await lstat(finalPath).catch((statError) => {",
                i2 + 'if (statError?.code !== "ENOENT") throw statError;',
                i1 + "});",
                i1 + "if (existing !== void 0) throw error;",
                i1 + "await rename(tmp, finalPath);",
                ind + "}",
            ])
        s2, n = pat.subn(repl, s, count=1)
        if n != 1:
            report.append("jsonl     : replace failed")
        else:
            write(p + ".bak", read(p)); write(p, s2)
            report.append("jsonl     : patched")

# 5) fs-local: createIfAbsent 硬链接失败回退（含 EACCES）
p = first("dsh-fs-local/lib/index.js")
if not p:
    report.append("fs-local  : not found, skip")
else:
    s = read(p)
    if '["EACCES", "EPERM", "EXDEV", "ENOTSUP", "EMLINK"]' in s:
        report.append("fs-local  : already patched")
    else:
        old = "\n".join([
            "\t\tif (options.createIfAbsent) try {",
            "\t\t\tawait linkFile(tempPath, absolutePath);",
            "\t\t} catch (error) {",
            "\t\t\tawait throwGuardedCreateFailure(error, absolutePath, displayPath, inspectPublicationTarget);",
            "\t\t}",
        ])
        combined = "\n".join([
            "\t\tif (options.createIfAbsent) try {",
            "\t\t\tawait linkFile(tempPath, absolutePath);",
            "\t\t} catch (error) {",
            '\t\t\tif (!(error instanceof Error && "code" in error && typeof error.code === "string" && ["EACCES", "EPERM", "EXDEV", "ENOTSUP", "EMLINK"].includes(error.code))) {',
            "\t\t\t\tawait throwGuardedCreateFailure(error, absolutePath, displayPath, inspectPublicationTarget);",
            "\t\t\t}",
            '\t\t\tthrowIfAborted(signal, "write");',
            '\t\t\thandle = await (internals.openPublicationFile ?? open)(absolutePath, "wx", 384)',
            "\t\t\t\t.catch((openError) => throwGuardedCreateFailure(openError, absolutePath, displayPath, inspectPublicationTarget));",
            "\t\t\ttry {",
            "\t\t\t\tawait handle.chmod(384);",
            '\t\t\t\tawait handle.writeFile(content, { encoding: "utf8", ...signal ? { signal } : {} });',
            "\t\t\t\tawait handle.sync();",
            "\t\t\t\tif (mode !== void 0) await handle.chmod(mode);",
            "\t\t\t\tawait handle.close();",
            "\t\t\t\thandle = void 0;",
            "\t\t\t} catch (writeError) {",
            "\t\t\t\t// Do not unlink by path: another writer may have replaced the file we opened.",
            '\t\t\t\tthrow new FsError(`cannot finish creating "${displayPath}": ${errorMessage(writeError)}; file may be incomplete`, isAbortError(writeError) ? "FS_ABORTED" : "FS_IO_ERROR", { cause: writeError });',
            "\t\t\t}",
            "\t\t}",
        ])
        if old not in s:
            report.append("fs-local  : anchor not found")
        else:
            s = s.replace(old, combined, 1)
            s = s.replace("and temp close failed (${errorMessage(closeError)})",
                          "and file close failed (${errorMessage(closeError)})")
            write(p + ".bak", read(p)); write(p, s)
            report.append("fs-local  : patched")

print("fix-dsh-native result:")
for row in report: print("  " + row)
print()
print("After a dsh upgrade, run:")
print("  npm rebuild -g --foreground-scripts --allow-scripts=@deepseek-ai/dsh-subprocess-local,koffi,node-pty,@google/genai,protobufjs")
```

## 附录 B：`~/bin/dsh-web.sh`

```sh
#!/data/data/com.termux/files/usr/bin/sh
LOG="$HOME/dsh-web.log"
: > "$LOG"
nohup dsh web --host 127.0.0.1 --port 3080 --no-open >>"$LOG" 2>&1 &
i=0
URL=""
while [ "$i" -lt 90 ]; do
  URL=$(sed -n 's#^dsh web: \(http://127\.0\.0\.1:[0-9]*/?token=[A-Za-z0-9_-]*\).*#\1#p' "$LOG" | head -1)
  [ -n "$URL" ] && break
  i=$((i+1)); sleep 1
done
if [ -z "$URL" ]; then echo "启动失败，最后日志："; tail -20 "$LOG"; exit 1; fi
printf '%s\n' "$URL" > "$HOME/dsh-web.url"
echo "已就绪: $URL"
echo "日志: $LOG"
```

## 附录 C：`~/.termux/boot/server`

```sh
#!/data/data/com.termux/files/usr/bin/sh
LOG=/data/data/com.termux/files/home/boot.log
exec >>"$LOG" 2>&1
echo "=== boot $(date) ==="
termux-wake-lock
sshd
echo "sshd exit: $?"
```

## 附录 D：本次验收证据

- `~/boot.log`：`=== boot Mon Nov 16 17:37:16 CST 2026 ===` + `sshd exit: 0`（证明 Termux:Boot 执行、sshd 起成功）。
- 重启+解锁后：tailnet 约 51s 恢复、sshd 约 60s 可达（PC 侧 `BatchMode` 探测）。
- 锁屏 30 分钟后 PC 仍能 SSH。
- 全程蜂窝数据：`tailscale ping` 显示 `direct ... 43ms`。
- `dsh web` 打印 `dsh web: http://127.0.0.1:3080/?token=…`，浏览器能新建会话并收到 DeepSeek 回复（Key 已配在 `~/.dsh`）。
