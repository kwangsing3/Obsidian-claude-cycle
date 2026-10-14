# -*- coding: utf-8 -*-
"""把 GitLab Issues 轉成 vault 的需求筆記。
開啟中的 issue → status 依標籤判定；已關閉 → done。
已存在的筆記只更新 status 與 updated，不覆蓋人工補充的內容。"""
import sys, os, io, re, json, urllib.parse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitlab_sync as G

VAULT = G.VAULT
PD = os.path.join(VAULT, "10-projects")
TODAY = datetime.date.today().isoformat()

LABEL_STATUS = {"feature request": "approved", "enhancement": "approved",
                "optimize": "draft", "bug": "approved", "documentation": "draft"}
LABEL_PRI = {"bug": "high", "feature request": "medium",
             "enhancement": "medium", "optimize": "low", "documentation": "low"}

def slug_of(folder):
    return folder.split(" ", 1)[1] if " " in folder else folder

def projects():
    out = []
    for folder in sorted(os.listdir(PD)):
        f = os.path.join(PD, folder, folder + ".md")
        if not os.path.exists(f):
            continue
        s = io.open(f, encoding="utf-8").read(4000)
        m = re.search(r"^git-remote: https://gitlab\.com/(\S+?)(?:\.git)?\s*$", s, re.M)
        if m:
            out.append((folder, slug_of(folder), m.group(1)))
    return out

def clean(t):
    if not t:
        return ""
    t = re.sub(r"!\[image\]\(/uploads/[^)]+\)", "（圖片，見 GitLab issue）", t)
    t = re.sub(r"\r\n", "\n", t)
    return t.strip()

def main():
    G.TOKEN = G.get_token()
    created = updated = 0
    report = []
    for folder, slug, full in projects():
        pid = urllib.parse.quote(full, safe="")
        iss, err = G.api("projects/%s/issues" % pid, scope="all", state="all",
                         per_page=100, order_by="created_at", sort="asc")
        if not iss:
            continue
        rdir = os.path.join(PD, folder, "requirements")
        os.makedirs(rdir, exist_ok=True)
        n_new = n_upd = 0
        for i in iss:
            rid = "GL-%d" % i["iid"]
            fn = os.path.join(rdir, "\U0001F4CC %s.md" % rid)
            labels = [x.lower() for x in (i.get("labels") or [])]
            closed = i["state"] == "closed"
            status = "done" if closed else next(
                (LABEL_STATUS[l] for l in labels if l in LABEL_STATUS), "draft")
            pri = next((LABEL_PRI[l] for l in labels if l in LABEL_PRI), "medium")
            if os.path.exists(fn):
                s = io.open(fn, encoding="utf-8").read()
                # 人工／查證後的 status 比標籤推導的準，不要洗掉。
                # 只有 issue 在 GitLab 上被關閉時，才強制改成 done。
                verified = re.search(r"^verified: ", s, re.M) is not None
                s2 = s
                if closed or not verified:
                    s2 = re.sub(r"^status: .*$", "status: " + status, s2, count=1, flags=re.M)
                s2 = re.sub(r"^synced: .*$", "synced: " + TODAY, s2, count=1, flags=re.M)
                if s2 != s:
                    io.open(fn, "w", encoding="utf-8").write(s2)
                    n_upd += 1
                continue
            who = (i.get("assignee") or {}).get("name") or "未指派"
            L = ["---", "type: requirement", "kind: requirement",
                 "title: %s" % i["title"].replace(":", "：").replace('"', "'"),
                 "aliases:", "  - %s" % rid, "  - %s!%d" % (slug, i["iid"]),
                 "req-id: %s" % rid,
                 'project: "[[%s]]"' % slug,
                 "source: %s" % i["web_url"],
                 "source-type: gitlab-issue",
                 "status: %s" % status, "priority: %s" % pri,
                 "owner: %s" % who,
                 "created: %s" % (i.get("created_at") or "")[:10],
                 "synced: %s" % TODAY,
                 "gitlab-labels:"] + ["  - %s" % x for x in (i.get("labels") or [])] + [
                 "tags:", "  - requirement", "  - gitlab-issue", "---", "",
                 "# 📌 %s（%s）" % (i["title"], rid), "",
                 "> [!info] 來源：GitLab Issue",
                 "> `%s` #%d ｜ 狀態 **%s** ｜ 標籤 %s" % (
                     full, i["iid"], i["state"], "、".join(i.get("labels") or []) or "無"),
                 "> <%s>" % i["web_url"], ""]
            body = clean(i.get("description"))
            if body:
                L += ["## 需求內容", "", body, ""]
            else:
                L += ["> [!warning] 這則 issue 沒有描述，只有標題。", ""]
            if closed:
                L += ["## 狀態", "",
                      "已於 %s 關閉。" % (i.get("closed_at") or "")[:10], ""]
            L += ["## 相關", "- 專案：[[%s]]" % slug, "- GitLab：<%s>" % i["web_url"]]
            io.open(fn, "w", encoding="utf-8").write("\n".join(L))
            n_new += 1
        if n_new or n_upd:
            opened = sum(1 for x in iss if x["state"] == "opened")
            report.append((slug, len(iss), opened, n_new, n_upd))
            created += n_new
            updated += n_upd
    print("新建 %d 則、更新 %d 則需求筆記\n" % (created, updated))
    print("%-32s %-8s %-8s %-6s %s" % ("專案", "issues", "未關閉", "新建", "更新"))
    for r in sorted(report, key=lambda x: -x[1]):
        print("%-32s %-8d %-8d %-6d %d" % r)

if __name__ == "__main__":
    main()
