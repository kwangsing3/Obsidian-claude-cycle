# -*- coding: utf-8 -*-
"""掃描 vault 根目錄與 00-inbox 的投放檔，抽出純文字到 .ops/drops/ 供 Claude 閱讀。
不刪除、不搬移任何東西——那由 Claude 在確認歸納成功後執行。"""
import os, io, sys, re, json, zipfile, email, email.policy, datetime

VAULT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(VAULT, ".ops")
OUT_DIR = os.path.join(OPS, "drops"); os.makedirs(OUT_DIR, exist_ok=True)
SKIP_NAMES = {"CLAUDE.md", "home.md", "README.md", "❓ 待決事項.md"}
NATIVE = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ipynb"}
PLAIN = {".txt", ".csv", ".json", ".log", ".md", ".yaml", ".yml", ".xml", ".sql", ".ndjson"}
TEXTY_ATT = {".md", ".txt", ".csv", ".json", ".log", ".html", ".htm", ".xml", ".eml"}
OOXML_ATT = {".docx", ".xlsx", ".pptx"}
CANDIDATES = ("utf-8", "gb18030", "big5hkscs", "cp950", "utf-16", "latin-1")
COMMON = set("的一是不了在人有我他這中大為上個到說時要就出會可也你對生能"
             "而子那得於著下自之年過發們所以及此系統資料需求功能服務客戶")
LIMIT = 30000

def best_decode(raw, declared=None):
    """信件常宣告錯編碼（實測有內容標 gb2312 但其實是 gb18030）。
    用常用中文字數為主、替換字數為輔，挑最合理的解碼結果。"""
    if isinstance(raw, str):
        return raw
    order = ([declared] if declared else []) + list(CANDIDATES)
    best, best_score = None, None
    for enc in order:
        if not enc:
            continue
        try:
            t = raw.decode(enc, "replace")
        except (LookupError, UnicodeError):
            continue
        score = sum(1 for c in t if c in COMMON) - t.count("\ufffd") * 3
        if best_score is None or score > best_score:
            best, best_score = t, score
    return best if best is not None else raw.decode("utf-8", "replace")

def strip_tags(t):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "\n", t)
    return "\n".join(x.strip() for x in t.split("\n") if x.strip())

def xml_text(data):
    t = re.sub(rb"<[^>]+>", b" ", data).decode("utf-8", "replace")
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n{3,}", "\n\n", t)).strip()

def from_ooxml(path, ext):
    parts = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if ext == ".docx":
            targets = [n for n in names if n == "word/document.xml"]
        elif ext == ".pptx":
            targets = sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))
        elif ext == ".xlsx":
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = [s.decode("utf-8", "replace") for s in
                          re.findall(rb"<t[^>]*>(.*?)</t>", z.read("xl/sharedStrings.xml"), re.S)]
            out = ["共用字串 %d 筆：" % len(shared), " | ".join(shared[:800])]
            for n in sorted(x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
                out.append("\n--- %s ---" % n)
                out.append(xml_text(z.read(n))[:8000])
            return "\n".join(out)
        else:
            targets = []
        for n in targets:
            parts.append(("\n--- %s ---\n" % n) + xml_text(z.read(n)))
    return "\n".join(parts)

def fix_name(fn):
    """附件檔名的 encoded-word 也可能宣告錯 charset。
    解得出來就用解出來的，解不出來就原樣保留——絕不做會丟字的轉換。"""
    if not fn:
        return fn
    import email.header
    try:
        out = []
        for txt, enc in email.header.decode_header(fn):
            out.append(best_decode(txt, enc) if isinstance(txt, bytes) else txt)
        joined = "".join(out)
        return joined if joined.strip() else fn
    except Exception:
        return fn

def raw_headers(path):
    """標頭的 MIME encoded-word 也常宣告錯 charset，改用 best_decode 重解。"""
    import email.header
    with open(path, "rb") as f:
        m2 = email.message_from_binary_file(f)   # compat32：保留原始位元組
    def dec(k):
        v = m2.get(k)
        if not v:
            return ""
        out = []
        for txt, enc in email.header.decode_header(v):
            out.append(best_decode(txt, enc) if isinstance(txt, bytes) else txt)
        return "".join(out)
    return dec

def from_eml(path):
    with open(path, "rb") as f:
        m = email.message_from_binary_file(f, policy=email.policy.default)
    att = [fix_name(x.get_filename()) for x in m.walk() if x.get_filename()]
    d = raw_headers(path)
    head = ["寄件者: %s" % d("From"), "收件者: %s" % d("To"),
            "副本: %s" % d("Cc"), "日期: %s" % d("Date"),
            "主旨: %s" % d("Subject"),
            "附件: %s" % ("、".join(x for x in att if x) or "無")]
    body = ""
    try:
        b = m.get_body(preferencelist=("plain", "html"))
        if b is not None:
            raw = b.get_payload(decode=True)
            body = best_decode(raw, b.get_content_charset()) if raw else ""
            if b.get_content_type() == "text/html":
                body = strip_tags(body)
    except Exception as e:
        body = "(內文解析失敗: %s)" % e
    out = ["\n".join(head), "\n\n---\n\n", body.strip()]
    for part in m.walk():
        fn = fix_name(part.get_filename())
        if not fn:
            continue
        ext = os.path.splitext(fn)[1].lower()
        if ext not in TEXTY_ATT and ext not in OOXML_ATT:
            continue
        try:
            raw = part.get_payload(decode=True)
            if not raw:
                continue
            out.append("\n\n########## 附件：%s (%d bytes) ##########\n" % (fn, len(raw)))
            if ext in OOXML_ATT:
                tmp = os.path.join(OUT_DIR, "_tmp" + ext)
                open(tmp, "wb").write(raw)
                out.append(from_ooxml(tmp, ext)[:12000])
                os.remove(tmp)
            elif ext in (".html", ".htm"):
                t = best_decode(raw)
                out.append(strip_tags(t)[:8000])
                for sc in re.findall(r"<script[^>]*>(.*?)</script>", t, flags=re.S | re.I):
                    if len(sc) > 2000 and "{" in sc:
                        out.append("\n【⚠️ 附件 script 內含 %d 字資料】\n%s" % (len(sc), sc[:10000]))
            else:
                out.append(best_decode(raw)[:12000])
        except Exception as e:
            out.append("(附件 %s 抽取失敗: %s)" % (fn, e))
    return "".join(out)

def from_msg(path):
    import extract_msg
    m = extract_msg.Message(path)
    att = [a.longFilename or a.shortFilename for a in (m.attachments or [])]
    head = ["寄件者: %s" % (m.sender or ""), "收件者: %s" % (m.to or ""),
            "副本: %s" % (m.cc or ""), "日期: %s" % (m.date or ""),
            "主旨: %s" % (m.subject or ""),
            "附件: %s" % ("、".join(x for x in att if x) or "無")]
    body = m.body or ""
    if not body and m.htmlBody:
        body = strip_tags(best_decode(m.htmlBody))
    m.close()
    return "\n".join(head) + "\n\n---\n\n" + body.strip()

def from_html(path):
    s = best_decode(open(path, "rb").read())
    out = []
    txt = strip_tags(s)
    out.append("【可見文字 %d 字】\n%s" % (len(txt), txt[:12000]))
    for sc in re.findall(r"<script[^>]*>(.*?)</script>", s, flags=re.S | re.I):
        if len(sc) > 2000 and "{" in sc:
            out.append("\n【⚠️ script 內含 %d 字的資料，可能才是真正的內容】\n%s" % (len(sc), sc[:15000]))
    return "\n".join(out)

def collect():
    files = []
    for name in sorted(os.listdir(VAULT)):
        p = os.path.join(VAULT, name)
        if os.path.isdir(p) or name in SKIP_NAMES or name.startswith("."):
            continue
        files.append(p)
    inbox = os.path.join(VAULT, "00-inbox")
    if os.path.isdir(inbox):
        for name in sorted(os.listdir(inbox)):
            p = os.path.join(inbox, name)
            if os.path.isfile(p) and not name.startswith("."):
                files.append(p)
    return files

def main():
    files = collect()
    if not files:
        print("NO_DROPS")
        return
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(OUT_DIR, "%s.md" % stamp)
    L = ["# 投放檔抽取結果 %s" % stamp, "", "共 %d 個檔案。" % len(files), ""]
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        rel = os.path.relpath(p, VAULT).replace("\\", "/")
        size = os.path.getsize(p)
        mt = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
        L += ["", "=" * 70, "## `%s`" % rel, "",
              "- 大小：%s bytes ｜ 修改時間：%s ｜ 副檔名：`%s`" % (size, mt, ext), ""]
        try:
            if ext in NATIVE:
                L += ["> [!note] 這個格式請用 Read 工具直接開 `%s`，不需要抽取。" % rel]
            elif ext == ".msg":
                L += ["```", from_msg(p)[:LIMIT], "```"]
            elif ext == ".eml":
                L += ["```", from_eml(p)[:LIMIT], "```"]
            elif ext in OOXML_ATT:
                L += ["```", from_ooxml(p, ext)[:LIMIT], "```"]
            elif ext in (".html", ".htm"):
                L += ["```", from_html(p)[:LIMIT], "```"]
            elif ext in PLAIN:
                L += ["```", best_decode(open(p, "rb").read())[:LIMIT], "```"]
            else:
                L += ["> [!warning] 未支援的格式 `%s`，只列出存在，內容未抽取。" % ext]
        except Exception as e:
            L += ["> [!failure] 抽取失敗：`%s: %s`" % (type(e).__name__, e)]
    io.open(out, "w", encoding="utf-8").write("\n".join(L))
    print("EXTRACTED:%s" % os.path.relpath(out, VAULT).replace("\\", "/"))
    for p in files:
        print("FILE:%s" % os.path.relpath(p, VAULT).replace("\\", "/"))

if __name__ == "__main__":
    main()
