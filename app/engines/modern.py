"""Engine B, the "smart parser": column-aware reading order.

Lines are read straight across (so a right-aligned date stays with its job
title) unless the page has a column gutter. In that case each run of lines
that doesn't cross the gutter is read as left column, then right column.
Full-width lines such as a name banner stay where they are. Good commercial
parsers behave like this.
"""

from app.engines.geometry import find_gutter, line_text, word_lines


def _page_text(page) -> str:
    lines = word_lines(page)
    gutter = find_gutter(page, lines)
    if gutter is None:
        return "\n".join(line_text(l) for l in lines)
    out, left, right = [], [], []

    def flush():
        out.extend(left + right)
        left.clear()
        right.clear()

    for line in lines:
        if any(w["x0"] <= gutter <= w["x1"] for w in line):
            flush()
            out.append(line_text(line))
            continue
        l_words = [w for w in line if w["x1"] < gutter]
        r_words = [w for w in line if w["x0"] > gutter]
        if l_words:
            left.append(line_text(l_words))
        if r_words:
            right.append(line_text(r_words))
    flush()
    return "\n".join(out)


def extract(pdf) -> list[str]:
    """Return the text of each page."""
    return [_page_text(page) for page in pdf.pages]
