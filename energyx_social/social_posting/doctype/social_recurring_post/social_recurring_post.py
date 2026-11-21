import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from energyx_social.services.recurring import compute_next
from energyx_social.social_posting.doctype.social_post.social_post import FORMATS

SCHEDULE_FIELDS = ("frequency", "weekday", "day_of_month", "post_time", "start_date", "end_date", "enabled")


class SocialRecurringPost(Document):
    def validate(self):
        if self.frequency == "Monthly" and not (1 <= int(self.day_of_month or 0) <= 28):
            frappe.throw(_("Day of Month harus 1-28."))
        if self.frequency == "Weekly" and not self.weekday:
            frappe.throw(_("Pilih Weekday."))
        if self.start_date and self.end_date and getdate(self.end_date) < getdate(self.start_date):
            frappe.throw(_("End Date tidak boleh sebelum Start Date."))
        if int(self.lead_days or 0) < 0:
            frappe.throw(_("Create Days Before tidak boleh negatif."))
        if not self.channels:
            frappe.throw(_("Tambahkan minimal satu kanal."))
        for row in self.channels:
            fmts = FORMATS.get(row.channel) or []
            row.post_format = row.post_format or (fmts[0] if fmts else None)
            if row.post_format not in fmts:
                frappe.throw(_("Row {0}: format {1} tidak tersedia untuk {2}.").format(row.idx, row.post_format, row.channel))
            acc = frappe.db.get_value("Social Account", row.account, ["channel", "parent"], as_dict=True)
            if not acc or acc.parent != "Social Posting Settings" or acc.channel != row.channel:
                frappe.throw(_("Row {0}: akun tidak cocok dengan kanal {1}.").format(row.idx, row.channel))
            if row.post_format in ("Carousel", "Album"):
                frappe.throw(_("Row {0}: Carousel/Album belum didukung untuk posting berulang.").format(row.idx))
        before = self.get_doc_before_save()
        changed = (not before) or any(self.get(f) != before.get(f) for f in SCHEDULE_FIELDS)
        if not self.enabled:
            self.next_run_on = None
        elif changed or not self.next_run_on:
            self.next_run_on = compute_next(self, now_datetime())
