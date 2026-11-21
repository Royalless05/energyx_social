from dataclasses import dataclass, field
from typing import Callable

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from energyx_social.services.client import SocialClient
from energyx_social.services.credentials import Account
from energyx_social.services.errors import AuthError, UnsupportedOperation


@dataclass
class PublishContext:
    post: str
    row: str
    title: str
    caption: str
    post_format: str
    first_comment: str = ""
    media: object = None          # MediaInfo | None
    thumbnail: object = None      # MediaInfo | None
    provider_state: str = ""
    media_items: list = field(default_factory=list)  # list MediaInfo untuk Carousel/Album
    save_state: Callable[[str], None] = lambda value: None  # checkpoint idempotensi (di-commit)


@dataclass
class PublishResult:
    remote_id: str
    permalink: str = ""
    warnings: list = field(default_factory=list)


class BaseProvider:
    channels: tuple = ()

    def __init__(self, account: Account, client: SocialClient | None = None):
        self.account = account
        self.client = client or SocialClient(account.channel, self.map_error)

    # ---- override
    def map_error(self, resp):
        return None

    def media_requirements(self, post_format: str) -> dict:
        return {"public": False, "local": False}

    def test_connection(self) -> str:
        raise NotImplementedError

    def publish(self, ctx: PublishContext) -> PublishResult:
        raise NotImplementedError

    def refresh_token(self) -> None:
        raise UnsupportedOperation("Provider ini tidak mendukung refresh token.")

    def delete(self, remote_id: str) -> None:
        raise UnsupportedOperation(f"{self.account.channel} tidak mendukung penghapusan lewat API; hapus manual di platform.")

    def fetch_metrics(self, remote_id: str, post_format: str) -> dict:
        return {}

    # ---- komentar (Inbox). Provider yang tidak mendukung biarkan default.
    def fetch_comments(self, remote_id: str, post_format: str) -> list:
        """list of dict: id, text, author, author_id, created (datetime/str), parent_id."""
        raise UnsupportedOperation(f"{self.account.channel} tidak mendukung pengambilan komentar lewat API.")

    def reply_comment(self, remote_id: str, comment_id: str, text: str) -> str:
        raise UnsupportedOperation(f"{self.account.channel} tidak mendukung balasan komentar lewat API.")

    # ---- shared
    def ensure_fresh_token(self, margin_minutes: int = 5, force: bool = False):
        if not self.account.access_token:
            raise AuthError("Access token belum diisi.")
        exp = self.account.token_expires_on
        if force or (exp and get_datetime(exp) < add_to_date(now_datetime(), minutes=margin_minutes)):
            self.refresh_token()
