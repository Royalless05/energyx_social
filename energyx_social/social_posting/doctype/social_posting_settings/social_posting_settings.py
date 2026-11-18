import frappe
from frappe import _
from frappe.model.document import Document

IDENTITY_FIELDS = ("channel", "account_id", "api_version", "app_id")
SECRET_FIELDS = ("app_secret", "access_token", "refresh_token")


def _is_masked(value) -> bool:
    """Password field yang tidak diubah user datang sebagai '*****'."""
    return bool(value) and set(value) == {"*"}


class SocialPostingSettings(Document):
    def validate(self):
        if self.public_base_url:
            self.public_base_url = self.public_base_url.strip().rstrip("/")
            if not self.public_base_url.startswith("https://"):
                frappe.throw(_("Public Base URL harus diawali https://"))

        seen = set()
        for row in self.accounts:
            key = (row.channel, (row.account_id or "").strip())
            if key in seen:
                frappe.throw(_("Row {0}: akun {1} duplikat.").format(row.idx, row.account_id))
            seen.add(key)
            self._guard_enabled(row)

    def _guard_enabled(self, row):
        """`enabled` hanya boleh di-set oleh Test Connection. Ganti kredensial/identitas => nonaktif lagi."""
        old = frappe.db.get_value("Social Account", row.name, ("enabled",) + IDENTITY_FIELDS, as_dict=True) \
            if not row.is_new() else None
        if not old:
            row.enabled = 0
            return
        changed = any((row.get(f) or "") != (old.get(f) or "") for f in IDENTITY_FIELDS)
        changed = changed or any(row.get(f) and not _is_masked(row.get(f)) for f in SECRET_FIELDS)
        row.enabled = 0 if changed else old.enabled
        if changed and old.enabled:
            row.connection_status = _("Kredensial berubah - jalankan Test Connection ulang.")
