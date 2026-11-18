from dataclasses import dataclass, field

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from energyx_social.services.errors import PermanentError

SETTINGS = "Social Posting Settings"
ACCOUNT = "Social Account"


@dataclass
class Account:
    """Kredensial satu akun. Rahasia di-repr=False agar tidak bocor ke log/traceback."""
    name: str
    channel: str
    account_name: str
    account_id: str
    app_id: str
    api_version: str
    token_expires_on: object
    playlist_id: str
    enabled: bool
    app_secret: str = field(default="", repr=False)
    access_token: str = field(default="", repr=False)
    refresh_token: str = field(default="", repr=False)

    @classmethod
    def load(cls, name: str) -> "Account":
        row = frappe.db.get_value(
            ACCOUNT, name,
            ["name", "parent", "channel", "account_name", "account_id", "app_id", "api_version",
             "token_expires_on", "playlist_id", "enabled"],
            as_dict=True,
        )
        if not row or row.parent != SETTINGS:
            raise PermanentError("Akun sosial tidak ditemukan di Social Posting Settings.")

        def pw(fieldname):
            return get_decrypted_password(ACCOUNT, name, fieldname, raise_exception=False) or ""

        return cls(
            name=row.name, channel=row.channel, account_name=row.account_name, account_id=row.account_id or "",
            app_id=row.app_id or "", api_version=row.api_version or "", token_expires_on=row.token_expires_on,
            playlist_id=row.playlist_id or "", enabled=bool(row.enabled),
            app_secret=pw("app_secret"), access_token=pw("access_token"), refresh_token=pw("refresh_token"),
        )

    @property
    def secrets(self):
        return [s for s in (self.app_secret, self.access_token, self.refresh_token) if s]

    def save_tokens(self, access_token, expires_on=None, refresh_token=None):
        """Simpan token baru terenkripsi (field Password) + kedaluwarsa."""
        set_encrypted_password(ACCOUNT, self.name, access_token, "access_token")
        self.access_token = access_token
        if refresh_token:
            set_encrypted_password(ACCOUNT, self.name, refresh_token, "refresh_token")
            self.refresh_token = refresh_token
        frappe.db.set_value(ACCOUNT, self.name, "token_expires_on", expires_on, update_modified=False)
        self.token_expires_on = expires_on
        frappe.clear_document_cache(SETTINGS, SETTINGS)
