"""Skills: what's listed in the Skills section, plus taxonomy hits anywhere.

Commercial parsers match the whole resume against a large skills taxonomy.
app/match/taxonomy.py is a small version of that idea, enough to show which
keywords a search would find.
"""

import re

from app.fields.entries import BULLET_RE
from app.match.taxonomy import SKILLS


def from_section(lines: list[str]) -> list[str]:
    items = []
    for line in lines:
        line = BULLET_RE.sub("", line)
        if ":" in line[:40]:
            line = line.split(":", 1)[1]
        for item in re.split(r"[,;|•·]|\s{2,}|\s+and\s+", line):
            item = item.strip(" .()")
            if item and len(item) <= 40 and item.lower() not in (i.lower() for i in items):
                items.append(item)
    return items


def detect(full_text: str) -> list[str]:
    """Technical skills (not soft skills) the taxonomy finds anywhere in the text."""
    return [sk.name for sk in SKILLS if sk.category != "soft" and sk.pattern.search(full_text)]
