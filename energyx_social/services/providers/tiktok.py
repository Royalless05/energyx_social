"""TikTok Content Posting API: video (FILE_UPLOAD berpotongan / PULL_FROM_URL) dan foto (PULL_FROM_URL)."""
import os
import time

import frappe
from frappe.utils import add_to_date, now_datetime

from energyx_social.services.client import parse_json, retry_after_seconds
from energyx_social.services.errors import (
    AuthError, PermanentError, QuotaExceededError, RateLimitError, TransientError,
)
from energyx_social.services.providers.base import BaseProvider, PublishContext, PublishResult

BASE = "https://open.tiktokapis.com"
MB = 1024 * 1024
CHUNK = 10 * MB
STATUS_POLL_SECONDS = 10
STATUS_TIMEOUT = 600

AUTH_CODES = {"access_token_invalid", "scope_not_authorized", "token_not_authorized_for_specified_user",
              "scope_permission_missed"}


def plan_chunks(size: int):
    """(chunk_size, total_chunk_count). Chunk terakhir menyerap sisa (<10 MB), jadi <= 20 MB (batas 128 MB)."""
    if size <= CHUNK:
        return size, 1
    return CHUNK, size // CHUNK


class TikTokProvider(BaseProvider):
    channels = ("TikTok",)

    def map_error(self, resp):
        err = parse_json(resp).get("error")
        code = err.get("code") if isinstance(err, dict) else None
        if code in (None, "ok"):
            return None  # sukses (HTTP >= 400 tanpa body error jatuh ke pemetaan umum)
        msg = f"TikTok {code}: {err.get('message', '')}"
        kw = {"code": code, "status": resp.status_code}
        if code == "rate_limit_exceeded" or resp.status_code == 429:
            return RateLimitError(msg, retry_after=retry_after_seconds(resp), **kw)
        if code == "spam_risk_too_many_posts":
            return QuotaExceededError(msg, **kw)
        if code in AUTH_CODES:
            return AuthError(msg, **kw)
        if code in ("internal_error", "server_error") or resp.status_code >= 500:
            return TransientError(msg, **kw)
        return PermanentError(msg, **kw)

    def _headers(self):
        return {"Authorization": f"Bearer {self.account.access_token}",
                "Content-Type": "application/json; charset=UTF-8"}

    def _call(self, path, payload=None, params=None, method="POST") -> dict:
        return parse_json(self.client.request(method, f"{BASE}{path}", json=payload, params=params,
                                              headers=self._headers())).get("data") or {}

    @staticmethod
    def _upload_mode() -> str:
        return frappe.db.get_single_value("Social Posting Settings", "tiktok_upload_mode") or "FILE_UPLOAD"

    def media_requirements(self, post_format):
        if post_format == "Photo" or self._upload_mode() == "PULL_FROM_URL":
            return {"public": True, "local": False}
        return {"public": False, "local": True}

    # ------------------------------------------------------------------ auth
    def refresh_token(self):
        a = self.account
        if not (a.app_id and a.app_secret and a.refresh_token):
            raise AuthError("Client Key, Client Secret, dan Refresh Token dibutuhkan untuk TikTok.")
        resp = self.client.request("POST", f"{BASE}/v2/oauth/token/", data={
            "client_key": a.app_id, "client_secret": a.app_secret,
            "grant_type": "refresh_token", "refresh_token": a.refresh_token,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        body = parse_json(resp)
        if not body.get("access_token"):
            raise AuthError("TikTok tidak mengembalikan access_token baru.")
        a.save_tokens(body["access_token"], add_to_date(now_datetime(), seconds=int(body.get("expires_in", 86400))),
                      refresh_token=body.get("refresh_token"))

    def test_connection(self) -> str:
        self.ensure_fresh_token(force=bool(self.account.refresh_token))
        data = self._call("/v2/user/info/", params={"fields": "open_id,display_name"}, method="GET")
        user = data.get("user") or {}
        return f"TikTok {user.get('display_name', user.get('open_id', 'OK'))}"

    # ------------------------------------------------------------------ publish
    def _privacy_level(self) -> str:
        wanted = frappe.db.get_single_value("Social Posting Settings", "tiktok_default_privacy") or "SELF_ONLY"
        options = self._call("/v2/post/publish/creator_info/query/").get("privacy_level_options") or []
        if options and wanted not in options:
            raise PermanentError(f"Privasi {wanted} tidak diizinkan akun ini (tersedia: {', '.join(options)}).")
        return wanted

    def publish(self, ctx: PublishContext) -> PublishResult:
        self.ensure_fresh_token()
        state = ctx.provider_state or ""
        if state.startswith("uploaded:"):  # unggahan selesai, tinggal menunggu pemrosesan TikTok
            publish_id = state.split(":", 1)[1]
        else:
            publish_id = self._init_photo(ctx) if ctx.post_format == "Photo" else self._init_video(ctx)
            ctx.save_state(f"uploaded:{publish_id}")
        post_id = self._wait_published(publish_id)
        remote = post_id or publish_id
        # Best-effort: format URL tanpa username; TikTok mengarahkan ke halaman video bila id valid.
        permalink = f"https://www.tiktok.com/@/video/{post_id}" if post_id else ""
        return PublishResult(remote, permalink)

    def _init_video(self, ctx) -> str:
        media = ctx.media
        info = {"title": ctx.caption[:2200] or ctx.title, "privacy_level": self._privacy_level()}
        if self._upload_mode() == "PULL_FROM_URL":
            src = {"source": "PULL_FROM_URL", "video_url": media.public_url}
            data = self._call("/v2/post/publish/video/init/", {"post_info": info, "source_info": src})
            return data["publish_id"]

        size = os.path.getsize(media.local_path)
        chunk_size, count = plan_chunks(size)
        src = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": count}
        data = self._call("/v2/post/publish/video/init/", {"post_info": info, "source_info": src})
        upload_url = data["upload_url"]
        with open(media.local_path, "rb") as fh:
            for i in range(count):
                start = i * chunk_size
                end = size - 1 if i == count - 1 else start + chunk_size - 1
                fh.seek(start)
                self.client.request(
                    "PUT", upload_url, data=fh.read(end - start + 1), timeout=(10, 600),
                    headers={"Content-Type": media.mime, "Content-Length": str(end - start + 1),
                             "Content-Range": f"bytes {start}-{end}/{size}"})
        return data["publish_id"]

    def _init_photo(self, ctx) -> str:
        payload = {
            "post_info": {"title": (ctx.title or "")[:90], "description": ctx.caption[:4000],
                          "privacy_level": self._privacy_level()},
            "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": [ctx.media.public_url]},
            "post_mode": "DIRECT_POST", "media_type": "PHOTO",
        }
        return self._call("/v2/post/publish/content/init/", payload)["publish_id"]

    def _wait_published(self, publish_id):
        deadline = time.monotonic() + STATUS_TIMEOUT
        while True:
            data = self._call("/v2/post/publish/status/fetch/", {"publish_id": publish_id})
            status = data.get("status")
            if status == "PUBLISH_COMPLETE":
                ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
                return str(ids[0]) if ids else None
            if status == "FAILED":
                raise PermanentError(f"TikTok gagal memproses: {data.get('fail_reason', 'unknown')}")
            if status == "SEND_TO_USER_INBOX":
                raise PermanentError("Terkirim ke inbox TikTok (mode draft); selesaikan publikasi di aplikasi TikTok.")
            if time.monotonic() > deadline:
                raise TransientError("TikTok masih memproses; akan dicek ulang.")
            time.sleep(STATUS_POLL_SECONDS)

    # ------------------------------------------------------------------ metrics
    def fetch_metrics(self, remote_id, post_format):
        if not str(remote_id).isdigit():
            return {}  # hanya publish_id, belum ada id video publik
        self.ensure_fresh_token()
        data = self._call("/v2/video/query/", {"filters": {"video_ids": [remote_id]}},
                          params={"fields": "id,like_count,comment_count,share_count,view_count"})
        videos = data.get("videos") or []
        if not videos:
            return {}
        v = videos[0]
        return {"impressions": v.get("view_count", 0), "likes": v.get("like_count", 0),
                "comments": v.get("comment_count", 0), "shares": v.get("share_count", 0)}
