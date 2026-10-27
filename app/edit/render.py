"""Render an edited resume to a PDF that parses cleanly.

The template follows this app's own issue list: one column, standard headings,
no tables, text boxes, header/footer content or icon glyphs, every link written
out as text, and a TrueType font with a ToUnicode map so the text layer extracts
letter for letter. Each job header keeps its dates on the same line, in the
format the date parser reads.
"""

import io
import unicodedata
from pathlib import Path

import reportlab
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.edit.model import Resume
from app.fields.contact import find_urls
from app.fields.dates import find_range
from app.fields.sections import classify, looks_like_heading

# Bitstream Vera ships with reportlab (permissive licence): Latin-1 and a bit more.
FONT_DIR = Path(reportlab.__file__).parent / "fonts"
REGULAR, BOLD = "ResumeSans", "ResumeSans-Bold"
pdfmetrics.registerFont(TTFont(REGULAR, str(FONT_DIR / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(BOLD, str(FONT_DIR / "VeraBd.ttf")))
_GLYPHS = pdfmetrics.getFont(REGULAR).face.charToGlyph

MARGIN = 42
BULLET_INDENT = 12
MIN_HEADER = 8.5
SIZE = {"name": 18, "contact": 9, "heading": 11, "header": 10, "body": 9.5}
LEADING = 1.25
SEP = " | "
DASH = " — "


# Look-alikes for characters Vera lacks, so "∼10 minutes" doesn't become "?10 minutes".
FALLBACK = {"∼": "~", "≈": "~", "−": "-", "‐": "-", "‑": "-", "→": "->", "←": "<-", "⇒": "=>",
            "≥": ">=", "≤": "<=", "×": "x", "✓": "", "✔": "", "★": "*", "\u00a0": " "}


def supported(text: str) -> str:
    """Characters the font can't draw would come out as empty boxes and as
    garbage in the text layer: use a look-alike, else '?' so it's visible."""
    out = []
    for ch in text:
        if ord(ch) in _GLYPHS or ch in " \t":
            out.append(ch)
        elif ch in FALLBACK and all(ord(c) in _GLYPHS for c in FALLBACK[ch]):
            out.append(FALLBACK[ch])
        else:
            plain = unicodedata.normalize("NFKD", ch)
            out.append(plain if plain != ch and all(ord(c) in _GLYPHS for c in plain) else "?")
    return "".join(out)


def _split(text: str, font: str, size: float, width: float, first_width: float) -> list[str]:
    """Wrap so that no continuation line reads as something else to a parser:
    a lone "Leadership" or "Skills" becomes a section heading, a date range
    becomes a new job. Narrow the column a little until that doesn't happen."""
    for step in range(8):
        shrink = 1 - 0.04 * step
        lines = simpleSplit(text, font, size, first_width * shrink) or [""]
        if len(lines) > 1:
            lines = lines[:1] + simpleSplit(" ".join(lines[1:]), font, size, width * shrink)
        if not any(classify(l) or looks_like_heading(l) or find_range(l) for l in lines[1:]):
            return lines
    return lines


def pack(items: list[str], sep: str, font: str, size: float, width: float) -> list[str]:
    """Join items into lines, breaking only between items (never inside an
    email, URL or "DSPy (Prompt Optimisation)")."""
    lines, current = [], ""
    for item in items:
        trial = f"{current}{sep}{item}" if current else item
        if current and pdfmetrics.stringWidth(trial, font, size) > width:
            lines.append(current + sep.rstrip())
            trial = item
        current = trial
    if current:
        lines.append(current)
    return lines


def visible_link(link: str) -> str:
    """A bare 'name.dev' isn't read as a link by parsers; 'https://name.dev' is."""
    if link and find_urls(link) != [link] and not link.startswith(("http://", "https://")):
        return "https://" + link
    return link


class Page:
    """Draws lines top-down in one column and starts new pages as needed."""

    def __init__(self, c: canvas.Canvas, size):
        self.c, (self.w, self.h) = c, size
        self.left, self.right = MARGIN, self.w - MARGIN
        self.y = self.h - MARGIN

    def _room(self, height: float):
        if self.y - height < MARGIN:
            self.c.showPage()
            self.y = self.h - MARGIN

    def line(self, text: str, size: float, font: str = REGULAR, right_text: str | None = None,
             indent: float = 0, after: float = 0):
        self._room(size * LEADING)
        self.y -= size
        self.c.setFont(font, size)
        self.c.drawString(self.left + indent, self.y, supported(text))
        if right_text:
            self.c.drawRightString(self.right, self.y, supported(right_text))
        self.y -= size * (LEADING - 1) + after

    def wrapped(self, text: str, size: float, font: str = REGULAR, indent: float = 0,
                first_prefix: str = "", right_reserve: float = 0, right_text: str | None = None):
        """Wrap to the column. A bullet gets a hanging indent: '•' on the first
        line, continuation lines lined up with the text (no bullet, so the
        parser joins them back into one bullet)."""
        width = self.right - self.left - indent - BULLET_INDENT * bool(first_prefix)
        # Only the first line shares room with the dates.
        lines = _split(supported(text), font, size, width, width - right_reserve)
        for i, part in enumerate(lines):
            if first_prefix:
                self._room(size * LEADING)
                if i == 0:
                    self.c.setFont(font, size)
                    self.c.drawString(self.left + indent, self.y - size, first_prefix)
                self.line(part, size, font, indent=indent + BULLET_INDENT)
            else:
                self.line(part, size, font, indent=indent, right_text=right_text if i == 0 else None)

    def gap(self, points: float):
        self.y -= points


def _header(p: Page, left: str, dates: str):
    """'Title — Company' in bold with the dates right-aligned on the same line.
    A long header shrinks a little before it wraps: a second header line under
    the date is easily read as the start of the bullets."""
    size = SIZE["header"]
    while True:
        reserve = (pdfmetrics.stringWidth(supported(dates), BOLD, size) + 16) if dates else 0
        fits = pdfmetrics.stringWidth(supported(left), BOLD, size) <= p.right - p.left - reserve
        if fits or size <= MIN_HEADER:
            break
        size -= 0.25
    p.wrapped(left, size, BOLD, right_reserve=reserve, right_text=dates or None)


def _closed(bullets: list[str], last_entry: bool) -> list[str]:
    """Parsers take up to two short lines above a date as the next entry's
    header, so the wrapped tail of a bullet ("three regional teams") would
    become the next job's company. A line ending in a full stop is never taken."""
    if last_entry or not bullets or bullets[-1].endswith((".", "!", "?")):
        return bullets
    return [*bullets[:-1], bullets[-1] + "."]


def render(resume: Resume) -> bytes:
    buf = io.BytesIO()
    size = A4 if resume.page_size == "a4" else LETTER
    c = canvas.Canvas(buf, pagesize=size, invariant=1)
    c.setTitle(resume.contact.name or "Resume")
    c.setAuthor(resume.contact.name or "")
    c.setCreator("ats-parser")
    p = Page(c, size)

    ct = resume.contact
    if ct.name:
        p.line(ct.name, SIZE["name"], BOLD, after=4)
    contact = [supported(x) for x in (ct.email, ct.phone, ct.location, *map(visible_link, ct.links)) if x]
    for line in pack(contact, SEP, REGULAR, SIZE["contact"], p.right - p.left):
        p.line(line.removesuffix(SEP.rstrip()).rstrip(), SIZE["contact"])

    for s in resume.sections:
        if not (s.text or s.entries or s.schools or s.items):
            continue
        p.gap(6)
        p.line(s.heading.upper(), SIZE["heading"], BOLD, after=3)
        if s.kind == "text":
            p.wrapped(s.text, SIZE["body"])
        elif s.kind == "entries":
            for i, e in enumerate(s.entries):
                if i:
                    p.gap(4)
                _header(p, DASH.join(x for x in (e.title, e.org) if x), e.dates)
                if e.location:
                    p.line(e.location, SIZE["body"])
                for b in _closed(e.bullets, last_entry=i == len(s.entries) - 1):
                    p.wrapped(b, SIZE["body"], first_prefix="•")
        elif s.kind == "education":
            for i, e in enumerate(s.schools):
                if i:
                    p.gap(4)
                # School and dates, then degree: with a single part on the date
                # line the parser pulls in the line below as the degree. The
                # location goes after, where it is read as one.
                _header(p, e.school, e.dates)
                second = ", ".join(x for x in (e.degree, e.gpa) if x)
                if second:
                    p.wrapped(second, SIZE["body"])
                if e.location:
                    p.line(e.location, SIZE["body"])
                for d in _closed(e.details, last_entry=i == len(s.schools) - 1):
                    p.wrapped(d, SIZE["body"], first_prefix="•")
        elif s.kind == "skills":
            for line in pack([supported(x) for x in s.items], ", ", REGULAR, SIZE["body"], p.right - p.left):
                p.line(line, SIZE["body"])
        elif s.kind == "list":
            for item in s.items:
                p.wrapped(item, SIZE["body"], first_prefix="•")
    c.showPage()
    c.save()
    return buf.getvalue()
