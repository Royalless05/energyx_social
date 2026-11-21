"""Normalisasi hashtag (logika murni, bisa diuji tanpa framework)."""
import re

_TOKEN = re.compile(r"#?[^\s#,;]+", re.UNICODE)


def normalize_hashtags(text: str) -> str:
    """Pisahkan dengan spasi/baris/koma, tambahkan '#' bila belum ada, buang duplikat (tanpa membedakan huruf besar/kecil)."""
    seen, out = set(), []
    for raw in _TOKEN.findall(text or ""):
        tag = "#" + raw.lstrip("#")
        if len(tag) < 2:
            continue
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            out.append(tag)
    return " ".join(out)
