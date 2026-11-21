import frappe
from frappe import _
from frappe.model.document import Document

from energyx_social.services.hashtags import normalize_hashtags


class SocialHashtagTemplate(Document):
    def validate(self):
        self.hashtags = normalize_hashtags(self.hashtags)
        if not self.hashtags:
            frappe.throw(_("Isi minimal satu hashtag."))
        if self.account:
            acc = frappe.db.get_value("Social Account", self.account, ["channel", "parent"], as_dict=True)
            if not acc or acc.parent != "Social Posting Settings":
                frappe.throw(_("Akun tidak ditemukan."))
            if self.channel and self.channel != acc.channel:
                frappe.throw(_("Akun yang dipilih bukan akun {0}.").format(self.channel))
            self.channel = acc.channel
        if self.is_default:
            self._unset_other_defaults()

    def _unset_other_defaults(self):
        frappe.db.sql(
            """update `tabSocial Hashtag Template` set is_default = 0
               where name != %(name)s and is_default = 1
                 and ifnull(account, '') = %(account)s and ifnull(channel, '') = %(channel)s""",
            {"name": self.name or "", "account": self.account or "", "channel": self.channel or ""},
        )
