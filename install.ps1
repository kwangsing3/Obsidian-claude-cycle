<#
.SYNOPSIS
    把 Obsidian-claude-cycle 框架安裝到你的 vault。

.DESCRIPTION
    只補檔、不覆寫：目的地已存在的檔案一律跳過並列出來，
    所以對已經在用的 vault 重跑也不會弄丟任何筆記。

.EXAMPLE
    .\install.ps1 -DryRun     # 先看會做什麼，不動檔案
    .\install.ps1
    .\install.ps1 -RegisterTask
#>
[CmdletBinding()]
param(
    [string] $ConfigPath = "$PSScriptRoot\config.json",
    [switch] $DryRun,
    [switch] $RegisterTask
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Say($msg, $color = "Gray") { Write-Host $msg -ForegroundColor $color }

# ---------- 1. 讀設定 ----------
if (-not (Test-Path $ConfigPath)) {
    Say "找不到 $ConfigPath" Red
    Say "請先複製 config.example.json 成 config.json 並填入你的路徑。" Yellow
    exit 1
}
$cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json

foreach ($k in @("vault", "source_root")) {
    if (-not $cfg.$k) { Say "config.json 缺少必填欄位：$k" Red; exit 1 }
}
$Vault = $cfg.vault -replace "/", "\"
$Vault = $Vault.TrimEnd("\")

if (-not (Test-Path $Vault)) {
    if ($DryRun) { Say "（試跑）會建立 vault 目錄：$Vault" Cyan }
    else { New-Item -ItemType Directory -Path $Vault -Force | Out-Null; Say "已建立 vault 目錄：$Vault" Green }
}
if (-not (Test-Path $cfg.source_root)) {
    Say "警告：source_root 不存在 —— $($cfg.source_root)" Yellow
}

$Tpl = Join-Path $PSScriptRoot "template"
if (-not (Test-Path $Tpl)) { Say "找不到 template\ 目錄，repo 不完整。" Red; exit 1 }

# ---------- 2. 佔位符 ----------
$subs = @{
    "{{VAULT}}"        = $Vault
    "{{SOURCE_ROOT}}"  = ($cfg.source_root -replace "\\", "/")
    "{{GITLAB_GROUP}}" = [string]$cfg.gitlab_group
    "{{GITHUB_OWNER}}" = [string]$cfg.github_owner
    "{{OWNER_NAME}}"   = $(if ($cfg.owner_name) { $cfg.owner_name } else { "使用者" })
}
$textExt = @(".md", ".base", ".ps1", ".py", ".json", ".txt", ".canvas")

# ---------- 3. 複製（不覆寫）----------
$created = New-Object System.Collections.Generic.List[string]
$skipped = New-Object System.Collections.Generic.List[string]

Get-ChildItem $Tpl -Recurse -File -Force | ForEach-Object {
    $rel = $_.FullName.Substring($Tpl.Length).TrimStart("\")
    $dst = Join-Path $Vault $rel

    if (Test-Path $dst) { $skipped.Add($rel); return }

    $dstDir = Split-Path $dst -Parent
    if (-not (Test-Path $dstDir)) {
        if (-not $DryRun) { New-Item -ItemType Directory -Path $dstDir -Force | Out-Null }
    }

    if ($DryRun) { $created.Add($rel); return }

    if ($textExt -contains $_.Extension.ToLower()) {
        # .ps1 含中文必須保留 UTF-8 BOM，否則排程用的 powershell 5.1 會以 cp950 解讀
        $hasBom = $_.Extension -ieq ".ps1"
        $enc = New-Object System.Text.UTF8Encoding($hasBom)
        $text = [System.IO.File]::ReadAllText($_.FullName, $enc)
        foreach ($k in $subs.Keys) { $text = $text.Replace($k, $subs[$k]) }
        [System.IO.File]::WriteAllText($dst, $text, $enc)
    } else {
        Copy-Item $_.FullName $dst
    }
    $created.Add($rel)
}

# ---------- 4. 把 config 放進 vault 的 .ops\ ----------
$opsCfg = Join-Path $Vault ".ops\config.json"
if ($DryRun) {
    Say "（試跑）會寫入 $opsCfg" Cyan
} else {
    $cfg | ConvertTo-Json -Depth 5 | Set-Content $opsCfg -Encoding UTF8
    Say "已寫入 $opsCfg" Green
}

# ---------- 5. 安裝 skill ----------
$skillSrc = Join-Path $PSScriptRoot "skills\obsidian-review"
$skillDst = Join-Path $env:USERPROFILE ".claude\skills\obsidian-review"
if (Test-Path $skillSrc) {
    if ($DryRun) {
        Say "（試跑）會安裝 skill 到 $skillDst" Cyan
    } elseif (Test-Path (Join-Path $skillDst "SKILL.md")) {
        Say "skill 已存在，跳過：$skillDst" DarkGray
    } else {
        New-Item -ItemType Directory -Path $skillDst -Force | Out-Null
        Get-ChildItem $skillSrc -Recurse -File | ForEach-Object {
            $srel = $_.FullName.Substring($skillSrc.Length).TrimStart([char]92)
            $sdst = Join-Path $skillDst $srel
            $sdir = Split-Path $sdst -Parent
            if (-not (Test-Path $sdir)) { New-Item -ItemType Directory -Path $sdir -Force | Out-Null }
            if ($textExt -contains $_.Extension.ToLower()) {
                $enc  = New-Object System.Text.UTF8Encoding($false)
                $text = [System.IO.File]::ReadAllText($_.FullName, $enc)
                foreach ($k in $subs.Keys) { $text = $text.Replace($k, $subs[$k]) }
                [System.IO.File]::WriteAllText($sdst, $text, $enc)
            } else { Copy-Item $_.FullName $sdst -Force }
        }
        Say "已安裝 skill：$skillDst" Green
    }
}

# ---------- 6. 報告 ----------
Say ""
Say ("=" * 56)
Say ("新增 {0} 個檔案，跳過 {1} 個（已存在，未動）" -f $created.Count, $skipped.Count) White
if ($skipped.Count -gt 0) {
    Say "跳過的檔案：" DarkGray
    $skipped | Sort-Object | ForEach-Object { Say "  - $_" DarkGray }
}
Say ("=" * 56)

# ---------- 7. 排程 ----------
if ($RegisterTask) {
    $ps1  = Join-Path $Vault ".ops\daily-review.ps1"
    $time = $(if ($cfg.schedule_time) { $cfg.schedule_time } else { "21:00" })
    $name = "Obsidian 每日筆記整理"
    if ($DryRun) {
        Say "（試跑）會註冊排程「$name」每天 $time 執行 $ps1" Cyan
    } else {
        $action  = New-ScheduledTaskAction -Execute "powershell.exe" `
                   -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ps1`""
        $trigger = New-ScheduledTaskTrigger -Daily -At $time
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
            -Description "每天用 Claude Code 整理 Obsidian vault" -Force | Out-Null
        Say "已註冊排程「$name」，每天 $time。" Green
    }
}

Say ""
Say "接下來：" White
Say "  1. 用 Obsidian 開啟 $Vault" 
Say "  2. 啟用核心外掛 Canvas 與 Bases"
Say "  3. 要接 GitLab 的話，執行 .ops\set-gitlab-token.ps1 存入 token"
Say "  4. 在 vault 目錄下跑 claude，它會讀 CLAUDE.md"
