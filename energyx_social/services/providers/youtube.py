"""YouTube Data API v3: resumable videos.insert, thumbnails.set, playlist, refresh token otomatis."""
import os

from frappe.utils import add_to_date, now_datetime

from energyx_social.services.client import parse_json, retry_after_seconds
from energyx_social.services.errors import (
    AuthError, PermanentError, QuotaExceededError, RateLimitError, SocialError, TransientError,
)
from energyx_social.services.providers.base import BaseProvider, PublishContext, PublishResult

API = "https://www.googleapis.com"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHUNK = 32 * 256 * 1024  # 8 MiB, kelipatan 256 KiB sesuai syarat YouTube


class YouTubeProvider(BaseProvider):
    channels = ("YouTube",)

    def map_error(self, resp):
        if resp.status_code < 400:
            return None
        body = parse_json(resp)
        err = body.get("error")
        if isinstance(err, dict):  # galat API Google
            reason = ((err.get("errors") or [{}])[0]).get("reason", "")
            msg = f"YouTube {resp.status_code} {reason}: {err.get('message', '')}"
        else:  # galat OAuth: {"error": "invalid_grant", "error_description": ...}
            reason = err or ""
            msg = f"Google OAuth {reason}: {body.get('error_description', '')}"
        kw = {"code": reason, "status": resp.status_code}
        if reason in ("quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"):
            return QuotaExceededError(msg, **kw)
        if reason in ("rateLimitExceeded", "userRateLimitExceeded") or resp.status_code == 429:
            return RateLimitError(msg, retry_after=retry_after_seconds(resp), **kw)
        if resp.status_code == 401 or reason in ("invalid_grant", "invalid_client", "authError"):
            return AuthError(msg, **kw)
        if resp.status_code >= 500:
            return TransientError(msg, **kw)
        return PermanentError(msg, **kw)

    def _headers(self, extra=None):
        return {"Authorization": f"Bearer {self.account.access_token}", **(extra or {})}

    def media_requirements(self, post_format):
        return {"public": False, "local": True}

    # ------------------------------------------------------------------ auth
    def refresh_token(self):
        a = self.account
        if not (a.app_id and a.app_secret and a.refresh_token):
            raise AuthError("Client ID, Client Secret, dan Refresh Token dibutuhkan untuk YouTube.")
        body = parse_json(self.client.request("POST", TOKEN_URL, data={
            "grant_type": "refresh_token", "client_id": a.app_id,
            "client_secret": a.app_secret, "refresh_token": a.refresh_token,
        }))
        if not body.get("access_token"):
            raise AuthError("Google tidak mengembalikan access_token.")
        a.save_tokens(body["access_token"], add_to_date(now_datetime(), seconds=int(body.get("expires_in", 3600))))

    def test_connection(self) -> str:
        self.ensure_fresh_token(force=bool(self.account.refresh_token))
        data = parse_json(self.client.request(
            "GET", f"{API}/youtube/v3/channels", params={"part": "snippet", "mine": "true"}, headers=self._headers()))
        items = data.get("items") or []
        if not items:
            raise PermanentError("Token tidak memiliki channel YouTube.")
        ch = items[0]
        if self.account.account_id and ch["id"] != self.account.account_id:
            raise PermanentError(f"Token milik channel {ch['id']}, bukan {self.account.account_id}.")
        return f"YouTube {ch['snippet']['title']}"

    # ------------------------------------------------------------------ publish
    def publish(self, ctx: PublishContext) -> PublishResult:
        self.ensure_fresh_token()
        state = ctx.provider_state or ""
        if state.startswith("video:"):
            video_id = state.split(":", 1)[1]
        else:
            video_id = self._upload(ctx)
            ctx.save_state(f"video:{video_id}")

        warnings = []
        if ctx.thumbnail:
            self._try(warnings, "thumbnail", lambda: self._set_thumbnail(video_id, ctx.thumbnail))
        if self.account.playlist_id:
            self._try(warnings, "playlist", lambda: self._add_to_playlist(video_id))
        path = "shorts/" if ctx.post_format == "Short" else "watch?v="
        return PublishResult(video_id, f"https://www.youtube.com/{path}{video_id}", warnings)

    @staticmethod
    def _try(warnings, label, fn):
        try:
            fn()
        except SocialError as exc:  # video sudah terbit; langkah pelengkap tidak boleh menggagalkan
            warnings.append(f"{label} gagal: {exc}")

    def _upload(self, ctx) -> str:
        media = ctx.media
        path, size, mime = media.local_path, os.path.getsize(media.local_path), media.mime
        state = ctx.provider_state or ""
        uri = state.split(":", 1)[1] if state.startswith("session:") else None

        if not uri:
            description = ctx.caption or ""
            if ctx.post_format == "Short" and "#shorts" not in (ctx.title + description).lower():
                description = (description + "\n\n#Shorts").strip()
            meta = {
                "snippet": {"title": ctx.title[:100], "description": description, "categoryId": "22"},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
            }
            resp = self.client.request(
                "POST", f"{API}/upload/youtube/v3/videos",
                params={"uploadType": "resumable", "part": "snippet,status"}, json=meta,
                headers=self._headers({"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": mime}),
            )
            uri = resp.headers.get("Location")
            if not uri:
                raise PermanentError("YouTube tidak mengembalikan upload session URI.")
            ctx.save_state(f"session:{uri}")

        done_id, offset = self._upload_status(uri, size, mime)
        if done_id:
            return done_id
        with open(path, "rb") as fh:
            while offset < size:
                fh.seek(offset)
                chunk = fh.read(CHUNK)
                end = offset + len(chunk) - 1
                resp = self.client.request(
                    "PUT", uri, data=chunk, allow_redirects=False, timeout=(10, 600),
                    headers=self._headers({"Content-Length": str(len(chunk)), "Content-Type": mime,
                                           "Content-Range": f"bytes {offset}-{end}/{size}"}),
                )
                if resp.status_code in (200, 201):
                    return parse_json(resp)["id"]
                offset = self._next_offset(resp)
        done_id, _ = self._upload_status(uri, size, mime)
        if not done_id:
            raise TransientError("Upload YouTube belum selesai; akan dilanjutkan.")
        return done_id

    def _upload_status(self, uri, size, mime):
        resp = self.client.request("PUT", uri, allow_redirects=False, headers=self._headers(
            {"Content-Length": "0", "Content-Range": f"bytes */{size}", "Content-Type": mime}))
        if resp.status_code in (200, 201):
            return parse_json(resp).get("id"), size
        return None, self._next_offset(resp)

    @staticmethod
    def _next_offset(resp) -> int:
        rng = resp.headers.get("Range", "")  # "bytes=0-12345"
        return int(rng.rsplit("-", 1)[1]) + 1 if "-" in rng else 0

    def _set_thumbnail(self, video_id, thumb):
        with open(thumb.local_path, "rb") as fh:
            self.client.request(
                "POST", f"{API}/upload/youtube/v3/thumbnails/set",
                params={"videoId": video_id, "uploadType": "media"}, data=fh.read(),
                headers=self._headers({"Content-Type": thumb.mime}))

    def _add_to_playlist(self, video_id):
        self.client.request(
            "POST", f"{API}/youtube/v3/playlistItems", params={"part": "snippet"},
            json={"snippet": {"playlistId": self.account.playlist_id,
                              "resourceId": {"kind": "youtube#video", "videoId": video_id}}},
            headers=self._headers())

    # ------------------------------------------------------------------ delete / metrics
    def delete(self, remote_id):
        self.ensure_fresh_token()
        self.client.request("DELETE", f"{API}/youtube/v3/videos", params={"id": remote_id}, headers=self._headers())

    def fetch_metrics(self, remote_id, post_format):
        self.ensure_fresh_token()
        data = parse_json(self.client.request(
            "GET", f"{API}/youtube/v3/videos", params={"part": "statistics", "id": remote_id},
            headers=self._headers()))
        items = data.get("items") or []
        if not items:
            return {}
        s = items[0].get("statistics", {})
        # YouTube tidak mengekspos reach/shares lewat Data API; viewCount dipakai sebagai impressions.
        return {"impressions": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0))}
