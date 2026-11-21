"""Meta Graph API: Instagram (container -> media_publish) dan Facebook Page."""
import json
import time

from frappe.utils import add_to_date, now_datetime

from energyx_social.services.client import parse_json, retry_after_seconds
from energyx_social.services.errors import (
    AuthError, PermanentError, RateLimitError, SocialError, TransientError, UnsupportedOperation,
)
from energyx_social.services.providers.base import BaseProvider, PublishContext, PublishResult

RATE_LIMIT_CODES = {4, 17, 32, 613, 80000, 80001, 80002, 80003, 80004, 80005, 80006, 80008, 80009, 80014}
AUTH_CODES = {102, 190, 200, 10}
CONTAINER_POLL_SECONDS = 5
CONTAINER_TIMEOUT = 600


class MetaProvider(BaseProvider):
    channels = ("Instagram", "Facebook Page")

    # ------------------------------------------------------------------ plumbing
    @property
    def base(self) -> str:
        host = (self.account.api_version or "graph.facebook.com/v21.0").strip().rstrip("/")
        return host if host.startswith("http") else f"https://{host}"

    def map_error(self, resp):
        if resp.status_code < 400:
            return None
        err = parse_json(resp).get("error") or {}
        code, sub = err.get("code"), err.get("error_subcode")
        msg = f"Meta {code}/{sub}: {err.get('message', 'HTTP ' + str(resp.status_code))}"
        kw = {"code": code, "status": resp.status_code}
        if resp.status_code == 429 or code in RATE_LIMIT_CODES:
            return RateLimitError(msg, retry_after=retry_after_seconds(resp), **kw)
        if code in AUTH_CODES or resp.status_code == 401:
            return AuthError(msg, **kw)
        if err.get("is_transient") or code in (1, 2) or resp.status_code >= 500:
            return TransientError(msg, **kw)
        return PermanentError(msg, **kw)

    def _headers(self):
        return {"Authorization": f"Bearer {self.account.access_token}"}

    def _get(self, path, params=None) -> dict:
        return parse_json(self.client.request("GET", f"{self.base}/{path}", params=params, headers=self._headers()))

    def _post(self, path, data=None) -> dict:
        return parse_json(self.client.request("POST", f"{self.base}/{path}", data=data, headers=self._headers()))

    # ------------------------------------------------------------------ interface
    def media_requirements(self, post_format):
        return {"public": post_format != "Text", "local": False}

    def _items_or_raise(self, ctx):
        if not ctx.media_items:
            raise PermanentError("Carousel/Album membutuhkan daftar media.")
        return ctx.media_items

    def test_connection(self) -> str:
        self.ensure_fresh_token()
        if self.account.channel == "Instagram":
            d = self._get(self.account.account_id, {"fields": "id,username"})
            return f"Instagram @{d.get('username', d.get('id'))}"
        d = self._get(self.account.account_id, {"fields": "id,name"})
        return f"Facebook Page {d.get('name', d.get('id'))}"

    def refresh_token(self):
        a = self.account
        if not (a.app_id and a.app_secret and a.access_token):
            raise AuthError("App ID, App Secret, dan Access Token dibutuhkan untuk memperpanjang token Meta.")
        # POST + body agar app_secret/token tidak muncul di URL/log.
        resp = self.client.request("POST", f"{self.base}/oauth/access_token", data={
            "grant_type": "fb_exchange_token", "client_id": a.app_id,
            "client_secret": a.app_secret, "fb_exchange_token": a.access_token,
        })
        body = parse_json(resp)
        token = body.get("access_token")
        if not token:
            raise AuthError("Meta tidak mengembalikan access_token baru.")
        expires = add_to_date(now_datetime(), seconds=int(body["expires_in"])) if body.get("expires_in") else None
        a.save_tokens(token, expires)

    def publish(self, ctx: PublishContext) -> PublishResult:
        self.ensure_fresh_token()
        return self._publish_ig(ctx) if self.account.channel == "Instagram" else self._publish_fb(ctx)

    # ------------------------------------------------------------------ Instagram
    def _publish_ig(self, ctx):
        ig, fmt, media = self.account.account_id, ctx.post_format, ctx.media
        state = ctx.provider_state or ""

        if state.startswith("published:"):  # sudah terbit, proses sebelumnya mati sebelum menyimpan hasil
            media_id = state.split(":", 1)[1]
        else:
            container = state.split(":", 1)[1] if state.startswith("container:") else None
            if not container:
                if fmt == "Carousel":
                    container = self._ig_carousel_container(ctx)
                elif fmt == "Post":
                    params = {"image_url": media.public_url, "caption": ctx.caption}
                elif fmt == "Reel":
                    params = {"media_type": "REELS", "video_url": media.public_url,
                              "caption": ctx.caption, "share_to_feed": "true"}
                elif fmt == "Story":
                    key = "video_url" if media.kind == "video" else "image_url"
                    params = {"media_type": "STORIES", key: media.public_url}
                else:
                    raise PermanentError(f"Format Instagram tidak dikenal: {fmt}")
                if fmt != "Carousel":
                    container = self._post(f"{ig}/media", params)["id"]
                ctx.save_state(f"container:{container}")
            self._wait_container(container)
            media_id = self._post(f"{ig}/media_publish", {"creation_id": container})["id"]
            ctx.save_state(f"published:{media_id}")

        warnings = []
        permalink = ""
        try:
            permalink = self._get(media_id, {"fields": "permalink"}).get("permalink", "")
        except SocialError as exc:
            warnings.append(f"permalink: {exc}")
        if ctx.first_comment and ctx.post_format != "Story":
            self._first_comment(media_id, ctx.first_comment, warnings)
        return PublishResult(media_id, permalink, warnings)

    def _ig_carousel_container(self, ctx) -> str:
        """Buat container anak per item (checkpoint tiap item), tunggu semuanya, lalu container CAROUSEL."""
        ig, state = self.account.account_id, ctx.provider_state or ""
        children = state.split(":", 1)[1].split(",") if state.startswith("children:") else []
        items = self._items_or_raise(ctx)
        for item in items[len(children):]:
            params = {"is_carousel_item": "true"}
            if item.kind == "video":
                params.update(media_type="VIDEO", video_url=item.public_url)
            else:
                params["image_url"] = item.public_url
            children.append(self._post(f"{ig}/media", params)["id"])
            ctx.save_state("children:" + ",".join(children))
        for child in children:
            self._wait_container(child)
        return self._post(f"{ig}/media", {"media_type": "CAROUSEL", "children": ",".join(children),
                                          "caption": ctx.caption})["id"]

    def _wait_container(self, container_id):
        deadline = time.monotonic() + CONTAINER_TIMEOUT
        while True:
            st = self._get(container_id, {"fields": "status_code,status"})
            code = st.get("status_code")
            if code in ("FINISHED", "PUBLISHED"):
                return
            if code in ("ERROR", "EXPIRED"):
                raise PermanentError(f"Instagram container {code}: {st.get('status', '')}")
            if time.monotonic() > deadline:
                raise TransientError("Instagram container belum FINISHED (timeout); akan dicoba lagi.")
            time.sleep(CONTAINER_POLL_SECONDS)

    # ------------------------------------------------------------------ Facebook Page
    def _publish_fb(self, ctx):
        page, fmt, media = self.account.account_id, ctx.post_format, ctx.media
        if fmt == "Album":
            post_id = self._fb_album(ctx)
        elif fmt == "Photo":
            r = self._post(f"{page}/photos", {"url": media.public_url, "caption": ctx.caption, "published": "true"})
            post_id = r.get("post_id") or r["id"]
        elif fmt == "Video":
            r = self._post(f"{page}/videos", {"file_url": media.public_url, "description": ctx.caption,
                                              "title": ctx.title, "published": "true"})
            post_id = r["id"]
        elif fmt == "Text":
            post_id = self._post(f"{page}/feed", {"message": ctx.caption})["id"]
        else:
            raise PermanentError(f"Format Facebook tidak dikenal: {fmt}")
        ctx.save_state(f"published:{post_id}")

        warnings = []
        try:
            permalink = self._get(post_id, {"fields": "permalink_url"}).get("permalink_url", "")
        except SocialError:
            permalink = ""
        permalink = permalink if permalink.startswith("http") else (
            f"https://www.facebook.com{permalink}" if permalink else f"https://www.facebook.com/{post_id}")
        if ctx.first_comment:
            self._first_comment(post_id, ctx.first_comment, warnings)
        return PublishResult(post_id, permalink, warnings)

    def _fb_album(self, ctx) -> str:
        """Unggah tiap foto tanpa publish (checkpoint per foto), lalu satu feed post dengan attached_media."""
        page, state = self.account.account_id, ctx.provider_state or ""
        photos = state.split(":", 1)[1].split(",") if state.startswith("photos:") else []
        items = self._items_or_raise(ctx)
        for item in items[len(photos):]:
            photos.append(self._post(f"{page}/photos", {"url": item.public_url, "published": "false"})["id"])
            ctx.save_state("photos:" + ",".join(photos))
        attached = {f"attached_media[{i}]": json.dumps({"media_fbid": pid}) for i, pid in enumerate(photos)}
        return self._post(f"{page}/feed", {"message": ctx.caption, **attached})["id"]

    def _first_comment(self, target_id, text, warnings):
        try:
            self._post(f"{target_id}/comments", {"message": text})
        except SocialError as exc:  # posting sudah terbit; komentar gagal bukan alasan menggagalkan semuanya
            warnings.append(f"first_comment gagal: {exc}")

    # ------------------------------------------------------------------ delete / metrics
    def delete(self, remote_id):
        if self.account.channel == "Instagram":
            raise UnsupportedOperation("Instagram Graph API tidak menyediakan penghapusan media; hapus manual di aplikasi Instagram.")
        self.client.request("DELETE", f"{self.base}/{remote_id}", headers=self._headers())

    def _first_insight(self, node, metrics):
        """Nama metrik insight sering berubah antar versi: coba satu per satu, ambil yang pertama berhasil."""
        for metric in metrics:
            try:
                data = self._get(f"{node}/insights", {"metric": metric}).get("data") or []
                if data and data[0].get("values"):
                    return int(data[0]["values"][0].get("value") or 0)
            except SocialError:
                continue
        return 0

    def fetch_metrics(self, remote_id, post_format):
        self.ensure_fresh_token()
        if self.account.channel == "Instagram":
            node = self._get(remote_id, {"fields": "like_count,comments_count"})
            out = {"likes": node.get("like_count", 0), "comments": node.get("comments_count", 0)}
            if post_format != "Story":
                out["impressions"] = self._first_insight(remote_id, ["views", "impressions"])
                out["reach"] = self._first_insight(remote_id, ["reach"])
                out["shares"] = self._first_insight(remote_id, ["shares"])
            return out
        node = self._get(remote_id, {
            "fields": "likes.summary(true).limit(0),comments.summary(true).limit(0),shares"})
        return {
            "likes": (node.get("likes") or {}).get("summary", {}).get("total_count", 0),
            "comments": (node.get("comments") or {}).get("summary", {}).get("total_count", 0),
            "shares": (node.get("shares") or {}).get("count", 0),
            "impressions": self._first_insight(remote_id, ["post_media_view", "post_impressions"]),
            "reach": self._first_insight(remote_id, ["post_impressions_unique"]),
        }

    # ------------------------------------------------------------------ comments
    def fetch_comments(self, remote_id, post_format):
        self.ensure_fresh_token()
        out = []
        if self.account.channel == "Instagram":
            if post_format == "Story":
                return out
            data = self._get(f"{remote_id}/comments", {
                "fields": "id,text,username,timestamp,replies{id,text,username,timestamp}", "limit": 50})
            own = self._ig_username()
            for c in data.get("data") or []:
                entries = [(c, None)] + [(r, c["id"]) for r in (c.get("replies") or {}).get("data") or []]
                for item, parent in entries:
                    if own and item.get("username") == own:
                        continue
                    out.append({"id": item["id"], "text": item.get("text", ""), "author": item.get("username", ""),
                                "author_id": item.get("username", ""), "created": item.get("timestamp"),
                                "parent_id": parent})
            return out
        data = self._get(f"{remote_id}/comments", {
            "fields": "id,message,from{id,name},created_time,parent{id}", "filter": "stream",
            "order": "reverse_chronological", "limit": 50})
        for c in data.get("data") or []:
            sender = c.get("from") or {}
            if sender.get("id") == self.account.account_id:
                continue  # balasan dari Page sendiri
            out.append({"id": c["id"], "text": c.get("message", ""), "author": sender.get("name", ""),
                        "author_id": sender.get("id", ""), "created": c.get("created_time"),
                        "parent_id": (c.get("parent") or {}).get("id")})
        return out

    def _ig_username(self):
        if not hasattr(self, "_username"):
            try:
                self._username = self._get(self.account.account_id, {"fields": "username"}).get("username", "")
            except SocialError:
                self._username = ""
        return self._username

    def reply_comment(self, remote_id, comment_id, text):
        self.ensure_fresh_token()
        path = f"{comment_id}/replies" if self.account.channel == "Instagram" else f"{comment_id}/comments"
        return str(self._post(path, {"message": text}).get("id", ""))
