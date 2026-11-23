"""Website freshness check + public email extraction."""
from __future__ import annotations

import datetime as dt
import re
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

UA = {"User-Agent": "Mozilla/5.0 (compatible; SiteCheck/1.0)"}
NOW_YEAR = dt.date.today().year

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
COPYRIGHT_RE = re.compile(r"(?:©|&copy;|&#169;|copyright)\s*(?:\d{4}\s*(?:-|–|&ndash;|to)\s*)?((?:19|20)\d{2})", re.I)
LASTMOD_RE = re.compile(r"<lastmod>\s*((?:19|20)\d{2})", re.I)
YEAR_RE = re.compile(r"\b(20[0-3]\d)\b")
LINK_RE = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
CONTACT_HINTS = ("contact", "about", "connect", "reach", "impressum", "info")
BAD_EMAIL_PARTS = (
    "example.", "sentry", "wixpress", "domain.com", "yourname", "email.com", "@2x", ".png",
    ".jpg", ".jpeg", ".gif", ".webp", ".svg", "godaddy", "squarespace.com", "noreply", "no-reply",
)


def _get(url: str, timeout: int = 15):
    try:
        r = requests.get(url, headers=UA, timeout=timeout, allow_redirects=True)
        return r
    except requests.RequestException:
        return None


def _text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", unescape(re.sub(r"(?s)<[^>]+>", " ", html))).strip()


def _cf_decode(hexstr: str) -> str:
    key = int(hexstr[:2], 16)
    return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))


def extract_emails(html: str) -> set[str]:
    found = set()
    for m in re.findall(r'data-cfemail="([0-9a-fA-F]+)"', html):
        try:
            found.add(_cf_decode(m))
        except ValueError:
            pass
    decoded = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", unescape(html), flags=re.I)
    for m in re.findall(r"mailto:([^\"'?>\s]+)", decoded, re.I):
        found.add(m)
    found.update(EMAIL_RE.findall(decoded))
    clean = set()
    for e in found:
        e = e.strip().strip(".").lower()
        if EMAIL_RE.fullmatch(e) and not any(b in e for b in BAD_EMAIL_PARTS):
            clean.add(e)
    return clean


def rank_emails(emails: set[str], site_url: str | None) -> list[str]:
    host = urlparse(site_url).hostname.removeprefix("www.") if site_url else ""
    pref = ("info@", "hello@", "contact@", "owner@", "hi@", "office@")

    def score(e: str):
        return (not (host and e.endswith("@" + host)), not e.startswith(pref), e)

    return sorted(emails, key=score)


def analyze(url: str, stale_years: int = 2) -> dict:
    """Return freshness signals, a stale/broken verdict, emails and page text."""
    res = {
        "url": url, "reachable": False, "https": url.lower().startswith("https"),
        "mobile_viewport": None, "copyright_year": None, "sitemap_year": None,
        "last_modified_year": None, "latest_year": None, "verdict": "unknown",
        "reasons": [], "emails": [], "text": "",
    }
    r = _get(url)
    if r is None or r.status_code >= 400 or len(r.text) < 200:
        res["verdict"] = "broken"
        res["reasons"].append(f"site unreachable or empty (status {getattr(r, 'status_code', 'n/a')})")
        return res

    html = r.text
    final = r.url
    res.update(reachable=True, https=final.lower().startswith("https"))
    res["mobile_viewport"] = bool(re.search(r'<meta[^>]+name=["\']viewport', html, re.I))
    text = _text(html)
    res["text"] = text[:4000]

    if re.search(r"domain (is )?for sale|parked free|this domain may be for sale|buy this domain", text, re.I):
        res["verdict"] = "broken"
        res["reasons"].append("domain looks parked / for sale")
        return res

    cy = [int(y) for y in COPYRIGHT_RE.findall(html)]
    res["copyright_year"] = max(cy) if cy else None
    if lm := r.headers.get("Last-Modified"):
        try:
            res["last_modified_year"] = parsedate_to_datetime(lm).year
        except (TypeError, ValueError):
            pass
    base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
    for sm in ("/sitemap.xml", "/wp-sitemap.xml", "/sitemap_index.xml"):
        s = _get(base + sm, timeout=10)
        if s is not None and s.status_code == 200 and "<lastmod" in s.text:
            years = [int(y) for y in LASTMOD_RE.findall(s.text)]
            if years:
                res["sitemap_year"] = max(years)
                break

    # Sitemap <lastmod> is the strongest signal. A Last-Modified header is often just "now"
    # on dynamic sites, so it only counts when it is old. Copyright year comes next.
    lm_old = res["last_modified_year"] if (res["last_modified_year"] or NOW_YEAR) < NOW_YEAR else None
    if res["sitemap_year"] and res["sitemap_year"] <= NOW_YEAR:
        latest = res["sitemap_year"]
    elif res["copyright_year"] or lm_old:
        latest = max(y for y in (res["copyright_year"], lm_old) if y)
    else:
        ty = [int(y) for y in YEAR_RE.findall(text) if int(y) <= NOW_YEAR]
        latest = max(ty) if ty else None
    res["latest_year"] = latest

    if latest and latest <= NOW_YEAR - stale_years:
        res["verdict"] = "stale"
        res["reasons"].append(f"newest update signal is {latest}")
    elif latest is None and (not res["mobile_viewport"] or not res["https"]):
        res["verdict"] = "stale"
    else:
        res["verdict"] = "fresh" if latest else "unknown"
    if not res["mobile_viewport"]:
        res["reasons"].append("no mobile viewport (not mobile-friendly)")
    if not res["https"]:
        res["reasons"].append("no HTTPS")

    # Emails: homepage + a few contact/about pages
    emails = extract_emails(html)
    links = []
    for href in LINK_RE.findall(html):
        full = urljoin(final, href)
        if urlparse(full).netloc == urlparse(final).netloc and any(h in full.lower() for h in CONTACT_HINTS):
            if full not in links:
                links.append(full)
    for link in links[:4]:
        p = _get(link, timeout=10)
        if p is not None and p.status_code == 200:
            emails |= extract_emails(p.text)
    res["emails"] = rank_emails(emails, final)
    return res
