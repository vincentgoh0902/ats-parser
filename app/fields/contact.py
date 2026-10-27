"""Name, email, phone, location and visible URLs."""

import os
import re

import phonenumbers

from app.fields.dates import RANGE_RE
from app.fields.sections import classify

PHONE_REGION = os.environ.get("DEFAULT_PHONE_REGION", "US")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
KNOWN_SITES = (r"linkedin\.com|github\.com|github\.io|gitlab\.com|behance\.net|dribbble\.com"
               r"|medium\.com|kaggle\.com|huggingface\.co|vercel\.app|netlify\.app|ts\.net"
               r"|leetcode\.com|stackoverflow\.com|x\.com|twitter\.com|substack\.com|notion\.site")
URL_RE = re.compile(
    rf"(?<![@\w.])(?:https?://\S+|www\.[^\s,;|)]+|(?:[\w-]+\.)*(?:{KNOWN_SITES})(?:/[^\s,;|)]*)?"
    r"|(?:[\w-]+\.)+(?:com|io|dev|me|org|net|ai|co|app|sg|xyz|tech|site)/[^\s,;|)]+)",
    re.I,
)
NAME_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ.'’-]*")
LOCATION_RE = re.compile(r"^[A-Z][A-Za-z .'-]+,\s*[A-Z][A-Za-z .'-]+$")
NOT_LOCATION = re.compile(r"\b(?:inc|llc|ltd|pte|corp|co|gmbh|plc)\b\.?", re.I)
SEPARATORS = re.compile(r"\s*[|•·◦▪●]\s*|\s{2,}")


def find_urls(text: str) -> list[str]:
    urls = []
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:)")
        if url not in urls:
            urls.append(url)
    return urls


def find_phone(text: str) -> str | None:
    for m in phonenumbers.PhoneNumberMatcher(text, PHONE_REGION):
        raw = m.raw_string
        if RANGE_RE.fullmatch(raw.strip()) or re.fullmatch(r"(?:19|20)\d{2}\D+(?:19|20)\d{2}", raw):
            continue
        return raw.strip()
    return None


def find_name(lines: list[str]) -> str | None:
    """First short line of plain words near the top. ATSs guess the same way."""
    for line in lines[:6]:
        part = SEPARATORS.split(line.strip())[0]
        words = part.split()
        if (2 <= len(words) <= 4 and len(part) <= 40 and not classify(part)
                and all(NAME_RE.fullmatch(w) for w in words)):
            return part
    return None


def find_location(lines: list[str], name: str | None) -> str | None:
    for line in lines[:10]:
        for part in SEPARATORS.split(line.strip()):
            part = part.strip()
            if (part != name and LOCATION_RE.match(part) and not NOT_LOCATION.search(part)
                    and len(part) <= 40):
                return part
    return None


def extract(top_lines: list[str], full_text: str) -> dict:
    emails = list(dict.fromkeys(EMAIL_RE.findall(full_text)))
    name = find_name(top_lines)
    return {
        "name": name,
        "email": emails[0] if emails else None,
        "other_emails": emails[1:],
        "phone": find_phone(full_text),
        "location": find_location(top_lines, name),
        "urls": [u for u in find_urls(full_text) if not EMAIL_RE.fullmatch(u)],
    }
