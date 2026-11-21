import mimetypes
import os

import frappe
from frappe import _
from frappe.model.document import Document

from energyx_social.services.library import normalize_tags


class SocialMediaAsset(Document):
    def validate(self):
        self.tags = normalize_tags(self.tags)
        if not self.file:
            return
        mime = (mimetypes.guess_type(self.file.split("?")[0])[0] or "").lower()
        kind = mime.split("/")[0]
        if kind not in ("image", "video"):
            frappe.throw(_("Hanya file gambar atau video yang bisa disimpan di Media Library."))
        self.mime_type = mime
        self.media_type = kind.title()
        self.file_size_kb = _file_size_kb(self.file)


def _file_size_kb(file_url):
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        return 0
    try:
        path = frappe.get_doc("File", name).get_full_path()
        return int(os.path.getsize(path) / 1024) if os.path.exists(path) else 0
    except Exception:
        return 0
