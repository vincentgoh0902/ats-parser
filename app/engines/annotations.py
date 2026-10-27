"""Engine C: link annotations, meaning clickable areas and where they point.

The URL behind a clickable word lives in an annotation, not in the text, so it
is read separately. The anchor text is whatever is drawn under the clickable
rectangle.
"""


def extract(pdf) -> list[dict]:
    links = []
    for page in pdf.pages:
        for link in page.hyperlinks:
            uri = link.get("uri")
            if not uri:
                continue
            if isinstance(uri, bytes):
                uri = uri.decode("utf-8", errors="replace")
            bbox = (
                max(link["x0"], page.bbox[0]),
                max(link["top"], page.bbox[1]),
                min(link["x1"], page.bbox[2]),
                min(link["bottom"], page.bbox[3]),
            )
            anchor = ""
            if bbox[0] < bbox[2] and bbox[1] < bbox[3]:
                anchor = page.crop(bbox).extract_text() or ""
            links.append({
                "uri": uri.strip(),
                "anchor_text": " ".join(anchor.split()),
                "page": page.page_number,
            })
    return links
