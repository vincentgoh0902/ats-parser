"""Resume date parsing: "Jan 2023 – Present", "01/2021 - 03/2022", "2019 – 2023"."""

import re

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    "spring": 3, "summer": 6, "fall": 9, "autumn": 9, "winter": 12,
}
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
          r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
          r"|spring|summer|fall|autumn|winter)\.?")
_YEAR = r"(?:19|20)\d{2}"
TOKEN = rf"(?:{_MONTH}\s*,?\s*'?{_YEAR}|(?:0?[1-9]|1[0-2])\s*[/.]\s*{_YEAR}|{_YEAR})"
_PRESENT = r"(?:present|current|now|today|ongoing|date)"
_SEP = r"\s*(?:-|–|—|―|to|until|till|~)\s*"

RANGE_RE = re.compile(rf"(?<![\w/])(?P<start>{TOKEN}){_SEP}(?P<end>{TOKEN}|{_PRESENT})\b", re.I)
SINGLE_RE = re.compile(rf"(?<![\w/])(?:(?:expected|graduat\w*|class of)\s*:?\s*)?(?P<date>{TOKEN})\b", re.I)


def normalize(token: str) -> str | None:
    """'Jan 2023' -> '2023-01', '2021' -> '2021', 'Present' -> 'present'."""
    t = token.strip().lower().rstrip(".")
    if re.fullmatch(_PRESENT, t):
        return "present"
    year = re.search(_YEAR, t)
    if not year:
        return None
    word = re.match(r"[a-z]*", t).group(0)
    month = MONTHS.get(word) or MONTHS.get(word[:3])
    if month:
        return f"{year.group(0)}-{month:02d}"
    num = re.match(r"(\d{1,2})\s*[/.]", t)
    if num:
        return f"{year.group(0)}-{int(num.group(1)):02d}"
    return year.group(0)


def find_range(text: str):
    """Return (match, start, end) for the first date range in text, or None."""
    m = RANGE_RE.search(text)
    if not m:
        return None
    return m, normalize(m.group("start")), normalize(m.group("end"))


def find_single(text: str):
    """Return (match, date) for the first standalone date in text, or None."""
    m = SINGLE_RE.search(text)
    if not m:
        return None
    return m, normalize(m.group("date"))
