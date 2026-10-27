"""Layout checks: the things about a PDF that make ATS parsers fail."""

import re
from difflib import SequenceMatcher

from app.engines.geometry import find_gutter, tables
from app.issues import issue


def order_similarity(a: str, b: str) -> float:
    """How alike two readings are in word order (1.0 means identical)."""
    wa, wb = a.split(), b.split()
    if not wa or not wb:
        return 1.0 if wa == wb else 0.0
    return SequenceMatcher(None, wa, wb, autojunk=False).ratio()


def header_footer_text(pdf, page_lines: list[list[str]]) -> list[str]:
    """Text a parser may treat as page header or footer.

    Two signals: content tagged as a pagination artifact (Word does this for its
    header and footer when it exports a tagged PDF), and lines repeated at the
    top or bottom of every page of a multi-page document.
    """
    found = []
    for page in pdf.pages:
        artifact = "".join(c["text"] for c in page.chars if c.get("tag") == "Artifact")
        if artifact.strip():
            found.append(" ".join(artifact.split()))
    if len(page_lines) >= 2 and all(page_lines):
        def norm(s):
            return re.sub(r"\d+", "#", s.strip().lower())
        for pick in (lambda ls: ls[0], lambda ls: ls[-1]):
            first = norm(pick(page_lines[0]))
            if first and all(norm(pick(ls)) == first for ls in page_lines[1:]):
                found.append(pick(page_lines[0]).strip())
    return list(dict.fromkeys(found))


def _unmapped(t: str) -> bool:
    return t.startswith("(cid:") or "\ufffd" in t


def glyph_stats(pdf) -> dict:
    """Count problem characters. An unmapped glyph only counts as garbled text
    when it sits inside a word; a lost bullet symbol doesn't hurt parsing."""
    total = unmapped = symbols_lost = icons = ligatures = 0
    for page in pdf.pages:
        chars = page.chars
        for i, c in enumerate(chars):
            t = c["text"]
            total += 1
            if _unmapped(t):
                neighbours = [chars[j]["text"] for j in (i - 1, i + 1) if 0 <= j < len(chars)
                              and abs(chars[j]["top"] - c["top"]) < 3]
                if any(n.isalnum() for n in neighbours):
                    unmapped += 1
                else:
                    symbols_lost += 1
            elif any(0xE000 <= ord(ch) <= 0xF8FF or ord(ch) >= 0xF0000 for ch in t):
                icons += 1
            elif any(0xFB00 <= ord(ch) <= 0xFB06 for ch in t):
                ligatures += 1
    return {"total": total, "unmapped": unmapped, "symbols_lost": symbols_lost,
            "icons": icons, "ligatures": ligatures}


def count_tables(page) -> int:
    n = 0
    for table in tables(page):
        rows = table.extract()
        filled = sum(1 for row in rows for cell in row if cell and cell.strip())
        if len(rows) >= 2 and max(len(r) for r in rows) >= 2 and filled >= 4:
            n += 1
    return n


def run(pdf, engines: dict[str, list[str]]) -> tuple[dict, list[dict]]:
    """Return (layout facts, issues)."""
    issues = []
    pages_without_text = [
        p.page_number for p in pdf.pages if len(p.chars) < 20
    ]
    if len(pages_without_text) == len(pdf.pages):
        issues.append(issue("NO_TEXT_LAYER",
            "No text layer found. This PDF is an image, so an ATS reads nothing from it."))
    elif pages_without_text:
        issues.append(issue("NO_TEXT_LAYER",
            f"Page(s) {', '.join(map(str, pages_without_text))} have no readable text.",
            pages=pages_without_text))

    gutters = {}
    for page in pdf.pages:
        g = find_gutter(page)
        if g is not None:
            gutters[page.page_number] = round(g, 1)

    modern = "\n".join(engines["modern"])
    similarity = order_similarity("\n".join(engines["legacy"]), modern)
    stream_similarity = order_similarity("\n".join(engines["stream"]), modern)
    if gutters:
        issues.append(issue("MULTI_COLUMN",
            f"Two columns detected on page(s) {', '.join(map(str, gutters))}. A simple "
            f"parser reads straight across both columns; the two readings here agree on "
            f"only {similarity:.0%} of the word order.",
            pages=list(gutters)))
    if stream_similarity < 0.85:
        issues.append(issue("ORDER_MISMATCH",
            f"The text is stored in the PDF in a different order from how it looks (only "
            f"{stream_similarity:.0%} alike). ATSs that read the raw PDF order see it jumbled."))

    glyphs = glyph_stats(pdf)
    if glyphs["unmapped"] >= 5 or (glyphs["total"] and glyphs["unmapped"] / glyphs["total"] > 0.005):
        issues.append(issue("GARBLED_GLYPHS",
            f"{glyphs['unmapped']} characters can't be turned back into text (the font has "
            f"no character map). They show up as gibberish or vanish."))
    if glyphs["icons"]:
        issues.append(issue("ICON_GLYPHS",
            f"{glyphs['icons']} icon-font characters found. ATSs see them as junk symbols."))
    if glyphs["ligatures"]:
        issues.append(issue("LIGATURES",
            f"{glyphs['ligatures']} ligature characters found (such as ﬁ or ﬂ)."))

    tables = sum(count_tables(p) for p in pdf.pages)
    if tables:
        issues.append(issue("TABLE_LAYOUT", f"{tables} table(s) found."))

    page_lines = [[l for l in t.splitlines() if l.strip()] for t in engines["legacy"]]
    layout = {
        "gutters": gutters,
        "order_similarity": round(similarity, 3),
        "stream_similarity": round(stream_similarity, 3),
        "header_footer": header_footer_text(pdf, page_lines),
        "glyphs": glyphs,
        "tables": tables,
        "images": sum(len(p.images) for p in pdf.pages),
    }
    return layout, issues
