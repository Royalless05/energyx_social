"""Penjadwalan massal dari CSV/XLSX: tiap baris menjadi satu Social Post berstatus Draft."""
import csv
import io

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from energyx_social.services.hashtags import normalize_hashtags

MAX_ROWS = 200
TEMPLATE_HEADER = ["title", "caption", "media", "channels", "formats", "scheduled_at", "campaign", "hashtags"]
TEMPLATE_EXAMPLE = [
    "Promo Akhir Tahun", "Diskon 20% semua paket!", "https://example.com/promo.jpg",
    "Instagram:Brand IG; Facebook Page", "Instagram=Post", "2026-12-01 09:00", "", "#promo #diskon",
]


def parse_table(content: bytes, filename: str) -> list:
    """CSV (UTF-8, pemisah , atau ;) atau XLSX -> list of dict dengan header huruf kecil."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    if (filename or "").lower().endswith((".xlsx", ".xlsm")):
        from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file
        raw = read_xlsx_file_from_attached_file(fcontent=content)
    else:
        text = content.decode("utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        raw = list(csv.reader(io.StringIO(text), dialect))
    raw = [r for r in raw if any(str(c or "").strip() for c in r)]
    if not raw:
        return []
    header = [str(h or "").strip().lower() for h in raw[0]]
    return [{header[i]: str(v).strip() if v is not None else "" for i, v in enumerate(row) if i < len(header)} for row in raw[1:]]


def find_account(channel, label, accounts):
    pool = [a for a in accounts if a["channel"] == channel]
    if label:
        hit = [a for a in pool if a["account_name"].lower() == label.lower() or a["name"] == label]
        if not hit:
            raise ValueError(f"akun '{label}' tidak ditemukan/aktif untuk {channel}")
        return hit[0]["name"]
    if not pool:
        raise ValueError(f"tidak ada akun {channel} yang aktif")
    if len(pool) > 1:
        raise ValueError(f"{channel} punya {len(pool)} akun aktif; tulis 'Channel:Nama Akun'")
    return pool[0]["name"]


def parse_channels(spec, formats_spec, accounts, has_media, formats_map):
    out = []
    wanted = {}
    for part in (formats_spec or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            wanted[k.strip().lower()] = v.strip()
    for part in (spec or "").split(";"):
        part = part.strip()
        if not part:
            continue
        channel, _, label = part.partition(":")
        channel = next((c for c in formats_map if c.lower() == channel.strip().lower()), None)
        if not channel:
            raise ValueError(f"kanal tidak dikenal: '{part}'")
        fmt = wanted.get(channel.lower())
        options = formats_map[channel]
        if fmt:
            fmt = next((f for f in options if f.lower() == fmt.lower()), None)
            if not fmt:
                raise ValueError(f"format tidak tersedia untuk {channel} (pilihan: {', '.join(options)})")
        else:
            fmt = "Text" if (not has_media and "Text" in options) else options[0]
        out.append({"channel": channel, "account": find_account(channel, label.strip(), accounts),
                    "post_format": fmt, "active": 1})
    if not out:
        raise ValueError("kolom channels kosong")
    return out


def plan_row(data, accounts, formats_map) -> dict:
    title = (data.get("title") or "").strip()
    if not title:
        raise ValueError("title kosong")
    caption = data.get("caption") or ""
    tags = normalize_hashtags(data.get("hashtags") or "")
    if tags:
        caption = (caption.rstrip() + "\n\n" + tags).strip()
    media = (data.get("media") or "").strip()
    when = None
    if (data.get("scheduled_at") or "").strip():
        try:
            when = get_datetime(data["scheduled_at"].strip())
        except Exception:
            raise ValueError(f"scheduled_at tidak valid: '{data['scheduled_at']}' (format YYYY-MM-DD HH:MM)")
        if when <= now_datetime():
            raise ValueError("scheduled_at sudah lewat")
    campaign = (data.get("campaign") or "").strip()
    if campaign and not frappe.db.exists("Campaign", campaign):
        raise ValueError(f"Campaign '{campaign}' tidak ada")
    return {
        "doctype": "Social Post", "title": title[:140], "status": "Draft", "base_caption": caption, "base_media": media or None,
        "default_scheduled_at": when, "campaign_link": campaign or None,
        "channels": parse_channels(data.get("channels"), data.get("formats"), accounts, bool(media), formats_map),
    }


def run(content: bytes, filename: str, dry_run: bool = True) -> dict:
    from energyx_social.social_posting.doctype.social_post.social_post import FORMATS
    rows = parse_table(content, filename)
    if not rows:
        frappe.throw(_("File kosong atau header tidak terbaca."))
    if len(rows) > MAX_ROWS:
        frappe.throw(_("Maksimal {0} baris per file (ditemukan {1}).").format(MAX_ROWS, len(rows)))
    accounts = frappe.get_all("Social Account", filters={"parent": "Social Posting Settings", "enabled": 1},
                              fields=["name", "channel", "account_name"])
    created, errors = [], []
    for i, data in enumerate(rows, start=2):  # baris 1 = header
        try:
            frappe.db.savepoint("bulk_row")
            doc = frappe.get_doc(plan_row(data, accounts, FORMATS))
            if dry_run:
                doc.validate()
            else:
                doc.insert()
                created.append(doc.name)
            if dry_run:
                created.append(f"baris {i}")
        except Exception as exc:
            frappe.db.rollback(save_point="bulk_row")
            errors.append({"row": i, "title": data.get("title", ""), "error": str(exc)})
    return {"dry_run": bool(dry_run), "total": len(rows), "ok": len(created), "created": created, "errors": errors}
