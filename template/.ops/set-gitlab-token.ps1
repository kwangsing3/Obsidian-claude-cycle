# 把 GitLab token 以 Windows DPAPI 加密存到家目錄（不在 OneDrive 同步範圍內）
# 用法：直接執行本檔，依提示貼上 token
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$dest = Join-Path $env:USERPROFILE ".gitlab_token"

Write-Host ""
Write-Host "請貼上 GitLab fine-grained token（輸入時畫面不會顯示任何字元，貼完按 Enter）"
$secure = Read-Host -AsSecureString

if ($null -eq $secure -or $secure.Length -eq 0) {
    Write-Host "沒有輸入任何內容，已取消。" -ForegroundColor Yellow
    exit 1
}

# ConvertFrom-SecureString 不帶 -Key 時走 DPAPI，只有目前 Windows 帳號在本機解得開
ConvertFrom-SecureString -SecureString $secure | Set-Content -Path $dest -Encoding ASCII -NoNewline

# 收緊檔案權限：只有自己可讀寫，移除繼承來的其他帳號
icacls $dest /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null

# 驗證能解回來，並確認長度與前綴合理（不顯示 token 內容）
$back = (Get-Content $dest -Raw).Trim() | ConvertTo-SecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($back)
$plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

Write-Host ""
Write-Host "已儲存：$dest"
Write-Host ("長度 {0} 字元，開頭 {1}…（僅顯示前 8 碼供你確認沒貼錯）" -f $plain.Length, $plain.Substring(0, [Math]::Min(8, $plain.Length)))
if ($plain -notmatch '^glpat-') {
    Write-Host "警告：開頭不是 glpat-，請確認貼到的是 GitLab token。" -ForegroundColor Yellow
}
$plain = $null
Write-Host "解密驗證通過。" -ForegroundColor Green
