"""Engine S: raw content-stream order, the order the text was written into the PDF.

Extractors that don't sort by position (Apache Tika's default PDF parser, many
older pipelines) emit text in this order. Word and Google Docs write it in
reading order. Design tools often don't: text boxes come out in the order they
were created.
"""


def _page_text(page) -> str:
    lines, current, prev = [], "", None
    for c in page.chars:
        if prev is not None:
            new_line = abs(c["top"] - prev["top"]) > 3 or c["x0"] < prev["x0"] - 1
            if new_line:
                lines.append(current)
                current = ""
            elif c["x0"] - prev["x1"] > c["size"] * 0.2 and not current.endswith(" "):
                current += " "
        if not (c["text"] == " " and current.endswith(" ")):
            current += c["text"]
        prev = c
    if current:
        lines.append(current)
    return "\n".join(l.strip() for l in lines if l.strip())


def extract(pdf) -> list[str]:
    return [_page_text(page) for page in pdf.pages]
