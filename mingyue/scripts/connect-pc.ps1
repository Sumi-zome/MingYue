# 溟月 · 电脑连接脚本：自动读取引擎端口与 token，建立 SSH 隧道并打开浏览器。
#
# 用法（在 PowerShell 里）：
#   .\mingyue\scripts\connect-pc.ps1            # 连接（默认本地端口 3099）
#   .\mingyue\scripts\connect-pc.ps1 -LocalPort 3100
#   .\mingyue\scripts\connect-pc.ps1 -Stop      # 关掉隧道
#
# 前提：App 连过主机（引擎在跑），否则 web.log 里没有启动行。

param(
  [int]$LocalPort = 3099,
  [switch]$Stop
)

$ErrorActionPreference = 'Continue'
$HostAlias = 'mingyue'

function Stop-Tunnels {
  $procs = Get-CimInstance Win32_Process -Filter "Name = 'ssh.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*-L $LocalPort*" }
  if (-not $procs) { Write-Host '没有找到正在用的隧道。'; return }
  foreach ($p in $procs) {
    Write-Host "结束隧道进程 PID $($p.ProcessId)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
  }
}

if ($Stop) {
  Stop-Tunnels
  Write-Host '已停止。浏览器里的页面会失联，重新运行本脚本即可再连。'
  exit 0
}

# 1. 读取启动行里的端口与 token
Write-Host '[1/3] 读取引擎端口与 token…'
$line = ssh $HostAlias "grep -o 'http://127\.0\.0\.1:[0-9]*/?token=[A-Za-z0-9_-]*' ~/.dsh-app-remote/web.log | tail -1" 2>$null
if (-not $line) {
  Write-Host '没读到启动行。可能原因：引擎没在跑（先开 App 连一次），或 ssh 别名不对。' -ForegroundColor Red
  exit 1
}
if ($line -notmatch '127\.0\.0\.1:(\d+)/\?token=([A-Za-z0-9_-]+)') {
  Write-Host "启动行解析失败：$line" -ForegroundColor Red
  exit 1
}
$RemotePort = $Matches[1]
$Token = $Matches[2]
Write-Host "      主机端口 $RemotePort"

# 2. 端口占用检查 + 建立隧道
$busy = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
if ($busy) {
  Write-Host "[2/3] 本地端口 $LocalPort 已被占用，先清理旧的隧道…"
  Stop-Tunnels
  Start-Sleep -Milliseconds 500
} else {
  Write-Host "[2/3] 建立隧道 127.0.0.1:$LocalPort -> 主机 127.0.0.1:$RemotePort"
}

Write-Host '[2/3] 建立隧道…'
$tunnel = Start-Process -FilePath 'ssh' `
  -ArgumentList @('-N', '-o', 'BatchMode=yes', '-o', 'ExitOnForwardFailure=yes',
                  '-o', 'ServerAliveInterval=30', '-L', "${LocalPort}:127.0.0.1:$RemotePort", $HostAlias) `
  -WindowStyle Hidden -PassThru
if (-not $tunnel) {
  Write-Host '无法启动 ssh 进程' -ForegroundColor Red
  exit 1
}
Write-Host "      ssh PID $($tunnel.Id)，等待端口就绪…"

# 轮询本地端口（最多约 10 秒）
$ready = $false
for ($i = 0; $i -lt 25; $i++) {
  if ($tunnel.HasExited) { break }
  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $client.Connect('127.0.0.1', $LocalPort)
    $client.Close()
    $ready = $true
    break
  } catch {
    Start-Sleep -Milliseconds 400
  }
}

if (-not $ready) {
  if ($tunnel.HasExited) { Write-Host "ssh 已退出（ExitCode $($tunnel.ExitCode)）" -ForegroundColor Red }
  else { Write-Host '端口 10 秒内没起来' -ForegroundColor Red }
  try { if (-not $tunnel.HasExited) { $tunnel.Kill() } } catch {}
  Write-Host '可能原因：主机引擎没在跑 / 端口变了 / ssh 别名配置不对'
  exit 1
}
Write-Host '      隧道已就绪'

# 3. 打开浏览器
$url = "http://127.0.0.1:$LocalPort/?token=$Token"
Write-Host '[3/3] 打开浏览器…'
Write-Host ''
Write-Host '地址（浏览器没自动弹就手动粘贴这个）：'
Write-Host "  $url" -ForegroundColor Cyan
try {
  Start-Process $url
  Write-Host '已尝试打开默认浏览器。'
} catch {
  Write-Host '自动打开失败，请手动粘贴上面的地址。'
}

Write-Host ''
Write-Host '注意：' -ForegroundColor Green
Write-Host '  · 引擎每次重启端口和 token 都会变，重新跑一次本脚本即可'
Write-Host "  · 用完执行 .\mingyue\scripts\connect-pc.ps1 -Stop 关掉隧道"
