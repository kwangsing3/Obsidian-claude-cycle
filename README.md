# Obsidian × Claude Code 專案知識庫框架

把散在硬碟裡的程式專案，變成一座**每天自己長大**的 Obsidian 知識庫。

Claude Code 每天固定時間讀你的本機 repo 與 GitLab，更新專案筆記、
心智圖與需求清單，並產出一份當日的行動建議——你早上打開 Obsidian 就看得到。

> 這是**框架**，不含任何筆記內容。所有筆記都留在你自己的 vault 裡，不進版控。

---

## 它會做什麼

| 用途 | 看哪裡 |
| --- | --- |
| 工作中要查某個系統怎麼接的 | 專案筆記的 `🏗 arch` 心智圖 |
| 工作外想回顧專案在幹嘛 | 專案筆記正文（中文、有來源索引） |
| 想知道還欠什麼 | `99-bases/requirements.base` 彙整的需求筆記 |
| 想知道今天該動哪件事 | `🎯 行動建議.md`（每天整份重寫，像一份內部新聞） |
| 有東西要問你本人 | `❓ 待決事項.md`（答完就刪） |

每個專案固定三張 Canvas 心智圖：`🏗 arch`（系統結構）、`📋 req`（需求與
🤖 AI 建議分支）、`🔗 rel`（跨專案關聯）。

---

## 安裝

需要：Windows、[Obsidian](https://obsidian.md)（啟用 Canvas 與 Bases 核心外掛）、
[Claude Code](https://claude.com/claude-code)、Python 3.10+。

```powershell
git clone https://github.com/kwangsing3/Obsidian-claude-cycle.git
cd Obsidian-claude-cycle

Copy-Item config.example.json config.json
notepad config.json          # 填你的 vault 路徑與原始碼路徑

.\install.ps1 -DryRun        # 先看會做什麼
.\install.ps1                # 實際安裝
.\install.ps1 -RegisterTask  # 順便註冊每日排程
```

`install.ps1` **只補檔、不覆寫**：目的地已存在的檔案會跳過並列在報告裡，
所以對已經在用的 vault 重跑也不會弄丟筆記。

### config.json

| 欄位 | 說明 |
| --- | --- |
| `vault` | Obsidian vault 的絕對路徑（可以放在 OneDrive 裡） |
| `source_root` | 你本機放所有程式專案的母目錄，**全程唯讀** |
| `gitlab_group` | 要同步的 GitLab 群組；不用就留空 |
| `github_owner` | 你的 GitHub 帳號，用來判斷哪些 repo 是你自己的 |
| `owner_name` | 筆記 `owner:` 欄位要填的名字 |
| `container_dirs` | 「只是裝其他 repo 的資料夾」，不當成專案 |
| `schedule_time` | 每日排程時間，預設 `21:00` |

### GitLab（選用）

```powershell
.\template\.ops\set-gitlab-token.ps1   # 安裝後在 vault 的 .ops\ 下執行
```

Token 用 DPAPI 加密存在 `%USERPROFILE%\.gitlab_token`，**不放在 vault 裡**，
也不會出現在任何輸出。建議開 fine-grained PAT，只給
Group / Project / Work Item / Merge Request / Commit / Wiki 的 **Read**，
要讓它在 issue 留言再加 `Note: Create`。

---

## 目錄

```
template/              → 安裝時複製進 vault
  CLAUDE.md            規範本體：命名、emoji、資料模型、安全守則
  home.md              入口
  .ops/                自動化腳本
    daily-review.md    每日流程的提示詞（整套行為都定義在這）
    daily-review.ps1   排程進入點，鎖好權限後呼叫 claude --print
    config.json        由 install.ps1 產生
    vaultconfig.py     所有腳本共用的設定讀取
    gitlab_sync.py     抓 Issues / MR / Wiki / 里程碑
    gitlab_fetch.py    抓單一專案的完整素材
    gitlab_issues_to_reqs.py  Issue → 需求筆記
    issue_commit_match.py     幫 Issue 找「可能解決它的 commit」
    gitlab_write.py    回寫（留言預設開放，關閉 issue 需 --allow-close）
    extract_drops.py   .eml/.msg/docx/xlsx/pptx/html → 純文字
  90-templates/        筆記範本
  99-bases/            Bases 檢視
  00-inbox/ … 80-attachments/   空骨架
skills/obsidian-review/  Claude Code skill
install.ps1
config.example.json
```

---

## 安全邊界

這套東西每天無人看管地跑，所以邊界寫死在腳本裡，不靠提示詞自律：

- **不刪筆記。** 要移除一律搬到 `40-archive/`；排程的 agent 連 `rm` 都被
  `disallowedTools` 封死，少數必要的清理由 `daily-review.ps1` 自己收尾。
- **`source_root` 唯讀。** 那是你的原始碼，只讀不寫。
- **不對外送資料。** `curl`／`wget`／`WebFetch`／`WebSearch` 全封，
  `git push`／`git commit` 也封。
- **寫入 GitLab 分兩級。** 留言可自動；關閉 issue、改標題／標籤／指派
  必須由你確認，排程永遠不會帶 `--allow-close`。
- **不確定就問。** 寫進 `❓ 待決事項.md`，不臆測。

### 你自己的筆記不會上傳

`.gitignore` 把 `/10-projects/`、`/50-daily/`、`/60-meetings/` 等內容資料夾
以及 `.ops/logs`、`.ops/drops` 全部擋掉。就算你把 vault 本身變成 git repo，
筆記也不會被 commit 出去。**不過還是建議：放筆記的 vault 不要設任何 remote。**

---

## 踩過的坑

- 含中文的 `.ps1` 一定要存成 **UTF-8 with BOM**，排程用的 `powershell.exe`
  5.1 會以 cp950 解讀無 BOM 的檔案，直接語法錯誤。
- PowerShell 接 headless 輸出要**強制 UTF-8**（`[Console]::OutputEncoding`），
  否則中文會被 cp950 打成問號且不可逆。
- `allowedTools` 是**指令字串前綴比對**，不是語意比對：
  `Bash(git log:*)` 管不到 `git -C <path> log`。

---

## 授權

MIT
