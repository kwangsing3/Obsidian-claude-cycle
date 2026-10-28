# Obsidian vault 每日整理 — 由 Windows 工作排程器呼叫（每天 21:00）
$ErrorActionPreference = "Continue"

# --- 強制全鏈路 UTF-8，否則中文輸出會被 cp950 打成問號 ---
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING     = "utf-8"

$Ops   = $PSScriptRoot
$Vault = Split-Path $Ops -Parent
$Cfg   = Get-Content (Join-Path $Ops "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
$Log   = Join-Path $Ops ("logs\" + (Get-Date -Format "yyyy-MM-dd_HHmm") + ".log")

Set-Location $Vault
$prompt = Get-Content (Join-Path $Ops "daily-review.md") -Raw -Encoding UTF8

"=== 每日整理開始 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $Log -Encoding utf8

# 允許：檔案工具 + 整個 git（含 git -C）+ python(venv) + 常用唯讀 shell + 搬移/建目錄
# 拒絕優先於允許，危險動作在下面 disallowedTools 一律封死
$allow = @(
    "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite",
    "Bash(git:*)",
    "Bash(python:*)", "Bash(.ops/venv/Scripts/python.exe:*)",
    "Bash(powershell.exe -NoProfile -Command $f = Join-Path:*)",
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)",
    "Bash(wc:*)", "Bash(find:*)", "Bash(mkdir:*)", "Bash(mv:*)", "Bash(cp:*)",
    "Bash(base64:*)", "Bash(certutil:*)", "Bash(iconv:*)"
)
# 破壞性或會對外送資料的動作，一律封死
$deny = @(
    # 關閉 issue 需 --allow-close，排程一律封死
    "Bash(*gitlab_write.py close*)",
    # 開新 issue 只在使用者於對話中要求時做，排程一律封死
    "Bash(*gitlab_write.py create*)",
    "Bash(rm:*)", "Bash(rmdir:*)", "Bash(del:*)",
    "Bash(git push:*)", "Bash(git commit:*)", "Bash(git reset:*)",
    "Bash(git checkout:*)", "Bash(git clean:*)", "Bash(git rebase:*)",
    "Bash(curl:*)", "Bash(wget:*)", "Bash(ssh:*)", "Bash(scp:*)",
    "WebFetch", "WebSearch"
)

$prompt | claude --print `
    --permission-mode acceptEdits `
    --allowedTools $allow `
    --disallowedTools $deny `
    --add-dir $Cfg.source_root `
    2>&1 | Out-File $Log -Append -Encoding utf8

"=== 結束 $(Get-Date -Format 'HH:mm:ss') ===" | Out-File $Log -Append -Encoding utf8

# --- 收尾清理：agent 的 disallowedTools 封了 rm，改由本腳本代勞 ---
# （{{OWNER_NAME}} 2026-08-31 Q41：執行權已通，卡的是刪除；不放寬 agent 權限，改在這裡收尾）
$Drops = Join-Path $Ops "drops"
if (Test-Path $Drops) {
    Get-ChildItem $Drops -File -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    "已清除 .ops/drops/ 的暫存抽取檔" | Out-File $Log -Append -Encoding utf8
}
# 搬去封存後留下的空資料夾
foreach ($base in @("10-projects", "70-maps")) {
    $root = Join-Path $Vault $base
    if (-not (Test-Path $root)) { continue }
    Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
        if (-not (Get-ChildItem $_.FullName -Force -ErrorAction SilentlyContinue)) {
            Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
            "已刪除空資料夾 $base/$($_.Name)" | Out-File $Log -Append -Encoding utf8
        }
    }
}

Get-ChildItem (Join-Path $Ops "logs") -Filter *.log |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 30 | Remove-Item -Force
