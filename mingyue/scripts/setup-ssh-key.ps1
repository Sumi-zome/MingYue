# 溟月 · SSH 密钥配置：配好之后连主机不再需要密码。
#
# 用法（PowerShell）：
#   .\mingyue\scripts\setup-ssh-key.ps1
#
# 全程只需要输一次密码（用来把公钥装到主机上）。

param(
  [string]$HostAlias = 'mingyue'
)

$ErrorActionPreference = 'Stop'

# 1. 本地密钥
$sshDir = Join-Path $env:USERPROFILE '.ssh'
if (-not (Test-Path $sshDir)) { New-Item -ItemType Directory -Path $sshDir | Out-Null }
$keyPath = Join-Path $sshDir 'id_ed25519'

if (Test-Path $keyPath) {
  Write-Host "[1/3] 已有密钥：$keyPath"
} else {
  Write-Host "[1/3] 生成新密钥（无口令）…"
  ssh-keygen -t ed25519 -f $keyPath -N '""' | Out-Null
  if (-not (Test-Path $keyPath)) { throw '生成密钥失败' }
  Write-Host "      $keyPath"
}

$pubPath = "$keyPath.pub"
if (-not (Test-Path $pubPath)) { throw "找不到公钥 $pubPath" }
$pub = (Get-Content $pubPath -Raw).Trim()

# 2. 装到主机（这一步要输一次密码）
Write-Host '[2/3] 把公钥装到主机…'
Write-Host '      会要你输一次密码（输入时不显示，正常）' -ForegroundColor DarkGray
$pub | ssh $HostAlias "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
if ($LASTEXITCODE -ne 0) { throw "装公钥失败（密码错或主机没连上）" }

# 3. 验证：不带密码能连上吗
Write-Host '[3/3] 验证免密登录…'
$probe = ssh -o BatchMode=yes -o ConnectTimeout=8 $HostAlias 'echo MINGYUE-KEY-OK' 2>&1
if ($probe -match 'MINGYUE-KEY-OK') {
  Write-Host ''
  Write-Host '好了！以后连接、scp 都不用再输密码。' -ForegroundColor Green
  Write-Host '现在跑： .\mingyue\scripts\connect-pc.ps1'
} else {
  Write-Host ''
  Write-Host '免密还没生效，输出如下：' -ForegroundColor Yellow
  Write-Host $probe
  Write-Host '可能原因：主机 sshd 关了 PubkeyAuthentication，或 ~/.ssh 权限不对。'
  exit 1
}
