#!/usr/bin/env python3
"""Local, read-only source ingestion and lexical retrieval for the Mouliao skill.

EPUB support uses the Python standard library. PDF extraction additionally needs
PyMuPDF. The generated index never executes book content and never changes sources.
"""
from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import os
from pathlib import Path
import posixpath
import re
import sqlite3
import sys
import tempfile
import unicodedata
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

FORMATS = {".epub", ".pdf", ".mobi", ".azw3"}
NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container",
      "o": "http://www.idpf.org/2007/opf",
      "d": "http://purl.org/dc/elements/1.1/",
      "n": "http://www.daisy.org/z3986/2005/ncx/"}


class PlainText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "br", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "li", "tr"):
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)

    def text(self):
        return "\n".join(re.sub(r"[\t \u00a0]+", " ", p).strip()
                         for p in "".join(self.parts).splitlines() if p.strip())


def plain(data):
    # Prefer the XML encoding declaration where provided; fall back explicitly.
    match = re.search(br'encoding=["\x27]([^"\x27]+)', data[:200])
    encoding = match.group(1).decode("ascii") if match else "utf-8-sig"
    parser = PlainText()
    parser.feed(data.decode(encoding, errors="replace"))
    return parser.text()


def iter_books(root):
    for parent, dirs, files in os.walk(root):
        for name in sorted(dirs[:]):
            if name.startswith("."):
                dirs.remove(name)
            elif name.lower().endswith(".epub"):
                dirs.remove(name)
                yield Path(parent) / name
        for name in sorted(files):
            if not name.startswith(".") and Path(name).suffix.lower() in FORMATS:
                yield Path(parent) / name


def stamp(path):
    """Metadata signature to detect stale local sources without changing them."""
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    dig = hashlib.sha256()
    for f in files:
        st = f.stat()
        rel = f.relative_to(path) if path.is_dir() else f.name
        dig.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode())
    return dig.hexdigest()


class Epub:
    def __init__(self, path):
        self.path = path
        self.archive = None if path.is_dir() else zipfile.ZipFile(path)

    def read(self, member):
        member = posixpath.normpath(member)
        if member.startswith(("../", "/")) or member == "..":
            raise ValueError("EPUB member points outside the book")
        if self.archive is not None:
            return self.archive.read(member)
        candidate = (self.path / member).resolve()
        if not candidate.is_relative_to(self.path.resolve()):
            raise ValueError("EPUB member escapes source package")
        return candidate.read_bytes()

    def close(self):
        if self.archive:
            self.archive.close()

    def extract(self):
        container = ET.fromstring(self.read("META-INF/container.xml"))
        rootfile = container.find("c:rootfiles/c:rootfile", NS)
        if rootfile is None:
            raise ValueError("Missing EPUB rootfile")
        opf_path = rootfile.get("full-path")
        opf = ET.fromstring(self.read(opf_path))
        base = posixpath.dirname(opf_path)
        meta = {k: [e.text for e in opf.findall(".//d:" + k, NS) if e.text]
                for k in ("title", "creator", "identifier", "publisher", "date")}
        manifest = {i.get("id"): i for i in opf.findall("o:manifest/o:item", NS)}
        toc = []
        for item in manifest.values():
            if item.get("media-type") != "application/x-dtbncx+xml":
                continue
            ncx_path = posixpath.normpath(posixpath.join(base, unquote(item.get("href"))))
            ncx = ET.fromstring(self.read(ncx_path))
            for nav in ncx.findall(".//n:navPoint", NS):
                label = nav.find("n:navLabel/n:text", NS)
                content = nav.find("n:content", NS)
                if label is not None and content is not None:
                    u = urlsplit(content.get("src", ""))
                    toc.append({"title": label.text or "", "member": posixpath.normpath(
                        posixpath.join(posixpath.dirname(ncx_path), unquote(u.path))),
                        "anchor": u.fragment})
        units, warnings = [], []
        for order, ref in enumerate(opf.findall("o:spine/o:itemref", NS)):
            item = manifest.get(ref.get("idref"))
            if item is None:
                warnings.append("missing_spine_item:" + str(ref.get("idref")))
                continue
            u = urlsplit(item.get("href", ""))
            if u.scheme:
                warnings.append("remote_spine_not_read:" + item.get("href"))
                continue
            member = posixpath.normpath(posixpath.join(base, unquote(u.path)))
            try:
                text = plain(self.read(member))
                labels = [t["title"] for t in toc if t["member"] == member]
                heading = labels[0] if labels else (text.splitlines()[0][:100] if text else member)
                units.append({"unit": member, "heading": heading, "order": order,
                              "text": text, "page": None})
            except Exception as exc:
                warnings.append(f"unreadable_member:{member}:{type(exc).__name__}")
        return meta, toc, units, warnings


def extract(path):
    if path.suffix.lower() == ".epub":
        book = Epub(path)
        try:
            return book.extract()
        finally:
            book.close()
    if path.suffix.lower() == ".pdf":
        import fitz
        fitz.TOOLS.mupdf_display_errors(False)
        fitz.TOOLS.mupdf_display_warnings(False)
        with fitz.open(path) as doc:
            if doc.needs_pass:
                return {}, [], [], ["password_required"]
            meta = {"title": [doc.metadata.get("title") or path.stem],
                    "creator": [doc.metadata.get("author") or ""], "pages": doc.page_count}
            toc = [{"title": title, "page": page} for _, title, page in doc.get_toc()]
            units = [{"unit": f"pdf-page:{i + 1}", "heading": f"PDF 文件第 {i + 1} 页",
                      "order": i, "text": p.get_text(sort=True).strip(), "page": i + 1}
                     for i, p in enumerate(doc)]
            low = sum(len(u["text"]) < 30 for u in units)
            warnings = [f"low_text_pages:{low}/{len(units)}"] if low else []
            return meta, toc, units, warnings
    return {}, [], [], ["format_not_extracted"]


def chunks(text, size=1800, overlap=150):
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + size // 2, end)
            if boundary > start:
                end = boundary
        yield start, end, text[start:end]
        if end == len(text):
            return
        start = max(start + 1, end - overlap)


def title_key(value):
    value = re.sub(r"^\d+_", "", unicodedata.normalize("NFKC", value))
    value = re.split(r"[\(\[【]", value)[0]
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


def build(workspace):
    config = json.loads((workspace / "config/sources.json").read_text())
    out = workspace / config["index_directory"]
    out.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="index-", suffix=".sqlite", dir=out)
    os.close(fd)
    db = sqlite3.connect(temporary)
    db.executescript("""
      CREATE TABLE books(id TEXT PRIMARY KEY,title TEXT,path TEXT,source TEXT,stamp TEXT,status TEXT);
      CREATE TABLE chunks(id TEXT PRIMARY KEY,book_id TEXT,unit TEXT,heading TEXT,
                          unit_order INTEGER,start_char INTEGER,end_char INTEGER,text TEXT,page INTEGER);
      CREATE INDEX chunks_book ON chunks(book_id,unit_order,start_char);
    """)
    catalog = []
    try:
        for source in config["sources"]:
            root = Path(source["path"])
            if not root.is_dir():
                raise FileNotFoundError(f"Source folder unavailable: {root}")
            for path in sorted(iter_books(root)):
                rel = str(path.relative_to(root))
                bid = "B" + hashlib.sha256((source["id"] + ":" + rel).encode()).hexdigest()[:12]
                entry = {"id": bid, "source": source["label"], "path": str(path),
                         "format": path.suffix.lower()[1:], "package": path.is_dir(),
                         "title": path.stem, "review_status": "not_reviewed",
                         "text_characters": 0, "indexed_units": 0, "chunks": 0}
                try:
                    before = stamp(path)
                    meta, toc, units, warnings = extract(path)
                    entry.update(metadata=meta, toc=toc, warnings=warnings, stamp=before)
                    entry["title"] = next(iter(meta.get("title", [])), path.stem)
                    entry["authors"] = meta.get("creator", [])
                    entry["sample"] = "试读" in entry["title"]
                    entry["text_characters"] = sum(len(u["text"]) for u in units)
                    entry["total_units"] = len(units)
                    entry["indexed_units"] = sum(bool(u["text"]) for u in units)
                    if "format_not_extracted" in warnings:
                        status = "catalog_only"
                    elif entry["text_characters"] == 0:
                        status = "needs_ocr_or_access"
                    elif path.suffix.lower() == ".pdf" and sum(len(u["text"]) < 30 for u in units) > len(units) / 4:
                        status = "partial_text_needs_ocr"
                    elif any(w.startswith(("missing_spine", "unreadable_member", "remote_spine")) for w in warnings):
                        status = "partial_text"
                    else:
                        status = "text_indexed"
                    if stamp(path) != before:
                        raise RuntimeError("Source changed during indexing; rebuild required")
                    entry["status"] = status
                    db.execute("INSERT INTO books VALUES(?,?,?,?,?,?)", (bid, entry["title"], str(path), source["label"], before, status))
                    for unit in units:
                        for start, end, text in chunks(unit["text"]):
                            cid = bid + ":" + hashlib.sha256((unit["unit"] + ":" + str(start)).encode()).hexdigest()[:12]
                            db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?,?)", (cid, bid, unit["unit"], unit["heading"], unit["order"], start, end, text, unit["page"]))
                            entry["chunks"] += 1
                except Exception as exc:
                    # A failed book remains visible in the catalog; it is never called read.
                    entry["status"] = "error"
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                    db.execute("DELETE FROM chunks WHERE book_id=?", (bid,))
                    db.execute("DELETE FROM books WHERE id=?", (bid,))
                entry["title_group_candidate"] = title_key(entry["title"])
                catalog.append(entry)
                print(json.dumps({"book": len(catalog), "title": entry["title"][:42], "status": entry["status"], "chars": entry["text_characters"]}, ensure_ascii=False), flush=True)
        db.commit()
        db.close()
        os.replace(temporary, out / "index.sqlite")
        payload = {"sources": config["sources"], "book_files": len(catalog),
                   "note": "文件数不等于去重书籍数；文字已提取不等于已经精读。书名组仅为版本核对线索。", "books": catalog}
        (out / "catalog.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        lines = ["# 幕僚资料索引", "", payload["note"], "", "| 书目 ID | 书名 | 来源 | 格式 | 可检索状态 |", "|---|---|---|---|---|"]
        for b in catalog:
            lines.append(f"| {b['id']} | {b['title'].replace('|', '／')} | {b['source']} | {b['format']} | {b['status']} |")
        (out / "书目索引.md").write_text("\n".join(lines) + "\n")
    finally:
        try:
            db.close()
        except Exception:
            pass
        if Path(temporary).exists():
            Path(temporary).unlink()


def connect(workspace):
    path = workspace / "library/index.sqlite"
    if not path.is_file():
        raise FileNotFoundError("尚无资料索引；请先运行 build。")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def freshness(row):
    path = Path(row["path"])
    if not path.exists():
        return "source_missing"
    return "current" if stamp(path) == row["stamp"] else "source_changed_rebuild_required"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    sub.add_parser("status")
    b = sub.add_parser("books"); b.add_argument("query", nargs="?", default="")
    s = sub.add_parser("search"); s.add_argument("terms", nargs="+")
    s.add_argument("--book", default=""); s.add_argument("--limit", type=int, default=6)
    r = sub.add_parser("read"); r.add_argument("chunk_id")
    r.add_argument("--whole-unit", action="store_true"); r.add_argument("--offset", type=int, default=0)
    r.add_argument("--max-chars", type=int, default=10000)
    args = parser.parse_args()
    workspace = (args.workspace or Path(os.environ.get("MOULIAO_WORKSPACE", Path(__file__).resolve().parents[4]))).resolve()
    if args.command == "build":
        build(workspace); return
    catalog = json.loads((workspace / "library/catalog.json").read_text())
    if args.command in ("status", "books"):
        if args.command == "status":
            from collections import Counter
            out = {"book_files": len(catalog["books"]), "statuses": dict(Counter(b["status"] for b in catalog["books"])), "meaning": catalog["note"]}
        else:
            out = [{k: b.get(k) for k in ("id", "title", "authors", "source", "status", "sample")}
                   for b in catalog["books"] if args.query.lower() in (b["title"] + b["path"] + b["id"]).lower()]
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    db = connect(workspace)
    try:
        if args.command == "search":
            terms = [t.strip() for t in args.terms if t.strip()]
            if not terms:
                raise ValueError("需要至少一个检索词")
            # LIKE supports two-character Chinese terms without extra tokenizer dependencies.
            condition = " OR ".join("(c.text LIKE ? OR c.heading LIKE ? OR b.title LIKE ?)" for _ in terms)
            params = ["%" + t + "%" for t in terms for _ in range(3)]
            book_where = " AND (b.id=? OR b.title LIKE ?)" if args.book else ""
            if args.book:
                params += [args.book, "%" + args.book + "%"]
            score = " + ".join("(CASE WHEN c.text LIKE ? THEN 1 ELSE 0 END)" for _ in terms)
            query = f"""WITH scored AS (
                SELECT c.*,b.title,b.path,b.source,b.stamp,b.status,({score}) AS matches
                FROM chunks c JOIN books b ON b.id=c.book_id WHERE ({condition}){book_where}
              ), ranked AS (
                SELECT *,ROW_NUMBER() OVER(PARTITION BY book_id,unit ORDER BY matches DESC,start_char) AS rn FROM scored
              ) SELECT * FROM ranked WHERE rn=1 ORDER BY matches DESC,id LIMIT ?"""
            rows = db.execute(query, ["%" + t + "%" for t in terms] + params + [max(1, min(args.limit, 30))]).fetchall()
            result, seen = [], set()
            for row in rows:
                key = (row["book_id"], row["unit"])
                if key in seen:
                    continue
                seen.add(key)
                pos = next((row["text"].find(t) for t in terms if t in row["text"]), 0)
                result.append({k: row[k] for k in ("id", "book_id", "title", "unit", "heading", "page", "source", "status")})
                result[-1].update(excerpt=row["text"][max(0, pos - 100):pos + 500], freshness=freshness(row))
            print(json.dumps({"retrieval": "local_keyword_match", "results": result,
                              "note": "命中仅用于定位。引用前运行 read 回读；搜索未命中不能证明原书没有相关内容。"}, ensure_ascii=False, indent=2))
        else:
            row = db.execute("SELECT c.*,b.title,b.path,b.source,b.stamp,b.status FROM chunks c JOIN books b ON b.id=c.book_id WHERE c.id=?", (args.chunk_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown chunk id")
            state = freshness(row)
            if state != "current":
                raise RuntimeError(state)
            text = row["text"]
            if args.whole_unit:
                parts = db.execute("SELECT start_char,text FROM chunks WHERE book_id=? AND unit=? ORDER BY start_char", (row["book_id"], row["unit"])).fetchall()
                text = ""
                for part in parts:
                    text += part["text"][max(0, len(text) - part["start_char"]):]
            start = max(0, args.offset); end = min(len(text), start + max(1, args.max_chars))
            print(json.dumps({"book_id": row["book_id"], "title": row["title"], "source_path": row["path"], "unit": row["unit"], "heading": row["heading"], "pdf_file_page": row["page"], "freshness": state, "total_chars": len(text), "offset": start, "end": end, "truncated": end < len(text), "text": text[start:end]}, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
