import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from energyx_social.services.library import apply_asset
from energyx_social.services.media import RULES, multi_limits

FORMATS = {
    "Instagram": ["Post", "Reel", "Story", "Carousel"],
    "Facebook Page": ["Photo", "Video", "Text", "Album"],
    "YouTube": ["Short", "Video"],
    "TikTok": ["Video", "Photo"],
    "LinkedIn": ["Text", "Photo", "Video"],
}
CAPTION_LIMITS = {"Instagram": 2200, "Facebook Page": 63206, "YouTube": 5000, "TikTok": 2200, "LinkedIn": 3000}

# Diisi sistem (publisher/jobs/approval) -- tidak boleh dikirim dari client.
SYSTEM_ROW_FIELDS = (
    "status", "remote_id", "permalink", "error_log", "published_on",
    "attempts", "provider_state", "scheduled_at",
)
CONTENT_LOCKED_FIELDS = ("title", "base_media", "base_caption")
PUBLISH_PHASE = ("Approved", "Publishing", "Partial")
PENDING = ("Pending Approval", "Pending Final Approval")
MANAGER_ROLES = {"Social Manager", "System Manager"}
FINAL_ROLES = {"Social Final Approver", "System Manager"}
REVIEWER_ROLES = MANAGER_ROLES | FINAL_ROLES
NOTE_FIELDS = ("note_type", "target_channel", "note")
NOTE_SYSTEM = ("reviewer_level", "raised_by", "raised_on")


class SocialPost(Document):
    def validate(self):
        if self.is_new():
            self.requested_by = frappe.session.user
        self._protect_system_fields()
        self._apply_media_assets()
        self._validate_rows()
        self._validate_revision_notes()
        self._lock_content()
        if self.status == "Draft" or self.is_new():
            self._set_final_flag()

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
        for f in ("requested_by", "approved_by", "approved_on", "final_approved_by", "final_approved_on",
                  "needs_final_approval"):
            if before:
                self.set(f, before.get(f))
            elif f != "requested_by":
                self.set(f, None)
        # recurring_source hanya boleh diisi job recurring saat insert
        if before:
            self.recurring_source = getattr(before, "recurring_source", None)
        elif not frappe.flags.get("social_recurring"):
            self.recurring_source = None

    def _set_final_flag(self):
        self.needs_final_approval = 1 if frappe.db.get_single_value("Social Posting Settings", "require_final_approval") else 0

    def _apply_media_assets(self):
        before = self.get_doc_before_save()
        apply_asset(self, "media_asset", "base_media", before)
        old_rows = {r.name: r for r in before.channels} if before else {}
        for row in self.channels:
            apply_asset(row, "media_asset", "media_override", old_rows.get(row.name))
        old_items = {r.name: r for r in before.media_items} if before else {}
        for item in self.media_items:
            apply_asset(item, "media_asset", "media", old_items.get(item.name))

    def _validate_rows(self):
        strict = self.status != "Draft"
        if strict and not self.channels:
            frappe.throw(_("Tambahkan minimal satu kanal."))
        items = [i for i in self.media_items if i.media]
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

            multi = multi_limits(row.channel, row.post_format)
            if multi:
                low, high = multi
                if len(items) > high:
                    frappe.throw(_("Row {0}: {1} / {2} maksimal {3} media.").format(row.idx, row.channel, row.post_format, high))
                if strict and row.active and len(items) < low:
                    frappe.throw(_("Row {0}: {1} / {2} membutuhkan {3}-{4} media pada tabel Carousel / Album Media.")
                                 .format(row.idx, row.channel, row.post_format, low, high))
            else:
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

    def _validate_revision_notes(self):
        """Catatan revisi terstruktur: hanya reviewer yang boleh menulis; editor hanya menandai Resolved."""
        before = self.get_doc_before_save()
        old_notes = {n.name: n for n in before.revision_notes} if before else {}
        reviewer = bool(REVIEWER_ROLES & set(frappe.get_roles()))
        level = {"Pending Approval": "Level 1", "Pending Final Approval": "Level 2"}.get(self.status, "Manager")
        user, now = frappe.session.user, now_datetime()
        kept = set()
        for note in self.revision_notes:
            old = old_notes.get(note.name)
            if not old:
                if not reviewer:
                    frappe.throw(_("Hanya reviewer (Social Manager / Social Final Approver) yang dapat menambah catatan revisi."),
                                 frappe.PermissionError)
                note.status = "Open"
                note.reviewer_level, note.raised_by, note.raised_on = level, user, now
                note.resolved_by = note.resolved_on = None
                continue
            kept.add(note.name)
            for f in NOTE_SYSTEM:
                note.set(f, old.get(f))
            if not reviewer and any(note.get(f) != old.get(f) for f in NOTE_FIELDS):
                frappe.throw(_("Catatan revisi hanya dapat diubah oleh reviewer. Anda hanya dapat mengisi Resolution dan status."))
            if note.status == "Resolved" and old.status != "Resolved":
                note.resolved_by, note.resolved_on = user, now
            elif note.status == "Open" and old.status == "Resolved":
                if not reviewer:
                    frappe.throw(_("Hanya reviewer yang dapat membuka kembali catatan revisi."))
                note.resolved_by = note.resolved_on = None
            else:
                note.resolved_by, note.resolved_on = old.resolved_by, old.resolved_on
        if before and not reviewer and set(old_notes) - kept:
            frappe.throw(_("Catatan revisi tidak boleh dihapus oleh editor."))

    def _open_notes(self):
        return [n for n in self.revision_notes if n.status != "Resolved"]

    def _lock_content(self):
        before = self.get_doc_before_save()
        if not before or before.status in ("Draft", "Pending Approval"):
            return
        if "System Manager" in frappe.get_roles():
            return
        for f in CONTENT_LOCKED_FIELDS:
            if self.get(f) != before.get(f):
                frappe.throw(_("Konten tidak bisa diubah setelah disetujui. Kembalikan ke Draft terlebih dahulu."))
        if [i.media for i in self.media_items] != [i.media for i in before.media_items]:
            frappe.throw(_("Konten tidak bisa diubah setelah disetujui. Kembalikan ke Draft terlebih dahulu."))

    # ------------------------------------------------------------------ workflow side effects
    def _handle_transitions(self):
        before = self.get_doc_before_save()
        if not before or before.status == self.status:
            return
        old, new, roles = before.status, self.status, set(frappe.get_roles())
        user, now = frappe.session.user, now_datetime()

        if old == "Draft" and new == "Pending Approval":
            self._set_final_flag()
            if self._open_notes():
                frappe.throw(_("Masih ada catatan revisi berstatus Open. Selesaikan (Resolved) sebelum mengajukan ulang."))

        if old == "Pending Approval" and new in ("Approved", "Pending Final Approval"):
            if not MANAGER_ROLES & roles:
                frappe.throw(_("Hanya Social Manager yang dapat menyetujui."), frappe.PermissionError)
            if new == "Approved" and self.needs_final_approval:
                frappe.throw(_("Postingan ini membutuhkan final approval (Social Final Approver)."))
            if new == "Pending Final Approval" and not self.needs_final_approval:
                frappe.throw(_("Final approval tidak diaktifkan untuk postingan ini."))
            if self._open_notes():
                frappe.throw(_("Masih ada catatan revisi berstatus Open."))
            self.approved_by, self.approved_on = user, now
        elif old == "Pending Final Approval" and new == "Approved":
            if not FINAL_ROLES & roles:
                frappe.throw(_("Hanya Social Final Approver yang dapat memberi final approval."), frappe.PermissionError)
            if self._open_notes():
                frappe.throw(_("Masih ada catatan revisi berstatus Open."))
            self.final_approved_by, self.final_approved_on = user, now
        elif new == "Draft" and old in PENDING:  # reject / minta revisi
            needed = FINAL_ROLES if old == "Pending Final Approval" else MANAGER_ROLES
            if not needed & roles:
                frappe.throw(_("Anda tidak berwenang menolak pada tahap ini."), frappe.PermissionError)
            if not self._open_notes():
                frappe.throw(_("Tambahkan minimal satu catatan revisi (status Open) pada tabel Revision Notes, lalu tolak."))

        if new == "Draft":  # reject / reopen
            self.approved_by = self.approved_on = None
            self.final_approved_by = self.final_approved_on = None
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
