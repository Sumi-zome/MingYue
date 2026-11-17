# 溟月 · 状态自检（Windows 版）
#
# ⚠️ 本文件必须保存为 UTF-8 **带 BOM**：Windows PowerShell 5.1 读 .ps1 默认按 GBK，
#    无 BOM 的中文会被解坏、连引号一起吃掉，直接解析失败。用编辑器保存时选 "UTF-8 with BOM"。
#
# 用途：当 PC 作为主机（或本地调试）时，用一条命令看她的服务状态。
# 手机（Termux）上请用 status.sh —— 两边输出结构一致，方便对照。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File status.ps1
#   powershell -ExecutionPolicy Bypass -File status.ps1 -MingyueHome 'D:\restore\mingyue'
#   powershell -ExecutionPolicy Bypass -File status.ps1 -Check      # 额外跑 mem.py check
#
# 只读：不写文件、不改配置、不打印任何 token。

[CmdletBinding()]
param(
    [string]$MingyueHome = (Join-Path $env:USERPROFILE 'mingyue'),
    [switch]$Check
)

$ErrorActionPreference = 'Continue'

function Section($title) { Write-Output ''; Write-Output "== $title ==" }

# ---------- 主机 ----------
Section '主机'
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    Write-Output ("{0} {1} ({2})" -f $os.Caption, $os.Version, $env:PROCESSOR_ARCHITECTURE)
} catch {
    Write-Output ("Windows {0} ({1})" -f [Environment]::OSVersion.Version, $env:PROCESSOR_ARCHITECTURE)
}
Write-Output ("PowerShell {0}" -f $PSVersionTable.PSVersion)

# ---------- sshd（当主机时才需要） ----------
Section 'sshd（入口）'
$sshd = Get-Service sshd -ErrorAction SilentlyContinue
if ($sshd) {
    Write-Output ("服务：{0} / 启动类型：{1}" -f $sshd.Status, $sshd.StartType)
    $listen22 = Get-NetTCPConnection -State Listen -LocalPort 22 -ErrorAction SilentlyContinue
    if ($listen22) { Write-Output '22 端口在监听' } else { Write-Output '22 端口没有监听' }
} else {
    Write-Output '未安装 OpenSSH Server（只作为客户端时不需要）'
}

# ---------- DSH 引擎 ----------
Section 'DSH 引擎'
$procs = @()
$procs += Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.ProcessName -like '*DeepSeek*' }
try {
    $procs += Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'dsh' } |
        ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
} catch { }
$procs = $procs | Where-Object { $_ } | Sort-Object Id -Unique

if (-not $procs) {
    Write-Output '没有找到 DSH 进程（桌面端没开，或引擎在别处）'
} else {
    # Electron 会拉起一堆辅助进程，只凭"有没有监听端口"挑出真正的引擎
    $engines = @()
    foreach ($p in $procs) {
        $listens = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
            Where-Object { $_.OwningProcess -eq $p.Id } |
            Sort-Object LocalPort
        if ($listens) { $engines += [pscustomobject]@{ Proc = $p; Listens = $listens } }
    }
    if (-not $engines) {
        Write-Output ("找到 {0} 个 DSH 进程，但都没有监听端口（可能还在启动）" -f $procs.Count)
    } else {
        foreach ($e in $engines) {
            Write-Output ("引擎：{0} (PID {1})" -f $e.Proc.ProcessName, $e.Proc.Id)
            foreach ($c in $e.Listens) {
                $url = "http://127.0.0.1:$($c.LocalPort)/"
                $code = '000'
                try {
                    $r = Invoke-WebRequest -Uri $url -Method Head -TimeoutSec 4 -UseBasicParsing -ErrorAction Stop
                    $code = [int]$r.StatusCode
                } catch {
                    if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } else { $code = '000' }
                }
                Write-Output ("  监听 {0}:{1} → http:{2}" -f $c.LocalAddress, $c.LocalPort, $code)
            }
        }
    }
}

# ---------- 她的家 ----------
Section '她的家'
if (-not (Test-Path $MingyueHome)) {
    Write-Output ("目录不存在：{0}" -f $MingyueHome)
    Write-Output '（PC 不是主机时正常；恢复备份后用 -MingyueHome 指向解包目录）'
} else {
    $size = (Get-ChildItem $MingyueHome -Recurse -File -ErrorAction SilentlyContinue |
        Measure-Object -Property Length -Sum).Sum
    Write-Output ("{0}  约 {1:N0} KB" -f $MingyueHome, ($size / 1KB))
    $expect = @('memory.db', 'journal.jsonl', 'AGENTS.md', 'manifest.json', 'persona.md', 'rules.md')
    foreach ($name in $expect) {
        $path = Join-Path $MingyueHome $name
        if (Test-Path $path) {
            $item = Get-Item $path
            Write-Output ("  [有] {0}  {1:N0} B  {2}" -f $name, $item.Length, $item.LastWriteTime.ToString('MM-dd HH:mm'))
        } else {
            Write-Output ("  [无] {0}" -f $name)
        }
    }
    foreach ($dir in @('scripts', 'schedules', 'reads', 'daily', 'tmp')) {
        $path = Join-Path $MingyueHome $dir
        if (Test-Path $path) {
            $n = (Get-ChildItem $path -File -ErrorAction SilentlyContinue | Measure-Object).Count
            Write-Output ("  [有] {0}\  {1} 个文件" -f $dir, $n)
        } else {
            Write-Output ("  [无] {0}\" -f $dir)
        }
    }
}

# ---------- 备份 ----------
Section '备份'
$backupDir = Join-Path $env:USERPROFILE 'backups'
if (Test-Path $backupDir) {
    $files = Get-ChildItem $backupDir -Filter 'mingyue-*.age' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 3
    if ($files) {
        foreach ($f in $files) {
            Write-Output ("  {0}  {1:N1} KB  {2}" -f $f.Name, ($f.Length / 1KB), $f.LastWriteTime.ToString('MM-dd HH:mm'))
        }
    } else { Write-Output '  还没有备份包' }
} else {
    Write-Output '  没有 backups 目录（备份默认跑在主机上，产物在主机 ~/backups）'
}

# ---------- Tailscale（有就报） ----------
Section 'Tailscale'
$ts = Get-Command tailscale -ErrorAction SilentlyContinue
if (-not $ts) {
    $candidate = 'C:\Program Files\Tailscale\tailscale.exe'
    if (Test-Path $candidate) { $ts = Get-Item $candidate }
}
if ($ts) {
    try {
        $status = & $ts.Source status --peers=false 2>&1 | Select-Object -First 3
        $status | ForEach-Object { Write-Output ("  " + $_) }
    } catch {
        Write-Output '  tailscale 存在但查询失败（可能未登录）'
    }
} else {
    Write-Output '  未安装 Tailscale（只做本机调试时不需要）'
}

# ---------- 可选自检 ----------
if ($Check) {
    Section 'mem.py check'
    $py = Get-Command py -ErrorAction SilentlyContinue
    $python = if ($py) { 'py' } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
    $mem = Join-Path $MingyueHome 'scripts\mem.py'
    if (-not $python) {
        Write-Output '  没有找到 Python（安装后可用 -Check）'
    } elseif (-not (Test-Path $mem)) {
        Write-Output ("  找不到 {0}" -f $mem)
    } else {
        $pyArgs = @()
        if ($python -eq 'py') { $pyArgs += '-3' }
        $pyArgs += @($mem, 'check')
        & $python @pyArgs
    }
}

Write-Output ''
