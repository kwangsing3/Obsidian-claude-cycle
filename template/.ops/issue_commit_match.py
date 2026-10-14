# -*- coding: utf-8 -*-
"""為每則 GitLab Issue 蒐集「可能解決它的 commit」證據，供人工判定。
不自動下結論——只列候選與匹配理由。"""
import sys, os, io, re, json, subprocess, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gitlab_sync as G

VAULT = G.VAULT
PD = os.path.join(VAULT, "10-projects")
LOCAL = G.CFG["source_root"]

STOP = set("的了在是和與及或這那有能夠可以進行需要新增修改更新以及並且一個項目功能"
           "add fix update the a an and or to for of in on with support".split())

def tokens(text):
    """抽出有辨識度的關鍵詞：英文字詞、型號、中文 2-4 字詞。"""
    t = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_.\-]{2,}", text or ""):
        wl = w.lower().strip(".-_")
        if len(wl) >= 3 and wl not in STOP:
            t.add(wl)
    for w in re.findall(r"[\u4e00-\u9fff]{2,6}", text or ""):
        if w not in STOP and len(w) >= 2:
            t.add(w)
    return t

def local_repo(slug, folder):
    f = os.path.join(PD, folder, folder + ".md")
    s = io.open(f, encoding="utf-8").read(4000)
    m = re.search(r"^repo-path: (.+)$", s, re.M)
    if not m:
        return None
    p = m.group(1).strip().replace("\\", "/")
    return p if os.path.isdir(os.path.join(p, ".git")) else None

def local_commits(path):
    try:
        out = subprocess.run(
            ["git", "-C", path, "log", "--all", "--date=short",
             "--format=%H%x01%ad%x01%an%x01%s%x01%b%x02"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90).stdout
    except Exception:
        return []
    res = []
    for rec in out.split("\x02"):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split("\x01")
        if len(parts) < 4:
            continue
        res.append({"sha": parts[0][:8], "d": parts[1], "a": parts[2],
                    "m": parts[3], "b": (parts[4] if len(parts) > 4 else "")[:300]})
    return res

def remote_commits(full):
    pid = urllib.parse.quote(full, safe="")
    out, page = [], 1
    while page <= 4:
        d, e = G.api("projects/%s/repository/commits" % pid, per_page=100, page=page)
        if not d:
            break
        for c in d:
            out.append({"sha": c["short_id"], "d": (c.get("created_at") or "")[:10],
                        "a": c.get("author_name"), "m": (c.get("title") or "").strip(),
                        "b": (c.get("message") or "")[:300]})
        if len(d) < 100:
            break
        page += 1
    return out

def main():
    G.TOKEN = G.get_token()
    report = []
    for folder in sorted(os.listdir(PD)):
        f = os.path.join(PD, folder, folder + ".md")
        rd = os.path.join(PD, folder, "requirements")
        if not os.path.exists(f) or not os.path.isdir(rd):
            continue
        gl = [x for x in os.listdir(rd) if x.startswith("\U0001F4CC GL-")]
        if not gl:
            continue
        slug = folder.split(" ", 1)[1]
        s = io.open(f, encoding="utf-8").read(4000)
        full = re.search(r"^git-remote: https://gitlab\.com/(\S+?)(?:\.git)?\s*$", s, re.M).group(1)
        lp = local_repo(slug, folder)
        commits = local_commits(lp) if lp else remote_commits(full)
        src = ("本機 %s" % lp) if lp else "GitLab API"
        report.append("\n" + "=" * 72)
        report.append("## %s  （%d 則 issue｜%d 個 commit，來源：%s）" % (slug, len(gl), len(commits), src))
        for fn in sorted(gl, key=lambda x: int(re.search(r"GL-(\d+)", x).group(1))):
            p = os.path.join(rd, fn)
            body = io.open(p, encoding="utf-8").read()
            iid = re.search(r"req-id: GL-(\d+)", body).group(1)
            title = re.search(r"^title: (.+)$", body, re.M).group(1)
            status = re.search(r"^status: (.+)$", body, re.M).group(1)
            created = re.search(r"^created: (.+)$", body, re.M).group(1)
            desc = body.split("## 需求內容", 1)[1].split("##")[0] if "## 需求內容" in body else ""
            kw = tokens(title + " " + desc)
            report.append("\n### GL-%s [%s] %s" % (iid, status, title))
            report.append("    建立 %s ｜ 關鍵詞 %s" % (created, ", ".join(sorted(kw))[:150]))
            # 1) 直接引用 issue 編號
            refs = [c for c in commits if re.search(r"#%s\b" % iid, c["m"] + " " + c["b"])]
            for c in refs[:5]:
                report.append("    [引用#%s] %s %s %s" % (iid, c["sha"], c["d"], c["m"][:70]))
            # 2) 關鍵詞命中（只看 issue 建立之後的 commit）
            scored = []
            for c in commits:
                if c["d"] < created:
                    continue
                ct = tokens(c["m"] + " " + c["b"])
                hit = kw & ct
                if len(hit) >= 1:
                    scored.append((len(hit), c, hit))
            scored.sort(key=lambda x: (-x[0], x[1]["d"]))
            for n, c, hit in scored[:6]:
                report.append("    [命中%d] %s %s %s  ← %s" % (
                    n, c["sha"], c["d"], c["m"][:62], "、".join(sorted(hit))[:40]))
            if not refs and not scored:
                report.append("    （issue 建立後沒有任何關鍵詞相符的 commit）")
    out = os.path.join(VAULT, ".ops", "drops", "issue-commit-evidence.md")
    io.open(out, "w", encoding="utf-8").write("# Issue ↔ Commit 證據\n" + "\n".join(report))
    print("寫入", os.path.relpath(out, VAULT), os.path.getsize(out), "bytes")

if __name__ == "__main__":
    main()
