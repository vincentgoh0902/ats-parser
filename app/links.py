"""Link audit: which links would a recruiter actually see, and do they work?

An ATS keeps the text of a resume. A URL written out as text survives; a URL
that exists only as a clickable annotation behind a word like "Portfolio" is
usually lost. The liveness check is optional and only ever connects to public
IP addresses, because this app runs inside a private network.
"""

import asyncio
import ipaddress
import os
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

from app.issues import issue

CHECK_TIMEOUT = float(os.environ.get("LINK_CHECK_TIMEOUT", "3"))
MAX_CHECKS = int(os.environ.get("LINK_CHECK_MAX", "20"))
MAX_REDIRECTS = 3
USER_AGENT = "Mozilla/5.0 (compatible; ats-parser link check)"
URLISH = re.compile(r"^(?:https?://|www\.)|^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$", re.I)


def norm(url: str) -> str:
    u = url.strip().lower()
    u = re.sub(r"^[a-z]+://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def audit(annotations: list[dict], visible_urls: list[str], full_text: str) -> tuple[list[dict], list[dict]]:
    """Return (links, issues). Every link appears once, keyed by normalized target."""
    visible = {norm(u): u for u in visible_urls}
    text_lower = full_text.lower()
    links, issues, seen = [], [], set()

    for a in annotations:
        uri, anchor = a["uri"], a["anchor_text"]
        scheme = urlsplit(uri).scheme.lower()
        if scheme == "mailto":
            target = uri.split(":", 1)[1].split("?")[0]
            shown = target.lower() in text_lower
            kind = "email"
        elif scheme == "tel":
            target = uri.split(":", 1)[1]
            shown = len(_digits(target)) >= 7 and _digits(target)[-7:] in _digits(full_text)
            kind = "phone"
        else:
            target = uri
            shown = norm(uri) in visible
            kind = "web"
        key = (kind, norm(target))
        if key in seen:
            continue
        seen.add(key)

        link = {"url": uri, "kind": kind, "anchor_text": anchor, "page": a["page"],
                "clickable": True, "visible_in_text": shown, "issue": None}
        if kind == "web" and anchor and URLISH.match(anchor) and norm(anchor) != norm(uri) \
                and not norm(uri).startswith(norm(anchor).rstrip(".")):
            link["issue"] = "LINK_MISMATCH"
            issues.append(issue("LINK_MISMATCH",
                f"The text says '{anchor}' but the link goes to {uri}.", url=uri))
        elif not shown and kind != "phone":
            link["issue"] = "LINK_HIDDEN"
            label = f"'{anchor}'" if anchor else "an area of the page"
            issues.append(issue("LINK_HIDDEN",
                f"{uri} is hidden behind {label}. The ATS text has no trace of it.", url=uri))
        links.append(link)

    for n, url in visible.items():
        if ("web", n) not in seen:
            seen.add(("web", n))
            links.append({"url": url, "kind": "web", "anchor_text": url, "page": None,
                          "clickable": False, "visible_in_text": True, "issue": None})
    return links, issues


class BlockedTarget(Exception):
    pass


async def _resolve_public(host: str, port: int) -> str:
    try:
        ip = ipaddress.ip_address(host)
        addrs = [str(ip)]
    except ValueError:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addrs = list(dict.fromkeys(info[4][0] for info in infos))
    if not addrs:
        raise BlockedTarget("does not resolve")
    for a in addrs:
        if not ipaddress.ip_address(a.split("%")[0]).is_global:
            raise BlockedTarget("points at a private address")
    return addrs[0]


async def _fetch(client: httpx.AsyncClient, url: str, method: str) -> httpx.Response:
    """One request, pinned to an IP we have checked (no DNS rebinding)."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedTarget("not an http(s) URL")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in (80, 443):
        raise BlockedTarget("non-standard port")
    ip = await _resolve_public(parts.hostname, port)
    ip_host = f"[{ip}]" if ":" in ip else ip
    pinned = parts._replace(netloc=f"{ip_host}:{port}").geturl()
    request = client.build_request(
        method, pinned,
        headers={"Host": parts.netloc.rsplit("@", 1)[-1], "User-Agent": USER_AGENT},
        extensions={"sni_hostname": parts.hostname},
    )
    return await client.send(request, stream=True)


async def check_one(client: httpx.AsyncClient, url: str) -> dict:
    if not urlsplit(url).scheme:
        url = "https://" + url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            resp = await _fetch(client, url, "HEAD")
            if resp.status_code in (403, 404, 405, 501):
                await resp.aclose()
                resp = await _fetch(client, url, "GET")  # some servers refuse HEAD
            await resp.aclose()
            if resp.is_redirect and "location" in resp.headers:
                url = urljoin(url, resp.headers["location"])
                continue
            code = resp.status_code
            if code == 999 or (code in (401, 403, 429) and "linkedin" in url):
                return {"status": code, "ok": None, "note": "site blocks automated checks"}
            return {"status": code, "ok": code < 400, "note": None}
        return {"status": None, "ok": False, "note": "too many redirects"}
    except BlockedTarget as e:
        return {"status": None, "ok": None, "note": f"not checked: {e}"}
    except socket.gaierror:
        return {"status": None, "ok": False, "note": "domain doesn't exist"}
    except httpx.TimeoutException:
        return {"status": None, "ok": False, "note": "timed out"}
    except (httpx.HTTPError, OSError) as e:
        return {"status": None, "ok": False, "note": type(e).__name__}


async def check_liveness(links: list[dict]) -> list[dict]:
    """Add a "check" field to web links and return LINK_DEAD issues."""
    targets = [l for l in links if l["kind"] == "web"][:MAX_CHECKS]
    sem = asyncio.Semaphore(5)
    timeout = httpx.Timeout(CHECK_TIMEOUT)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async def run(link):
            async with sem:
                link["check"] = await check_one(client, link["url"])
        await asyncio.gather(*(run(l) for l in targets))
    issues = []
    for l in targets:
        if l["check"]["ok"] is False:
            why = l["check"]["status"] or l["check"]["note"]
            issues.append(issue("LINK_DEAD", f"{l['url']} doesn't load ({why}).", url=l["url"]))
    return issues
