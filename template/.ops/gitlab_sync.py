# -*- coding: utf-8 -*-
"""從 GitLab 讀取本機 clone 拿不到的東西（Issues / MR / Wiki / 里程碑），
輸出成 .ops/drops/gitlab-<日期>.md 供 Claude 閱讀。

安全設計：
  - 只讀 token、不輸出 token；token 由 DPAPI 加密存在家目錄，不在 vault 內
  - 網域寫死 gitlab.com，只發 GET
  - 權限不足時降級並明確標示缺哪一項，不中斷
"""
import os, io, re, sys, json, ssl, datetime, subprocess, urllib.parse
import urllib.request as ureq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vaultconfig import CFG

API = CFG["gitlab_api"]
VAULT = CFG["vault"]
OUT_DIR = os.path.join(VAULT, ".ops", "drops")
GROUP = CFG["gitlab_group"]
SINCE_DAYS = CFG["since_days"]

def get_token():
    ps = ('$f = Join-Path $env:USERPROFILE ".gitlab_token"; '
          '$s = (Get-Content $f -Raw).Trim() | ConvertTo-SecureString; '
          '$b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s); '
          '[Runtime.InteropServices.Marshal]::PtrToStringBSTR($b)')
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=60)
    tok = (r.stdout or "").strip()
    if not tok.startswith("glpat-"):
        sys.exit("無法取得 token（%s）。請先執行 .ops/set-gitlab-token.ps1" % (r.stderr or "")[:200])
    return tok

TOKEN = None

class ApiError(str):
    """錯誤字串，另外帶結構化資訊。
    繼承 str 是為了讓既有的 `in` 比對與 print 都不用改。

    .kind        auth      認證失效（token 過期／被撤／無效）—— 換 token 才會好
                 permission 權限不足 —— 補勾該項權限才會好
                 notfound  404
                 other     其他（網路、逾時、伺服器錯誤）
    .status      HTTP 狀態碼（取不到為 None）
    .permission  GitLab 指名缺的權限（例 'Group: Read'），沒有則 None
    .raw         API 回傳的原始訊息
    """
    def __new__(cls, text, kind="other", status=None, permission=None, raw=""):
        o = super().__new__(cls, text)
        o.kind, o.status, o.permission, o.raw = kind, status, permission, raw
        return o


AUTH_HINTS = ("token is expired", "invalid_token", "revoked", "unauthorized",
              "invalid token", "token is invalid")


def api(endpoint, **params):
    """回傳 (資料, ApiError)。成功時錯誤為 None。"""
    url = API + "/" + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = ureq.Request(url, headers={"PRIVATE-TOKEN": TOKEN, "User-Agent": "obsidian-vault-sync"})
    try:
        with ureq.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as e:
        status = getattr(e, "code", None)
        body = ""
        if hasattr(e, "read"):
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
        msg = body
        try:
            j = json.loads(body)
            msg = j.get("error_description") or j.get("message") or j.get("error") or body
        except Exception:
            pass
        msg = (msg or str(e)).strip()

        low = msg.lower()
        if status == 401 or any(h in low for h in AUTH_HINTS):
            return None, ApiError("認證失效：%s" % msg[:160], kind="auth",
                                  status=status, raw=msg)

        m = re.search(r"\[(.*?)\]", msg)
        if m and status == 403:
            return None, ApiError("缺權限 %s" % m.group(1), kind="permission",
                                  status=status, permission=m.group(1), raw=msg)

        if status == 404:
            return None, ApiError("404 找不到：%s" % msg[:120], kind="notfound",
                                  status=status, raw=msg)

        return None, ApiError("HTTP %s：%s" % (status or "?", msg[:160]),
                              kind="other", status=status, raw=msg)


def projects_from_notes():
    """Group: Read 缺席時的退路——從專案筆記的 git-remote 欄位取出清單。"""
    out = []
    pd = os.path.join(VAULT, "10-projects")
    if not os.path.isdir(pd):
        return out
    for folder in sorted(os.listdir(pd)):
        f = os.path.join(pd, folder, folder + ".md")
        if not os.path.exists(f):
            continue
        s = io.open(f, encoding="utf-8").read(4000)
        m = re.search(r"^git-remote: (https://gitlab\.com/(\S+?))(?:\.git)?\s*$", s, re.M)
        if m:
            out.append({"path_with_namespace": m.group(2), "_from_notes": True})
    return out

def short(t, n=90):
    t = (t or "").replace("\n", " ").strip()
    return t if len(t) <= n else t[:n] + "…"

def main():
    global TOKEN
    TOKEN = get_token()
    os.makedirs(OUT_DIR, exist_ok=True)
    today = datetime.date.today()
    since = (datetime.datetime.now() - datetime.timedelta(days=SINCE_DAYS)).strftime("%Y-%m-%dT00:00:00Z")

    L = ["# GitLab 同步 %s" % today.isoformat(), "",
         "來源：`gitlab.com/%s`（唯讀）｜近期範圍：%d 天" % (GROUP, SINCE_DAYS), ""]
    gaps = []

    # ── 先確認 token 還能用。認證失效就直接中止，不要產出一堆假的零 ──
    _, autherr = api("groups/%s" % GROUP)
    if autherr is not None and autherr.kind == "auth":
        L += ["> [!failure] Token 認證失效，本次同步整段未執行",
              "> GitLab 回應：`%s`" % autherr.raw,
              "> HTTP 狀態：%s" % (autherr.status or "?"),
              ">",
              "> **這不是權限不足，是整組 token 無效**（過期／被撤銷）。",
              "> 補勾權限沒有用，必須重新產一組並執行 `.ops/set-gitlab-token.ps1`。",
              "",
              "本檔沒有任何專案資料——**不要把它讀成「遠端無變化」**。"]
        out = os.path.join(OUT_DIR, "gitlab-%s.md" % today.isoformat())
        io.open(out, "w", encoding="utf-8").write(chr(10).join(L))
        print("GITLAB_SYNC:%s" % os.path.relpath(out, VAULT).replace("\\", "/"))
        print("AUTH_FAILED:%s" % autherr.raw[:120])
        return

    projs, err = api("groups/%s/projects" % GROUP, include_subgroups="true",
                     per_page=100, simple="true", archived="false")
    if projs is None:
        gaps.append("列出群組專案失敗 → **%s**（已改用專案筆記的 git-remote 當清單）" % err)
        projs = projects_from_notes()
    L.append("掃描 %d 個專案。" % len(projs))
    L.append("")

    total_issues = total_mrs = total_wikis = 0
    body = []
    for p in projs:
        full = p["path_with_namespace"]
        pid = urllib.parse.quote(full, safe="")
        sec = ["", "=" * 70, "## `%s`" % full, ""]
        got_any = False

        info, e = api("projects/" + pid)
        if info:
            sec.append("- 預設分支 `%s`｜最後活動 %s｜可見度 %s" %
                       (info.get("default_branch"), (info.get("last_activity_at") or "")[:10],
                        info.get("visibility")))
            if info.get("description"):
                sec.append("- 描述：%s" % short(info["description"], 160))
            got_any = True
        elif e is not None:
            note = "專案基本資料：**%s**" % e
            if note not in gaps:
                gaps.append(note)

        iss, e = api("projects/%s/issues" % pid, scope="all", state="opened",
                     per_page=50, order_by="updated_at")
        if iss is not None:
            if iss:
                got_any = True
                total_issues += len(iss)
                sec += ["", "### 未關閉 Issues（%d）" % len(iss), "",
                        "| # | 標題 | 指派 | 標籤 | 更新 |", "| --- | --- | --- | --- | --- |"]
                for i in iss:
                    who = (i.get("assignee") or {}).get("name") or "—"
                    sec.append("| %s | %s | %s | %s | %s |" % (
                        i["iid"], short(i["title"], 60).replace("|", "／"), who,
                        "、".join(i.get("labels") or []) or "—", (i.get("updated_at") or "")[:10]))
        elif e is not None:
            note = "Issues：**%s**" % e
            if note not in gaps:
                gaps.append(note)

        mrs, e = api("projects/%s/merge_requests" % pid, state="all",
                     updated_after=since, per_page=30, order_by="updated_at")
        if mrs is not None:
            if mrs:
                got_any = True
                total_mrs += len(mrs)
                sec += ["", "### 近 %d 天的 Merge Requests（%d）" % (SINCE_DAYS, len(mrs)), "",
                        "| !# | 標題 | 狀態 | 作者 | 更新 |", "| --- | --- | --- | --- | --- |"]
                for m in mrs:
                    sec.append("| %s | %s | %s | %s | %s |" % (
                        m["iid"], short(m["title"], 60).replace("|", "／"), m["state"],
                        (m.get("author") or {}).get("name") or "—", (m.get("updated_at") or "")[:10]))
        elif e is not None:
            note = "Merge Requests：**%s**" % e
            if note not in gaps:
                gaps.append(note)

        wikis, e = api("projects/%s/wikis" % pid)
        if wikis:
            got_any = True
            total_wikis += len(wikis)
            sec += ["", "### Wiki 頁面（%d）" % len(wikis), ""]
            for w in wikis[:20]:
                page, _ = api("projects/%s/wikis/%s" % (pid, urllib.parse.quote(w["slug"], safe="")))
                sec.append("- **%s**" % w["title"])
                if page and page.get("content"):
                    c = page["content"].strip()
                    sec += ["", "```", c[:4000], "```", ""]
        elif e is not None:
            note = "Wiki：**%s**" % e
            if note not in gaps:
                gaps.append(note)

        ms, e = api("projects/%s/milestones" % pid, state="active")
        if ms:
            got_any = True
            sec += ["", "### 進行中的里程碑", ""]
            for m in ms:
                sec.append("- **%s**｜到期 %s｜%s" % (m["title"], m.get("due_date") or "未定",
                                                    short(m.get("description"), 80) or ""))

        if got_any:
            body += sec

    if gaps:
        L += ["> [!warning] 以下資料沒拿到（**不等於遠端沒有**）"] + ["> - " + g for g in gaps] + [""]
    L += ["**取得總計**：Issues %d 則｜MR %d 筆｜Wiki 頁 %d 頁" % (total_issues, total_mrs, total_wikis), ""]
    L += body

    out = os.path.join(OUT_DIR, "gitlab-%s.md" % today.isoformat())
    io.open(out, "w", encoding="utf-8").write("\n".join(L))
    print("GITLAB_SYNC:%s" % os.path.relpath(out, VAULT).replace("\\", "/"))
    print("issues=%d mrs=%d wikis=%d gaps=%d" % (total_issues, total_mrs, total_wikis, len(gaps)))

if __name__ == "__main__":
    main()
