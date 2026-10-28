---
name: obsidian-review
description: 整理 Obsidian vault —— 執行與每日排程完全相同的流程：掃投放檔（信件／Excel／PPT）、處理待決事項、比對 git 與 GitLab、更新需求筆記與心智圖、寫今日筆記。當使用者說「整理筆記」「跑一次整理」「同步 vault」「看一下 vault」或要求手動執行每日流程時使用。也用於在任何專案「開 GitLab issue／建 issue」（`.ops/gitlab_write.py create`）。
---

# Obsidian vault 整理

vault：`{{VAULT}}`

## 第一步：讀規範，不要憑記憶

**一定先讀這兩份**，它們是權威來源，比你記得的任何事都新：

1. `<vault>/CLAUDE.md` —— vault 的完整工作規範（emoji 分類、專案筆記結構、需求資料模型、來源索引、GitLab 寫入邊界）
2. `<vault>/.ops/daily-review.md` —— 每日流程的逐步指令

**接著照 `daily-review.md` 執行。** 那份是排程與手動共用的唯一流程定義，
不要在這裡複製一份步驟——會漂移。

## 兩種模式

| 情境 | 做法 |
| --- | --- |
| {{OWNER_NAME}} 說「整理筆記」但沒指定範圍 | 走完 `daily-review.md` 的全部步驟 |
| {{OWNER_NAME}} 指定範圍（「只看投放檔」「處理待決事項就好」） | 只跑那幾步，並在回報時說明跳過了什麼 |

## 可用的工具（都在 `<vault>/.ops/`，用 venv 的 python）

```
venv/Scripts/python.exe extract_drops.py        # 掃投放檔（.eml/.msg/docx/xlsx/pptx/html）
venv/Scripts/python.exe gitlab_sync.py          # GitLab 專案／MR／Wiki 同步
venv/Scripts/python.exe gitlab_issues_to_reqs.py # Issues → 需求筆記
venv/Scripts/python.exe issue_commit_match.py   # 為 issue 蒐集 commit 證據
venv/Scripts/python.exe gitlab_write.py comment <project> <iid> <md檔>
venv/Scripts/python.exe gitlab_write.py create <project> <title> <md檔>  # 開新 issue（僅限對話中被要求時）
```

## 回報語言

**一律繁體中文**（技術名詞、路徑、commit hash 保持原文）。

## 兩份平級清單

- `❓ 待決事項.md` — 我不能決定、要 {{OWNER_NAME}} 回答的**問題**
- `🎯 行動建議.md` — 每天整份重寫的**簡報**。{{OWNER_NAME}} 不回覆、我也不自行動手，純情報

流程定義都在 `.ops/daily-review.md`（步驟 1 與 1.5），不要在這裡複製規則。

## 不可違反

- **不刪除、不覆蓋既有筆記**；要移除一律搬 `40-archive/`，**搬完要刪掉留下的空目錄**
- **不用萬用字元批次刪除**（2026-08-19 曾因此誤刪整個專案）
- `{{SOURCE_ROOT}}` 底下**只能讀**
- **關閉 GitLab issue 需要 {{OWNER_NAME}} 當面確認**；留言可自動做；**開新 issue 只在 {{OWNER_NAME}} 明確要求時做**（排程不得開）
- 新建專案**必須有 `## 🧭 來源索引`**，並區分 ①權威／②外部／③推論
- 不確定的事寫進 `<vault>/❓ 待決事項.md`，不要臆測

## 互動模式與排程的差異

手動執行時 **{{OWNER_NAME}} 就在線上**，所以：

- 遇到需要判斷的事**可以直接問他**，不必一律丟進待決事項
- 他明確要求時**可以關閉 issue**（排程不行）
- 他要求開 issue 時用 `gitlab_write.py create`（任何專案都適用，不只在整理 vault 時）；Windows 下執行前設 `PYTHONIOENCODING=utf-8`
- 回報要具體：改了哪幾篇、發現什麼、還有什麼卡住

完成後簡短回報，不要把整個流程覆述一遍。
