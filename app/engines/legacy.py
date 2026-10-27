"""Engine A, the "simple parser": reads each line straight across the full page.

There is no column detection. Words that share a baseline are joined left to
right, so a sidebar and a main column end up interleaved line by line. This is
what position-sorting extractors (pdftotext -layout, PDFBox sorted by
position) feed to the cheaper ATSs.
"""

from app.engines.geometry import line_text, word_lines


def extract(pdf) -> list[str]:
    """Return the text of each page."""
    return ["\n".join(line_text(line) for line in word_lines(page)) for page in pdf.pages]
