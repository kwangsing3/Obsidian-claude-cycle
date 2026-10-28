# -*- coding: utf-8 -*-
"""對 GitLab Issue 寫入。預設只留言；關閉需明確帶 --allow-close。

用法：
  gitlab_write.py comment <project_path> <iid> <markdown 檔或 ->
  gitlab_write.py close   <project_path> <iid> --allow-close
  gitlab_write.py create  <project_path> <title> <markdown 檔或 ->

設計約束（{{OWNER_NAME}} 2026-08-20 決定）：
  - 每日排程只能 comment，不得 close。close 必須由 {{OWNER_NAME}} 在對話中確認後才執行。
  - 留言帶固定標記，重複執行不會洗版。
  - create 只在 {{OWNER_NAME}} 於對話中明確要求開 issue 時執行，排程不得開 issue；
    同標題已有 open issue 時跳過。
"""
import sys, os, io, json, urllib.parse, urllib.request as ureq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitlab_sync as G

MARK = "<!-- obsidian-vault-verify -->"

def _req(method, endpoint, data=None):
    url = G.API + "/" + endpoint
    body = urllib.parse.urlencode(data).encode() if data else None
    req = ureq.Request(url, data=body, method=method,
                       headers={"PRIVATE-TOKEN": G.TOKEN,
                                "User-Agent": "obsidian-vault-sync",
                                "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with ureq.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception as e:
        b = ""
        if hasattr(e, "read"):
            try: b = e.read().decode("utf-8", "replace")
            except Exception: pass
        msg = b
        try:
            j = json.loads(b); msg = j.get("error_description") or j.get("message") or b
        except Exception: pass
        return None, (msg or str(e))[:200]

def existing_marked_note(pid, iid):
    notes, err = G.api("projects/%s/issues/%s/notes" % (pid, iid), per_page=100)
    if not notes:
        return None
    for n in notes:
        if MARK in (n.get("body") or ""):
            return n
    return None

def comment(project, iid, text):
    pid = urllib.parse.quote(project, safe="")
    old = existing_marked_note(pid, iid)
    body = text.rstrip() + "\n\n" + MARK
    if old:
        if (old.get("body") or "").strip() == body.strip():
            return "SKIP 內容相同，未重複留言"
        d, e = _req("PUT", "projects/%s/issues/%s/notes/%s" % (pid, iid, old["id"]),
                    {"body": body})
        return ("UPDATED 既有留言 #%s" % old["id"]) if d else ("FAIL " + e)
    d, e = _req("POST", "projects/%s/issues/%s/notes" % (pid, iid), {"body": body})
    return ("POSTED 留言 #%s" % d["id"]) if d else ("FAIL " + e)

def close(project, iid):
    pid = urllib.parse.quote(project, safe="")
    d, e = _req("PUT", "projects/%s/issues/%s" % (pid, iid), {"state_event": "close"})
    return ("CLOSED #%s" % iid) if d else ("FAIL " + e)

def create(project, title, text):
    """開新 issue。同標題已有 open issue 時跳過，不重複開。不設標籤／指派。"""
    pid = urllib.parse.quote(project, safe="")
    found, err = G.api("projects/%s/issues" % pid, state="opened", search=title,
                       per_page=100)
    if err:
        return "FAIL " + str(err)[:200]
    for i in found or []:
        if (i.get("title") or "").strip() == title.strip():
            return "EXISTS #%s %s" % (i["iid"], i.get("web_url", ""))
    d, e = _req("POST", "projects/%s/issues" % pid,
                {"title": title, "description": text.rstrip()})
    return ("CREATED #%s %s" % (d["iid"], d.get("web_url", ""))) if d else ("FAIL " + e)

if __name__ == "__main__":
    G.TOKEN = G.get_token()
    act = sys.argv[1]
    if act == "create":
        proj, title, src = sys.argv[2], sys.argv[3], sys.argv[4]
        text = sys.stdin.read() if src == "-" else io.open(src, encoding="utf-8").read()
        print(create(proj, title, text))
        sys.exit(0)
    proj, iid = sys.argv[2], sys.argv[3]
    if act == "comment":
        src = sys.argv[4]
        text = sys.stdin.read() if src == "-" else io.open(src, encoding="utf-8").read()
        print(comment(proj, iid, text))
    elif act == "close":
        if "--allow-close" not in sys.argv:
            sys.exit("拒絕：關閉 issue 需要 --allow-close，且必須由 {{OWNER_NAME}} 確認後才執行。")
        print(close(proj, iid))
    else:
        sys.exit("未知動作：%s" % act)
