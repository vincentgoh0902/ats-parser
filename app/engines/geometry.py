"""Shared geometry: words grouped into lines, and column gutter detection."""

BIN = 2.0           # points per bin when scanning for a column gutter
MIN_GUTTER = 8.0    # narrowest whitespace strip that counts as a gutter
MIN_SPLIT_LINES = 5
WIDE_GAP = 20.0     # a gap this wide (right-aligned dates, tab stops) becomes 3 spaces


def word_lines(page, y_tolerance=3.0) -> list[list[dict]]:
    """Group the page's words into lines by baseline, each sorted left to right."""
    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
    words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
    lines, current, current_top = [], [], None
    for w in words:
        if current and abs(w["top"] - current_top) > y_tolerance:
            lines.append(current)
            current = []
        if not current:
            current_top = w["top"]
        current.append(w)
    if current:
        lines.append(current)
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def line_text(words: list[dict]) -> str:
    out = ""
    for i, w in enumerate(words):
        if i:
            out += "   " if w["x0"] - words[i - 1]["x1"] > WIDE_GAP else " "
        out += w["text"]
    return out


def tables(page) -> list:
    """pdfplumber's ruled tables on this page, computed once per page."""
    if not hasattr(page, "_ats_tables"):
        page._ats_tables = page.find_tables()
    return page._ats_tables


def _inside_table(page, x: float, lines) -> bool:
    """True if the whitespace at x is just the border between table cells."""
    for t in tables(page):
        x0, top, x1, bottom = t.bbox
        inside = [l for l in lines if x0 <= x <= x1 and top <= l[0]["top"] <= bottom]
        if len(inside) >= len(lines) / 2:
            return True
    return False


def find_gutter(page, lines=None) -> float | None:
    """Return the x position of a column gutter, or None for a single column.

    For each candidate x, a line is "split" if it has words on both sides of x
    and none covering it, and "crossing" if a word covers x. Right-aligned dates
    in a single-column resume split a few lines, but the bullet lines cross, so
    only a real side-by-side layout gets a high split ratio all the way down.
    """
    lines = lines if lines is not None else word_lines(page)
    if len(lines) < MIN_SPLIT_LINES:
        return None
    lo, hi = page.width * 0.15, page.width * 0.85
    run_start = None
    x = lo
    while x <= hi + BIN:
        split = crossing = 0
        for line in lines:
            if any(w["x0"] <= x <= w["x1"] for w in line):
                crossing += 1
            elif any(w["x1"] < x for w in line) and any(w["x0"] > x for w in line):
                split += 1
        is_gutter = x <= hi and split >= MIN_SPLIT_LINES and split / (split + crossing) >= 0.6
        if is_gutter and run_start is None:
            run_start = x
        elif not is_gutter and run_start is not None:
            mid = (run_start + x) / 2
            if x - run_start >= MIN_GUTTER and not _inside_table(page, mid, lines):
                return mid
            run_start = None
        x += BIN
    return None
