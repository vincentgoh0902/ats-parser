"""Catalogue of everything the report can flag."""

CATALOGUE = {
    "NO_TEXT_LAYER": ("high",
        "Export the resume from Word or Google Docs as a PDF (File > Download > PDF). "
        "Don't scan it, photograph it, or export it as an image."),
    "MULTI_COLUMN": ("high",
        "Use a single column. Put the sidebar content (skills, contact, links) in the "
        "main flow, under its own headings."),
    "GARBLED_GLYPHS": ("high",
        "Use a standard font (Calibri, Arial, Garamond, Helvetica) and export again. "
        "Avoid 'print to PDF' from design tools, which can drop the character map."),
    "ORDER_MISMATCH": ("medium",
        "Text boxes or floating shapes are being read out of order. Replace them with "
        "normal paragraphs."),
    "CONTACT_IN_HEADER": ("medium",
        "Move your email and phone number into the body of the page. Many ATSs throw "
        "away the header and footer."),
    "LINK_HIDDEN": ("medium",
        "Show the URL itself as the link text (e.g. 'github.com/you'), not a word like "
        "'Portfolio'. Recruiters often see plain text only."),
    "LINK_MISMATCH": ("medium",
        "The visible URL and the actual link target differ. Make them the same."),
    "LINK_DEAD": ("medium",
        "Fix or remove the link. A recruiter who clicks it will see an error."),
    "UNKNOWN_HEADING": ("medium",
        "Use a standard heading (Experience, Education, Skills, Projects) so the "
        "parser puts the content in the right field."),
    "NO_NAME": ("medium",
        "Put your name alone on the very first line of the page, in the main column. "
        "Parsers take the name from the top of the text."),
    "NO_EXPERIENCE": ("medium",
        "No Experience section was found. Use a heading such as 'Experience' or "
        "'Work Experience'."),
    "DATE_FORMAT": ("low",
        "Write dates as 'Jan 2023 – Present' or '01/2023 – 06/2024', on the same line "
        "as the job title or company."),
    "TABLE_LAYOUT": ("low",
        "Tables can be flattened in odd orders. Use plain paragraphs and tab stops."),
    "ICON_GLYPHS": ("low",
        "Icons (phone, mail, LinkedIn) come out as junk characters. Use words like "
        "'Email:' instead, or nothing."),
    "LIGATURES": ("low",
        "Ligature characters (ﬁ, ﬂ) can break keyword matching, e.g. 'certiﬁed'. "
        "Turn off ligatures in the font settings before exporting."),
}

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def issue(code: str, message: str, **extra) -> dict:
    severity, fix = CATALOGUE[code]
    return {"code": code, "severity": severity, "message": message, "fix": fix, **extra}
