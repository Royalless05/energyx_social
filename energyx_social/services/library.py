"""Media Library: normalisasi tag + penyalinan file aset ke kolom Attach."""
import frappe


def normalize_tags(text) -> str:
    seen, out = set(), []
    for raw in (text or "").replace("\n", ",").replace(";", ",").split(","):
        tag = raw.strip().lstrip("#").lower()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return ", ".join(out)


def asset_file(asset):
    """URL file milik aset (None bila aset tidak ada)."""
    return frappe.db.get_value("Social Media Asset", asset, "file") if asset else None


def apply_asset(doc, link_field, attach_field, before_doc=None):
    """Salin file aset ke kolom Attach hanya bila Link berubah (agar unggahan manual tidak tertimpa)."""
    asset = doc.get(link_field)
    if not asset:
        return
    if before_doc is not None and before_doc.get(link_field) == asset:
        return
    file_url = asset_file(asset)
    if not file_url:
        frappe.throw(f"Aset {asset} tidak ditemukan di Media Library.")
    doc.set(attach_field, file_url)
