"""LinkedIn REST Posts API: teks, gambar, video (author = person atau organization URN)."""
import os
from urllib.parse import quote

from frappe.utils import add_to_date, now_datetime

from energyx_social.services.client import parse_json, retry_after_seconds
from energyx_social.services.errors import (
    AuthError, PermanentError, RateLimitError, SocialError, TransientError,
)
from energyx_social.services.providers.base import BaseProvider, PublishContext, PublishResult

BASE = "https://api.linkedin.com"
OAUTH = "https://www.linkedin.com/oauth/v2/accessToken"
DEFAULT_VERSION = "202610"  # format YYYYMM; LinkedIn hanya mendukung versi ~12 bulan terakhir -> ubah di Social Account bila ditolak
_RESERVED = "\\|{}@[]()<>*_~"  # '#' sengaja tidak di-escape agar hashtag tetap aktif


def escape_commentary(text: str) -> str:
    """Karakter khusus 'little text format' LinkedIn harus di-escape, kecuali '#'."""
    return "".join("\\" + ch if ch in _RESERVED else ch for ch in (text or ""))


class LinkedInProvider(BaseProvider):
    channels = ("LinkedIn",)

    # ------------------------------------------------------------------ plumbing
    def map_error(self, resp):
        if resp.status_code < 400:
            return None
        body = parse_json(resp)
        msg = f"LinkedIn {resp.status_code}: {body.get('message') or body.get('error_description') or ''}".strip()
        kw = {"code": body.get("serviceErrorCode") or body.get("error"), "status": resp.status_code}
        if resp.status_code == 429:
            return RateLimitError(msg, retry_after=retry_after_seconds(resp), **kw)
        if resp.status_code in (401, 403) or body.get("error") == "invalid_grant":
            return AuthError(msg, **kw)
        if resp.status_code >= 500:
            return TransientError(msg, **kw)
        return PermanentError(msg, **kw)

    def _headers(self, extra=None):
        return {"Authorization": f"Bearer {self.account.access_token}",
                "LinkedIn-Version": (self.account.api_version or DEFAULT_VERSION).strip(),
                "X-Restli-Protocol-Version": "2.0.0", **(extra or {})}

    def _author(self) -> str:
        urn = (self.account.account_id or "").strip()
        if not urn.startswith(("urn:li:person:", "urn:li:organization:")):
            raise PermanentError("Account ID LinkedIn harus URN lengkap: urn:li:organization:<id> atau urn:li:person:<id>.")
        return urn

    def media_requirements(self, post_format):
        return {"public": False, "local": post_format != "Text"}

    # ------------------------------------------------------------------ auth
    def refresh_token(self):
        a = self.account
        if not (a.app_id and a.app_secret and a.refresh_token):
            raise AuthError("Token LinkedIn berlaku ~60 hari dan tidak bisa diperpanjang otomatis tanpa Refresh Token "
                            "(hanya untuk app yang disetujui LinkedIn). Buat token baru lewat OAuth dan isi ulang Access Token.")
        body = parse_json(self.client.request("POST", OAUTH, data={
            "grant_type": "refresh_token", "refresh_token": a.refresh_token,
            "client_id": a.app_id, "client_secret": a.app_secret,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}))
        if not body.get("access_token"):
            raise AuthError("LinkedIn tidak mengembalikan access_token baru.")
        a.save_tokens(body["access_token"], add_to_date(now_datetime(), seconds=int(body.get("expires_in", 5184000))),
                      refresh_token=body.get("refresh_token"))

    def test_connection(self) -> str:
        self.ensure_fresh_token()
        urn = self._author()
        if urn.startswith("urn:li:person:"):
            data = parse_json(self.client.request("GET", f"{BASE}/v2/userinfo", headers=self._headers()))
            if data.get("sub") and f"urn:li:person:{data['sub']}" != urn:
                raise PermanentError(f"Token milik member {data['sub']}, bukan {urn}.")
            return f"LinkedIn {data.get('name', urn)}"
        org_id = urn.rsplit(":", 1)[1]
        data = parse_json(self.client.request("GET", f"{BASE}/rest/organizations/{org_id}", headers=self._headers()))
        return f"LinkedIn {data.get('localizedName', urn)}"

    # ------------------------------------------------------------------ publish
    def publish(self, ctx: PublishContext) -> PublishResult:
        self.ensure_fresh_token()
        author, state = self._author(), ctx.provider_state or ""
        if state.startswith("published:"):
            post_urn = state.split(":", 1)[1]
        else:
            body = {
                "author": author, "commentary": escape_commentary(ctx.caption), "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
            }
            if ctx.post_format != "Text":
                asset = state.split(":", 1)[1] if state.startswith("asset:") else None
                if not asset:
                    asset = self._upload_video(ctx, author) if ctx.post_format == "Video" else self._upload_image(ctx, author)
                    ctx.save_state(f"asset:{asset}")
                media = {"id": asset}
                if ctx.post_format == "Video":
                    media["title"] = (ctx.title or "")[:200]
                body["content"] = {"media": media}
            resp = self.client.request("POST", f"{BASE}/rest/posts", json=body, headers=self._headers())
            post_urn = resp.headers.get("x-restli-id") or resp.headers.get("X-RestLi-Id")
            if not post_urn:
                raise PermanentError("LinkedIn tidak mengembalikan ID postingan.")
            ctx.save_state(f"published:{post_urn}")
        return PublishResult(post_urn, f"https://www.linkedin.com/feed/update/{post_urn}")

    def _upload_image(self, ctx, owner) -> str:
        init = parse_json(self.client.request(
            "POST", f"{BASE}/rest/images", params={"action": "initializeUpload"},
            json={"initializeUploadRequest": {"owner": owner}}, headers=self._headers())).get("value") or {}
        if not (init.get("uploadUrl") and init.get("image")):
            raise PermanentError("LinkedIn tidak mengembalikan upload URL gambar.")
        with open(ctx.media.local_path, "rb") as fh:
            self.client.request("PUT", init["uploadUrl"], data=fh.read(), timeout=(10, 300),
                                headers={"Authorization": f"Bearer {self.account.access_token}",
                                         "Content-Type": "application/octet-stream"})
        return init["image"]

    def _upload_video(self, ctx, owner) -> str:
        path = ctx.media.local_path
        size = os.path.getsize(path)
        init = parse_json(self.client.request(
            "POST", f"{BASE}/rest/videos", params={"action": "initializeUpload"},
            json={"initializeUploadRequest": {"owner": owner, "fileSizeBytes": size,
                                              "uploadCaptions": False, "uploadThumbnail": False}},
            headers=self._headers())).get("value") or {}
        parts = init.get("uploadInstructions") or []
        if not (init.get("video") and parts):
            raise PermanentError("LinkedIn tidak mengembalikan instruksi upload video.")
        etags = []
        with open(path, "rb") as fh:
            for part in parts:
                first, last = int(part["firstByte"]), int(part["lastByte"])
                fh.seek(first)
                resp = self.client.request("PUT", part["uploadUrl"], data=fh.read(last - first + 1), timeout=(10, 600),
                                           headers={"Content-Type": "application/octet-stream"})
                etag = resp.headers.get("ETag") or resp.headers.get("etag")
                if not etag:
                    raise PermanentError("LinkedIn tidak mengembalikan ETag untuk potongan video.")
                etags.append(etag.strip('"'))
        self.client.request("POST", f"{BASE}/rest/videos", params={"action": "finalizeUpload"}, headers=self._headers(),
                            json={"finalizeUploadRequest": {"video": init["video"], "uploadToken": init.get("uploadToken", ""),
                                                            "uploadedPartIds": etags}})
        return init["video"]

    # ------------------------------------------------------------------ delete / metrics
    def delete(self, remote_id):
        self.ensure_fresh_token()
        self.client.request("DELETE", f"{BASE}/rest/posts/{quote(remote_id, safe='')}", headers=self._headers())

    def fetch_metrics(self, remote_id, post_format):
        self.ensure_fresh_token()
        data = parse_json(self.client.request(
            "GET", f"{BASE}/rest/socialActions/{quote(remote_id, safe='')}", headers=self._headers()))
        likes = (data.get("likesSummary") or {}).get("totalLikes", 0)
        comments = (data.get("commentsSummary") or {}).get("aggregatedTotalComments",
                    (data.get("commentsSummary") or {}).get("totalFirstLevelComments", 0))
        return {"likes": int(likes or 0), "comments": int(comments or 0)}
