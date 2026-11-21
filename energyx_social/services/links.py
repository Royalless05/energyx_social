"""UTM builder + link shortener. Link di caption ditulis ulang saat terbit (draft tetap terbaca apa adanya)."""
import random
import re
import string
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import frappe

URL_RE = re.compile(r"https?://[^\s<>\"']+")
TRAILING = ".,;:!?)]}"
SOURCES = {"Instagram": "instagram", "Facebook Page": "facebook", "YouTube": "youtube",
           "TikTok": "tiktok", "LinkedIn": "linkedin"}
ALPHABET = string.ascii_letters + string.digits
MODES = ("None", "UTM only", "UTM + Short link")
SHORT_DOCTYPE = "Social Short Link"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:60]


def add_utm(url: str, params: dict) -> str:
    """Tambahkan parameter UTM yang belum ada (UTM manual milik user tidak ditimpa)."""
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    existing = {k for k, _ in query}
    for key, value in params.items():
        if value and key not in existing:
            query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def split_trailing(raw: str):
    url = raw.rstrip(TRAILING)
    return url, raw[len(url):]


def rewrite_urls(text: str, fn) -> str:
    """Ganti tiap URL di teks dengan fn(url); tanda baca di ujung dipertahankan."""
    def sub(match):
        url, tail = split_trailing(match.group(0))
        return fn(url) + tail
    return URL_RE.sub(sub, text or "")


def resolve_mode(post_mode: str, default_mode: str) -> str:
    mode = post_mode if post_mode and post_mode != "Default" else (default_mode or "None")
    return mode if mode in MODES else "None"


def utm_params(channel, post_format, title, campaign_link=None, utm_campaign=None):
    return {
        "utm_source": SOURCES.get(channel, slugify(channel)),
        "utm_medium": "social",
        "utm_campaign": slugify(utm_campaign or campaign_link or title) or "social",
        "utm_content": slugify(post_format),
    }


def _base_url() -> str:
    base = frappe.db.get_single_value("Social Posting Settings", "public_base_url") or frappe.utils.get_url()
    return base.rstrip("/")


def new_code(exists, length=7, rng=random) -> str:
    for _ in range(20):
        code = "".join(rng.choice(ALPHABET) for _ in range(length))
        if not exists(code):
            return code
    return new_code(exists, length + 1, rng)


def short_url_for(code: str) -> str:
    return f"{_base_url()}/s/{code}"


def get_or_create_short(post, channel, target_url, destination):
    """Idempoten: publish ulang (retry) memakai kode yang sama untuk post+kanal+tujuan yang sama."""
    found = frappe.db.get_value(SHORT_DOCTYPE, {"post": post, "channel": channel, "target_url": target_url}, "code")
    if found:
        return found
    doc = frappe.get_doc({
        "doctype": SHORT_DOCTYPE, "target_url": target_url, "post": post, "channel": channel,
        "destination": destination, "enabled": 1,
    }).insert(ignore_permissions=True)
    return doc.code


def track_text(text, *, post, channel, post_format, title, mode, campaign_link=None, utm_campaign=None) -> str:
    """Tulis ulang semua URL di teks sesuai mode. Mode 'None' = teks apa adanya."""
    if not text or mode == "None":
        return text or ""
    params = utm_params(channel, post_format, title, campaign_link, utm_campaign)
    own_prefix = _base_url() + "/s/"

    def handle(url):
        if url.startswith(own_prefix):
            return url
        tagged = add_utm(url, params)
        if mode == "UTM + Short link":
            return short_url_for(get_or_create_short(post, channel, url, tagged))
        return tagged
    return rewrite_urls(text, handle)
