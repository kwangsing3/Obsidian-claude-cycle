# -*- coding: utf-8 -*-
"""抓取指定 GitLab 專案的完整素材（README／檔案樹／語言／提交／貢獻者），輸出 JSON 供建檔用。"""
import sys, os, json, urllib.parse, urllib.request as ureq
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitlab_sync as G

def api_raw(endpoint, **params):
    url = G.API + "/" + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = ureq.Request(url, headers={"PRIVATE-TOKEN": G.TOKEN, "User-Agent": "obsidian-vault-sync"})
    try:
        with ureq.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    except Exception:
        return None

def fetch(full):
    pid = urllib.parse.quote(full, safe="")
    o = {"path": full}
    info, _ = G.api("projects/" + pid)
    if info:
        o["desc"] = info.get("description")
        o["branch"] = info.get("default_branch")
        o["created"] = (info.get("created_at") or "")[:10]
        o["last"] = (info.get("last_activity_at") or "")[:10]
        o["visibility"] = info.get("visibility")
        o["topics"] = info.get("topics") or []
        o["archived"] = info.get("archived")
    langs, _ = G.api("projects/%s/languages" % pid)
    o["langs"] = langs or {}
    br, _ = G.api("projects/%s/repository/branches" % pid, per_page=20)
    o["branches"] = [b["name"] for b in (br or [])]
    cm, _ = G.api("projects/%s/repository/commits" % pid, per_page=25)
    o["commits"] = [{"d": (c.get("created_at") or "")[:10], "m": (c.get("title") or "").strip(),
                     "a": c.get("author_name")} for c in (cm or [])]
    cm2, _ = G.api("projects/%s/repository/commits" % pid, per_page=1, order="default", ref_name=o.get("branch") or "main")
    co, _ = G.api("projects/%s/repository/contributors" % pid)
    o["contributors"] = [{"n": c.get("name"), "c": c.get("commits")} for c in (co or [])][:6]
    tree, _ = G.api("projects/%s/repository/tree" % pid, per_page=100)
    o["tree"] = [{"n": t["name"], "t": t["type"]} for t in (tree or [])]
    # 子目錄再看一層（最多 6 個目錄）
    o["subtree"] = {}
    for t in [x for x in (tree or []) if x["type"] == "tree"][:6]:
        sub, _ = G.api("projects/%s/repository/tree" % pid, path=t["path"], per_page=40)
        if sub:
            o["subtree"][t["name"]] = [s["name"] for s in sub][:40]
    # README
    o["readme"] = None
    for fn in ["README.md", "readme.md", "README.MD", "README", "README.txt", "CLAUDE.md"]:
        txt = api_raw("projects/%s/repository/files/%s/raw" % (pid, urllib.parse.quote(fn, safe="")),
                      ref=o.get("branch") or "main")
        if txt and txt.strip() and not txt.strip().startswith('{"message"'):
            o["readme_file"] = fn
            o["readme"] = txt[:8000]
            break
    # manifest
    o["manifests"] = {}
    for fn in ["package.json", "go.mod", "requirements.txt", "pyproject.toml", "composer.json", "pom.xml", "angular.json"]:
        txt = api_raw("projects/%s/repository/files/%s/raw" % (pid, urllib.parse.quote(fn, safe="")),
                      ref=o.get("branch") or "main")
        if txt and not txt.strip().startswith('{"message"'):
            o["manifests"][fn] = txt[:1200]
    return o

if __name__ == "__main__":
    G.TOKEN = G.get_token()
    targets = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    out = {}
    for i, t in enumerate(targets, 1):
        print("[%d/%d] %s" % (i, len(targets), t), flush=True)
        try:
            out[t] = fetch(t)
        except Exception as e:
            out[t] = {"path": t, "error": str(e)}
    json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("寫入", sys.argv[2], os.path.getsize(sys.argv[2]), "bytes")
