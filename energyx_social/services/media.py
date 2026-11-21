"""MediaService: file lokal -> URL publik, validasi preflight (HTTP 200, ukuran, format)."""
import contextlib
import ipaddress
import mimetypes
import os
import shutil
import socket
import tempfile
import uuid
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

import frappe
import requests

from energyx_social.services.errors import MediaError

MB = 1024 * 1024
VIDEO = {"video/mp4", "video/quicktime"}

# Batas bawaan yang konservatif. Platform sering mengubahnya -> verifikasi ke dokumentasi resmi.
RULES = {
    ("Instagram", "Post"): {"kinds": {"image"}, "mimes": {"image/jpeg"}, "max_mb": 8},
    ("Instagram", "Story"): {"kinds": {"image", "video"}, "mimes": {"image/jpeg"} | VIDEO, "max_mb": 100},
    ("Instagram", "Reel"): {"kinds": {"video"}, "mimes": VIDEO, "max_mb": 300},
    ("Facebook Page", "Photo"): {"kinds": {"image"}, "mimes": {"image/jpeg", "image/png", "image/gif"}, "max_mb": 10},
    ("Facebook Page", "Video"): {"kinds": {"video"}, "mimes": VIDEO, "max_mb": 1024},
    ("Facebook Page", "Text"): {"kinds": set(), "mimes": set(), "max_mb": 0},
    ("YouTube", "Short"): {"kinds": {"video"}, "mimes": VIDEO | {"video/webm"}, "max_mb": 4096},
    ("YouTube", "Video"): {"kinds": {"video"}, "mimes": VIDEO | {"video/webm"}, "max_mb": 8192},
    ("YouTube", "Thumbnail"): {"kinds": {"image"}, "mimes": {"image/jpeg", "image/png"}, "max_mb": 2},
    ("TikTok", "Video"): {"kinds": {"video"}, "mimes": VIDEO | {"video/webm"}, "max_mb": 4096},
    ("TikTok", "Photo"): {"kinds": {"image"}, "mimes": {"image/jpeg", "image/webp"}, "max_mb": 20},
    # Carousel / album: aturan berlaku per item; min_items/max_items menandai format multi-media.
    ("Instagram", "Carousel"): {"kinds": {"image", "video"}, "mimes": {"image/jpeg"} | VIDEO, "max_mb": 100,
                                "kind_max_mb": {"image": 8}, "min_items": 2, "max_items": 10},
    ("Facebook Page", "Album"): {"kinds": {"image"}, "mimes": {"image/jpeg", "image/png", "image/gif"}, "max_mb": 10,
                                 "min_items": 2, "max_items": 10},
    ("LinkedIn", "Text"): {"kinds": set(), "mimes": set(), "max_mb": 0},
    ("LinkedIn", "Photo"): {"kinds": {"image"}, "mimes": {"image/jpeg", "image/png", "image/gif"}, "max_mb": 10},
    ("LinkedIn", "Video"): {"kinds": {"video"}, "mimes": {"video/mp4"}, "max_mb": 200},
}


@dataclass
class MediaInfo:
    source: str
    kind: str
    mime: str
    size: int
    public_url: str | None = None
    local_path: str | None = None
    is_private: bool = False
    _cleanups: list = field(default_factory=list, repr=False)


def _is_external(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def _assert_public_host(url: str):
    """Cegah SSRF dari URL eksternal yang diketik user (tidak melindungi dari DNS rebinding)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise MediaError("URL media eksternal harus https.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
    except socket.gaierror:
        raise MediaError(f"Host media tidak dapat di-resolve: {parsed.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise MediaError("URL media eksternal mengarah ke alamat internal.")


def requires_media(channel: str, post_format: str) -> bool:
    return bool(RULES.get((channel, post_format), {}).get("kinds"))


def multi_limits(channel: str, post_format: str):
    """(min_items, max_items) untuk format carousel/album, None untuk format satu-media."""
    rule = RULES.get((channel, post_format)) or {}
    if rule.get("max_items"):
        return rule.get("min_items", 2), rule["max_items"]
    return None


class MediaService:
    def __init__(self, session=None):
        self.session = session or requests.Session()

    @staticmethod
    def public_base_url() -> str:
        base = frappe.db.get_single_value("Social Posting Settings", "public_base_url") or frappe.utils.get_url()
        return base.rstrip("/")

    @contextlib.contextmanager
    def prepared(self, source, channel, post_format, *, public=False, local=False):
        """Yield MediaInfo yang sudah lolos preflight; bersihkan salinan/temporer di akhir."""
        if not source:
            yield None
            return
        info = self.inspect(source)
        try:
            self.preflight(info, channel, post_format)
            if public:
                self._ensure_public(info)
                self.check_reachable(info)
            if local:
                self._ensure_local(info, channel, post_format)
            yield info
        finally:
            self.release(info)

    # ------------------------------------------------------------------ inspect
    def inspect(self, source: str) -> MediaInfo:
        if _is_external(source):
            _assert_public_host(source)
            resp = self.session.get(source, headers={"Range": "bytes=0-0"}, stream=True, timeout=20)
            try:
                if resp.status_code not in (200, 206):
                    raise MediaError(f"URL media mengembalikan HTTP {resp.status_code}.")
                mime = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                size = self._size_from_headers(resp)
            finally:
                resp.close()
            return MediaInfo(source, mime.split("/")[0], mime, size, public_url=source)

        file = frappe.db.get_value("File", {"file_url": source}, ["name", "is_private"], as_dict=True)
        if not file:
            raise MediaError(f"File tidak ditemukan: {source}")
        path = frappe.get_doc("File", file.name).get_full_path()
        if not os.path.exists(path):
            raise MediaError(f"File tidak ada di disk: {source}")
        mime = (mimetypes.guess_type(path)[0] or "").lower()
        return MediaInfo(source, mime.split("/")[0], mime, os.path.getsize(path),
                         local_path=path, is_private=bool(file.is_private))

    @staticmethod
    def _size_from_headers(resp) -> int:
        cr = resp.headers.get("Content-Range", "")
        if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
            return int(cr.rsplit("/", 1)[1])
        return int(resp.headers.get("Content-Length", 0) or 0)

    # ------------------------------------------------------------------ preflight
    def preflight(self, info: MediaInfo, channel: str, post_format: str):
        rule = RULES.get((channel, post_format))
        if not rule:
            raise MediaError(f"Kombinasi {channel} / {post_format} tidak didukung.")
        if info.kind not in rule["kinds"]:
            raise MediaError(f"{channel} {post_format} membutuhkan {'/'.join(sorted(rule['kinds']))}, bukan '{info.mime}'.")
        if info.mime not in rule["mimes"]:
            raise MediaError(f"Format {info.mime} tidak didukung untuk {channel} {post_format} "
                             f"(boleh: {', '.join(sorted(rule['mimes']))}).")
        limit_mb = rule.get("kind_max_mb", {}).get(info.kind, rule["max_mb"])
        if info.size and info.size > limit_mb * MB:
            raise MediaError(f"Ukuran {info.size / MB:.1f} MB melebihi batas {limit_mb} MB untuk {channel} {post_format} ({info.kind}).")
        if not info.size:
            raise MediaError("File media kosong.")

    def check_reachable(self, info: MediaInfo):
        """Meta/TikTok mengunduh sendiri dari URL: pastikan benar-benar HTTP 200 dan bukan halaman login."""
        if info.source == info.public_url:
            return  # URL eksternal sudah dicek di inspect()
        try:
            resp = self.session.get(info.public_url, headers={"Range": "bytes=0-0"}, stream=True, timeout=20)
        except requests.RequestException as exc:
            raise MediaError(f"URL publik tidak dapat dijangkau ({type(exc).__name__}). Periksa Public Base URL.")
        try:
            if resp.status_code not in (200, 206):
                raise MediaError(f"URL publik media mengembalikan HTTP {resp.status_code}.")
            ctype = resp.headers.get("Content-Type", "")
            if not ctype.startswith(info.kind):
                raise MediaError(f"URL publik mengembalikan '{ctype}', bukan {info.kind} (mungkin butuh login).")
        finally:
            resp.close()

    # ------------------------------------------------------------------ public / local
    def _ensure_public(self, info: MediaInfo):
        if info.public_url:
            return
        base = self.public_base_url()
        if not info.is_private:
            info.public_url = base + quote(info.source)
            return
        # File private tidak bisa diambil Meta/TikTok -> salinan publik sementara dengan nama acak.
        ext = os.path.splitext(info.local_path)[1]
        name = f"social-tmp-{uuid.uuid4().hex}{ext}"
        shutil.copyfile(info.local_path, frappe.get_site_path("public", "files", name))
        doc = frappe.get_doc({"doctype": "File", "file_name": name, "file_url": f"/files/{name}", "is_private": 0}) \
            .insert(ignore_permissions=True)
        info._cleanups.append(lambda: frappe.delete_doc("File", doc.name, ignore_permissions=True, force=True))
        info.public_url = base + f"/files/{name}"

    def _ensure_local(self, info: MediaInfo, channel: str, post_format: str):
        if info.local_path:
            return
        limit = RULES[(channel, post_format)]["max_mb"] * MB
        fd, path = tempfile.mkstemp(prefix="social-dl-")
        info._cleanups.append(lambda: os.path.exists(path) and os.remove(path))
        total = 0
        with os.fdopen(fd, "wb") as fh, self.session.get(info.source, stream=True, timeout=(10, 120)) as resp:
            if resp.status_code != 200:
                raise MediaError(f"Gagal mengunduh media: HTTP {resp.status_code}")
            for chunk in resp.iter_content(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise MediaError("Media melebihi batas ukuran saat diunduh.")
                fh.write(chunk)
        info.local_path, info.size = path, total

    def release(self, info: MediaInfo):
        for fn in info._cleanups:
            try:
                fn()
            except Exception:
                frappe.log_error(title="Social Posting: gagal membersihkan media sementara")
        info._cleanups.clear()
