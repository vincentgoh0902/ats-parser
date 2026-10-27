"""Experience and education entries, each anchored on a date.

The ATS approach: find a date (range), take the one or two short lines around
it as the entry header, and treat what follows as bullets until the next
header. Title and company are told apart by keywords; when no keyword matches
the parser guesses by position, just as real parsers do.
"""

import re

from app.fields.dates import find_range, find_single

# (cid:N) is a bullet glyph the font couldn't map; it still marks a bullet.
BULLET_RE = re.compile(r"^\s*(?:[•●○◦▪▫■□►▸‣⁃∙·\-–*➢➤✓✔\uf0b7\uf0a7]|\(cid:\d+\))\s*")
SPLIT_RE = re.compile(r"\s+[|•·—–-]\s+|\s*[|•·]\s*|\s{2,}|\s+at\s+|\s+@\s+")
COMPANY_SUFFIX = re.compile(r",\s*(?:inc|llc|ltd|pte\.? ltd|corp|co|gmbh|plc)\b\.?", re.I)
TITLE_WORDS = re.compile(
    r"\b(?:engineer|developer|intern|internship|analyst|manager|scientist|designer|lead|"
    r"consultant|assistant|researcher|associate|director|specialist|officer|architect|"
    r"president|founder|co-founder|head|coordinator|tutor|teaching|administrator|"
    r"programmer|technician|executive|member|volunteer|trainee|fellow|representative|"
    r"advisor|strategist|vp|cto|ceo|sde|swe|student)\b", re.I)
DEGREE_WORDS = re.compile(
    r"\b(?:bachelor\w*|master\w*|b\.?\s?sc?|m\.?\s?sc?|b\.?\s?eng|m\.?\s?eng|b\.?a\.?|m\.?a\.?|"
    r"mba|ph\.?d|doctor\w*|diploma|associate\w*|degree|a[\s-]?levels?|o[\s-]?levels?|"
    r"high school diploma|honou?rs|minor|major|b\.?comp|bcomp|b\.?tech|m\.?tech)\b", re.I)
SCHOOL_WORDS = re.compile(
    r"\b(?:university|college|institute|school|polytechnic|academy|universiti|"
    r"junior college|nus|ntu|smu|mit)\b", re.I)
LOCATION_RE = re.compile(
    r"^(?:remote|hybrid|on-?site|singapore|hong kong|london|new york|san francisco|"
    r"[A-Z][A-Za-z .'-]+,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?: [A-Z][a-z]+)?))$", re.I)
GPA_RE = re.compile(r"\b(?:c?gpa|grade)\s*:?\s*([0-4]\.\d{1,2})(?:\s*/\s*([0-9.]+))?", re.I)
HEADER_MAX = 80


def is_bullet(line: str) -> bool:
    return bool(BULLET_RE.match(line))


def _merge_lone_bullets(lines: list[str]) -> list[str]:
    out, pending = [], None
    for line in lines:
        if BULLET_RE.fullmatch(line):
            pending = line.strip()
            continue
        out.append(f"{pending} {line}" if pending else line)
        pending = None
    return out


def _anchors(lines: list[str], allow_single: bool) -> list[int]:
    ranges = [i for i, l in enumerate(lines) if not is_bullet(l) and find_range(l)]
    if ranges or not allow_single:
        return ranges
    return [i for i, l in enumerate(lines) if not is_bullet(l) and find_single(l)]


def _bullets(lines: list[str]) -> list[str]:
    bullets = []
    for line in lines:
        if is_bullet(line) or not bullets:
            bullets.append(BULLET_RE.sub("", line).strip())
        else:
            bullets[-1] += " " + line.strip()
    return [b for b in bullets if b]


def _parts(header: list[str], anchor_line: str) -> tuple[list[str], str | None, str | None, str]:
    found = find_range(anchor_line)
    if found:
        m, start, end = found
    else:
        m, single = find_single(anchor_line)
        start, end = None, single
    date_text = m.group(0)
    parts = []
    for line in header:
        line = GPA_RE.sub(" ", line.replace(date_text, " "))
        line = re.sub(r"\b(?:expected|graduat\w*|class of)\b\s*:?", " ", line, flags=re.I)
        for piece in SPLIT_RE.split(line):
            piece = piece.strip(" ,|()")
            keep_whole = LOCATION_RE.match(piece) or COMPANY_SUFFIX.search(piece)
            for p in [piece] if keep_whole else re.split(r",\s+", piece):
                p = p.strip(" ,|()")
                if p and p not in parts:
                    parts.append(p)
    return parts, start, end, date_text


def _is_location(part: str) -> bool:
    """'Berkeley, CA' yes; 'University of California, Berkeley' no."""
    return bool(LOCATION_RE.match(part)) and not (
        SCHOOL_WORDS.search(part) or TITLE_WORDS.search(part) or DEGREE_WORDS.search(part))


def _pick(parts: list[str], pattern) -> str | None:
    return next((p for p in parts if pattern.search(p)), None)


def extract(lines: list[str], kind: str) -> tuple[list[dict], list[str]]:
    """Return (entries, header lines that got no date)."""
    lines = _merge_lone_bullets([l for l in lines if l.strip()])
    # A project or a degree often has one date ("Oct 2026"); a job has a range.
    anchors = _anchors(lines, allow_single=kind in ("education", "projects"))
    if not anchors:
        return [], [l for l in lines if not is_bullet(l)][:3]

    # Work out each entry's header span: the anchor plus up to two short lines before it.
    spans, prev_end = [], -1
    for i in anchors:
        start = i
        while (start - 1 > prev_end and i - (start - 1) <= 2 and not is_bullet(lines[start - 1])
               and len(lines[start - 1]) <= HEADER_MAX and not lines[start - 1].endswith(".")
               and not find_range(lines[start - 1])):
            start -= 1
        spans.append((start, i))
        prev_end = i

    entries = []
    for n, (start, anchor) in enumerate(spans):
        end = anchor
        header = lines[start:anchor + 1]
        body_end = spans[n + 1][0] if n + 1 < len(spans) else len(lines)
        parts, d_start, d_end, date_text = _parts(header, lines[anchor])
        # "Company\nJan 2020 - Present\nTitle": pull in one short line after the date.
        if len(parts) < 2 and end + 1 < body_end and not is_bullet(lines[end + 1]) \
                and len(lines[end + 1]) <= 60:
            end += 1
            parts, d_start, d_end, date_text = _parts(lines[start:end + 1], lines[anchor])
        # In a project header "Python, LangGraph" is a stack, not "City, Region".
        location = next((p for p in parts if _is_location(p)), None) if kind != "projects" else None
        # "San Francisco, CA" on its own line under the header.
        if kind != "projects" and not location and end + 1 < body_end and _is_location(lines[end + 1].strip()):
            end += 1
            location = lines[end].strip()
        body = lines[end + 1:body_end]

        rest = [p for p in parts if p != location]
        if kind == "education":
            school = _pick(rest, SCHOOL_WORDS)
            degree = _pick([p for p in rest if p != school], DEGREE_WORDS)
            others = [p for p in rest if p not in (school, degree)]
            school = school or (others.pop(0) if others else None)
            degree = degree or (others.pop(0) if others else None)
            gpa = GPA_RE.search(" ".join(lines[start:body_end]))
            entries.append({
                "school": school, "degree": degree, "location": location,
                "start": d_start, "end": d_end, "date_text": date_text,
                "gpa": gpa.group(0) if gpa else None, "details": _bullets(body),
            })
        else:
            title = _pick(rest, TITLE_WORDS)
            others = [p for p in rest if p != title]
            title = title or (others.pop(0) if others else None)
            company = others.pop(0) if others else None
            entries.append({
                "title": title, "company": company, "location": location,
                "start": d_start, "end": d_end, "date_text": date_text,
                "bullets": _bullets(body),
            })
    undated = [l for l in lines[:spans[0][0]] if not is_bullet(l)]
    return entries, undated
