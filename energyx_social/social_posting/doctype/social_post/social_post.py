import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from energyx_social.services.media import RULES

FORMATS = {
    "Instagram": ["Post", "Reel", "Story"],
    "Facebook Page": ["Photo", "Video", "Text"],
    "YouTube": ["Short", "Video"],
    "TikTok": ["Video", "Photo"],
}
CAPTION_LIMITS = {"Instagram": 2200, "Facebook Page": 63206, "YouTube": 5000, "TikTok": 2200}

# Diisi sistem (publisher/jobs/approval) -- tidak boleh dikirim dari client.
SYSTEM_ROW_FIELDS = (
    "status", "remote_id", "permalink", "error_log", "published_on",
    "attempts", "provider_state", "scheduled_at",
)
CONTENT_LOCKED_FIELDS = ("title", "base_media", "base_caption")
PUBLISH_PHASE = ("Approved", "Publishing", "Partial")
MANAGER_ROLES = {"Social Manager", "System Manager"}


class SocialPost(Document):
    def validate(self):
        if self.is_new():
            self.requested_by = frappe.session.user
        self._protect_system_fields()
        self._validate_rows()
        self._lock_content()

    def before_save(self):
        self._handle_transitions()
        self._sync_schedule()

    # ------------------------------------------------------------------ guards
    def _protect_system_fields(self):
        before = self.get_doc_before_save()
        old_rows = {r.name: r for r in before.channels} if before else {}
        for row in self.channels:
            old = old_rows.get(row.name)
            for f in SYSTEM_ROW_FIELDS:
                row.set(f, old.get(f) if old else None)
            if not old:
                row.status = "Queued"
                row.attempts = 0
        for f in ("requested_by", "approved_by", "approved_on"):
            if before:
                self.set(f, before.get(f))
            elif f != "requested_by":
                self.set(f, None)

    def _validate_rows(self):
        strict = self.status != "Draft"
        if strict and not self.channels:
            frappe.throw(_("Tambahkan minimal satu kanal."))
        for row in self.channels:
            fmts = FORMATS.get(row.channel)
            if not fmts:
                frappe.throw(_("Row {0}: kanal tidak valid.").format(row.idx))
            row.post_format = row.post_format or fmts[0]
            if row.post_format not in fmts:
                frappe.throw(_("Row {0}: format {1} tidak tersedia untuk {2} (pilihan: {3}).").format(
                    row.idx, row.post_format, row.channel, ", ".join(fmts)))
            if row.first_comment and row.channel not in ("Instagram", "Facebook Page"):
                frappe.throw(_("Row {0}: First Comment hanya untuk Instagram/Facebook.").format(row.idx))

            acc = frappe.db.get_value(
                "Social Account", row.account, ["channel", "account_name", "enabled", "parent"], as_dict=True
            )
            if not acc or acc.parent != "Social Posting Settings":
                frappe.throw(_("Row {0}: akun tidak ditemukan.").format(row.idx))
            if acc.channel != row.channel:
                frappe.throw(_("Row {0}: akun {1} bukan akun {2}.").format(row.idx, acc.account_name, row.channel))
            row.account_label = acc.account_name
            if strict and row.active and not acc.enabled:
                frappe.throw(_("Row {0}: akun {1} belum aktif (jalankan Test Connection di Social Posting Settings).")
                             .format(row.idx, acc.account_name))

            rule = RULES.get((row.channel, row.post_format))
            media = row.media_override or self.base_media
            if strict and rule and rule["kinds"] and not media:
                frappe.throw(_("Row {0}: media wajib untuk {1} / {2}.").format(row.idx, row.channel, row.post_format))
            caption = row.caption_override or self.base_caption or ""
            if len(caption) > CAPTION_LIMITS[row.channel]:
                frappe.throw(_("Row {0}: caption melebihi {1} karakter untuk {2}.").format(
                    row.idx, CAPTION_LIMITS[row.channel], row.channel))
            if row.channel == "YouTube" and len(self.title or "") > 100:
                frappe.throw(_("Judul maksimal 100 karakter untuk YouTube."))

    def _lock_content(self):
        before = self.get_doc_before_save()
        if not before or before.status in ("Draft", "Pending Approval"):
            return
        if "System Manager" in frappe.get_roles():
            return
        for f in CONTENT_LOCKED_FIELDS:
            if self.get(f) != before.get(f):
                frappe.throw(_("Konten tidak bisa diubah setelah disetujui. Kembalikan ke Draft terlebih dahulu."))

    # ------------------------------------------------------------------ workflow side effects
    def _handle_transitions(self):
        before = self.get_doc_before_save()
        if not before or before.status == self.status:
            return
        if before.status == "Pending Approval" and self.status == "Approved":
            if not MANAGER_ROLES & set(frappe.get_roles()):
                frappe.throw(_("Hanya Social Manager yang dapat menyetujui."), frappe.PermissionError)
            self.approved_by = frappe.session.user
            self.approved_on = now_datetime()
        elif self.status == "Draft":  # reject / reopen
            self.approved_by = None
            self.approved_on = None
            for row in self.channels:
                if row.status in ("Queued", "Scheduled", "On Hold"):
                    row.status = "Queued"
                    row.scheduled_at = None

    def _sync_schedule(self):
        """Approved -> kanal berjadwal = Scheduled, tanpa jadwal = Queued (siap Publish Now)."""
        if self.status not in PUBLISH_PHASE:
            return
        for row in self.channels:
            if not row.active or row.status not in ("Queued", "Scheduled"):
                continue
            when = row.scheduled_at_override or self.default_scheduled_at
            row.scheduled_at = when
            row.status = "Scheduled" if when else "Queued"
