"""Smoke test Gelombang 1 dengan stub `frappe` (jalankan dari root repo: python3 -I tests_wave1.py)."""
import os, sys, types
from datetime import date, timedelta
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

created = []          # Notification Log yang dibuat
DB = {"roles": {"Social Manager": ["mgr1", "mgr2", "ed1"]}}


class Doc(NS):
    def insert(self, **kw):
        created.append(self.__dict__.copy())
        return self


def get_all(doctype, filters=None, pluck=None, **kw):
    if doctype == "Has Role":
        return DB["roles"].get(filters["role"], [])
    if doctype == "User":
        return [u for u in filters["name"][1] if u != "disabled1"]
    return []


frappe = types.ModuleType("frappe")
frappe.session = NS(user="ed1")
frappe.get_all = get_all
frappe.get_doc = lambda d: Doc(**d)
frappe.log_error = lambda **kw: None
frappe.db = NS(get_value=lambda dt, name, fields, as_dict=False: NS(title="Promo", requested_by="ed1"))
sys.modules["frappe"] = frappe

from energyx_social.services.hashtags import normalize_hashtags
from energyx_social import notifications as n

# ---- hashtag
assert normalize_hashtags("promo, #Energi  #energi\nsolar_panel;  ##ganda #  x") == "#promo #Energi #solar_panel #ganda #x"
assert normalize_hashtags("") == "" and normalize_hashtags("  ,; ") == ""

# ---- notifikasi: diajukan -> manajer (kecuali diri sendiri)
def doc(old, new, **kw):
    d = NS(title="Promo", name="SPOST-1", status=new, requested_by="ed1", approved_by="mgr1", **kw)
    d.get_doc_before_save = lambda: NS(status=old) if old else None
    return d

created.clear(); frappe.session.user = "ed1"
n.on_post_update(doc("Draft", "Pending Approval"))
assert sorted(c["for_user"] for c in created) == ["mgr1", "mgr2"], created   # ed1 (aktor) tidak dinotifikasi
assert all(c["document_name"] == "SPOST-1" for c in created)

# disetujui -> editor
created.clear(); frappe.session.user = "mgr1"
n.on_post_update(doc("Pending Approval", "Approved"))
assert [c["for_user"] for c in created] == ["ed1"] and "Disetujui" in created[0]["subject"]

# ditolak -> editor
created.clear(); n.on_post_update(doc("Pending Approval", "Draft"))
assert [c["for_user"] for c in created] == ["ed1"] and "Ditolak" in created[0]["subject"]

# dokumen baru / status tak berubah -> tidak ada notifikasi
created.clear(); n.on_post_update(doc(None, "Draft")); n.on_post_update(doc("Draft", "Draft"))
assert created == []

# hasil publish & gagal (aktor = Administrator di job latar belakang)
created.clear(); frappe.session.user = "Administrator"
n.notify_publish_result("SPOST-1", "Published")
assert [c["for_user"] for c in created] == ["ed1"] and created[0]["from_user"] is None
created.clear(); n.notify_publish_result("SPOST-1", "Partial")
assert "Sebagian" in created[0]["subject"]
created.clear(); n.notify_channel_failed("SPOST-1", "Instagram", "x" * 500)
assert sorted(c["for_user"] for c in created) == ["ed1", "mgr1", "mgr2"]    # editor + semua Social Manager, tanpa duplikat
assert all(len(c["email_content"]) <= 320 for c in created)
created.clear(); n.notify_publish_result("SPOST-1", "Approved")             # status lain diabaikan
assert created == []

# ---- minggu rekap = Senin
for d in (date(2026, 11, 16), date(2026, 11, 18), date(2026, 11, 22)):       # Sen, Rab, Min
    assert d - timedelta(days=d.weekday()) == date(2026, 11, 16)
assert date(2026, 11, 23) - timedelta(days=date(2026, 11, 23).weekday()) == date(2026, 11, 23)
print("tests_wave1: semua lolos")
