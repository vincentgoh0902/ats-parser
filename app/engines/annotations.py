"""Engine C: link annotations, meaning clickable areas and where they point.

The URL behind a clickable word lives in an annotation, not in the text, so it
is read separately. The anchor text is whatever is drawn under the clickable
rectangle.
"""


def _anchor_text(page, x0, top, x1, bottom) -> str:
    """Characters whose centre lies inside the link rectangle.

    Link rectangles are often taller than the text (LaTeX's hyperref pads them),
    so the bottom of a large heading above can poke in. Counting any overlap would
    splice those letters into the anchor text; counting by centre doesn't.
    """
    def inside(obj):
        if obj.get("object_type") != "char":
            return True
        cx, cy = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return x0 <= cx <= x1 and top <= cy <= bottom
    return page.filter(inside).extract_text() or ""


def extract(pdf) -> list[dict]:
    links = []
    for page in pdf.pages:
        for link in page.hyperlinks:
            uri = link.get("uri")
            if not uri:
                continue
            if isinstance(uri, bytes):
                uri = uri.decode("utf-8", errors="replace")
            anchor = _anchor_text(page, link["x0"], link["top"], link["x1"], link["bottom"])
            links.append({
                "uri": uri.strip(),
                "anchor_text": " ".join(anchor.split()),
                "page": page.page_number,
            })
    return links
