"""Smoke test Gelombang 2-3 dengan stub `frappe` (jalankan dari root repo: python3 -I tests_wave2.py)."""
import datetime as dt
import json, os, sys, types
from types import SimpleNamespace as NS

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# ------------------------------------------------------------------ stub frappe
class Throw(Exception):
    pass

class PermissionError_(Exception):
    pass

class Row(dict):
    __getattr__ = lambda s, k: s.get(k)
    def __setattr__(s, k, v): s[k] = v
    def set(s, k, v): s[k] = v

class DocBase:
    def __init__(self, **kw):
        self.__dict__.update(kw)
        self._before = None
    def get(self, k, d=None): return getattr(self, k, d)
    def set(self, k, v): setattr(self, k, v)
    def get_doc_before_save(self): return self._before
    def is_new(self): return self._before is None

DB = {"exists": set(), "values": {}, "inserted": [], "single": {}}
ROLES = {"roles": set()}
frappe = types.ModuleType("frappe")
frappe._ = lambda s: s
frappe.throw = lambda msg, exc=None: (_ for _ in ()).throw(exc(msg) if exc else Throw(msg))
frappe.PermissionError = PermissionError_
frappe.flags = types.SimpleNamespace(get=lambda k, d=None: None)
frappe.get_roles = lambda: list(ROLES["roles"])
frappe.session = NS(user="mgr")
frappe.log_error = lambda **kw: None
class _Doc(NS):
    def insert(self, **kw):
        DB["inserted"].append(self.__dict__.copy()); self.name = self.__dict__.get("code") or "NEW-1"; self.code = self.name; return self
frappe.get_doc = lambda d: _Doc(**d)
def get_single_value(dt_, f): return DB["single"].get(f)
def get_value(dt_, filt, fields=None, as_dict=False):
    key = (dt_, json.dumps(filt, sort_keys=True, default=str) if isinstance(filt, dict) else filt)
    return DB["values"].get(key)
frappe.db = NS(exists=lambda dt_, f=None: (dt_, json.dumps(f, sort_keys=True, default=str)) in DB["exists"],
               get_single_value=get_single_value, get_value=get_value, commit=lambda: None, rollback=lambda **k: None,
               savepoint=lambda n: None)
fu = types.ModuleType("frappe.utils")
NOW = dt.datetime(2026, 11, 21, 12, 0)
fu.now_datetime = lambda: NOW
fu.add_days = lambda d, n: d + dt.timedelta(days=n)
fu.get_datetime = lambda v: v if isinstance(v, dt.datetime) else dt.datetime.fromisoformat(str(v).replace("/", "-"))
fu.getdate = lambda v: v if isinstance(v, dt.date) and not isinstance(v, dt.datetime) else (v.date() if isinstance(v, dt.datetime) else dt.date.fromisoformat(str(v)))
fu.add_to_date = lambda d, **kw: d + dt.timedelta(**{k: v for k, v in kw.items()})
fu.get_url = lambda: "https://erp.example.com"
fu.convert_utc_to_system_timezone = lambda d: d + dt.timedelta(hours=7)
frappe.utils = fu
fm = types.ModuleType("frappe.model"); fd = types.ModuleType("frappe.model.document"); fd.Document = DocBase
frappe.model = fm; fm.document = fd
sys.modules.update({"frappe": frappe, "frappe.utils": fu, "frappe.model": fm, "frappe.model.document": fd})
req = types.ModuleType("requests"); req.Session = object; req.ConnectionError = req.Timeout = Exception
req.exceptions = NS(ChunkedEncodingError=Exception); sys.modules.setdefault("requests", req)
pw = types.ModuleType("frappe.utils.password"); pw.get_decrypted_password = lambda *a, **k: ""; pw.set_encrypted_password = lambda *a, **k: None
sys.modules["frappe.utils.password"] = pw

# ------------------------------------------------------------------ library
from energyx_social.services.library import normalize_tags
assert normalize_tags("Promo, #Produk ; promo\nRamadan ,,") == "promo, produk, ramadan"

# ------------------------------------------------------------------ media rules
from energyx_social.services import media as M
assert M.multi_limits("Instagram", "Carousel") == (2, 10) and M.multi_limits("Facebook Page", "Album") == (2, 10)
assert M.multi_limits("Instagram", "Post") is None and M.requires_media("LinkedIn", "Photo") and not M.requires_media("LinkedIn", "Text")
svc = M.MediaService()
info = M.MediaInfo("a.jpg", "image", "image/jpeg", 9 * M.MB)
try:
    svc.preflight(info, "Instagram", "Carousel"); raise SystemExit("image 9MB must fail on IG carousel")
except M.MediaError:
    pass
svc.preflight(M.MediaInfo("v.mp4", "video", "video/mp4", 50 * M.MB), "Instagram", "Carousel")

# ------------------------------------------------------------------ links
from energyx_social.services import links as L
DB["single"]["public_base_url"] = "https://erp.example.com"
assert L.resolve_mode("Default", "UTM only") == "UTM only" and L.resolve_mode("None", "UTM only") == "None" and L.resolve_mode("", None) == "None"
out = L.track_text("Cek https://shop.com/p. Ok!", post="P1", channel="Instagram", post_format="Post", title="Promo Akhir Tahun",
                   mode="UTM only")
assert out == "Cek https://shop.com/p?utm_source=instagram&utm_medium=social&utm_campaign=promo-akhir-tahun&utm_content=post. Ok!", out
assert L.track_text("x https://a.com", post="P", channel="TikTok", post_format="Video", title="t", mode="None") == "x https://a.com"
codes = iter(["abc", "abc", "xyz"])
class R:  # rng deterministik
    def choice(self, seq): return seq[0]
assert L.new_code(lambda c: False, 3, R()) == "aaa"
DB["values"][("Social Short Link", json.dumps({"post": "P", "channel": "YouTube", "target_url": "https://a.com"}, sort_keys=True))] = "CODE123"
short = L.track_text("see https://a.com now", post="P", channel="YouTube", post_format="Video", title="t", mode="UTM + Short link")
assert short == "see https://erp.example.com/s/CODE123 now", short
assert L.track_text("https://erp.example.com/s/CODE123", post="P", channel="YouTube", post_format="Video", title="t", mode="UTM + Short link") == "https://erp.example.com/s/CODE123"

# ------------------------------------------------------------------ recurring
from energyx_social.services.recurring import next_occurrence, to_time
assert to_time(dt.timedelta(hours=9, minutes=30)) == dt.time(9, 30) and to_time("09:30:00") == dt.time(9, 30)
sat = dt.datetime(2026, 11, 21, 12, 0)  # Sabtu
assert next_occurrence("Daily", sat, "13:00:00") == dt.datetime(2026, 11, 21, 13, 0)
assert next_occurrence("Daily", sat, "11:00:00") == dt.datetime(2026, 11, 22, 11, 0)
assert next_occurrence("Weekly", sat, "09:00:00", weekday="Monday") == dt.datetime(2026, 11, 23, 9, 0)
assert next_occurrence("Weekly", sat, "09:00:00", weekday="Saturday") == dt.datetime(2026, 11, 28, 9, 0)
assert next_occurrence("Monthly", sat, "09:00:00", day_of_month=5) == dt.datetime(2026, 12, 5, 9, 0)
assert next_occurrence("Monthly", sat, "09:00:00", day_of_month=28) == dt.datetime(2026, 11, 28, 9, 0)
assert next_occurrence("Daily", sat, "09:00:00", start_date=dt.date(2027, 1, 10)) == dt.datetime(2027, 1, 10, 9, 0)

# ------------------------------------------------------------------ bulk
from energyx_social.services import bulk as B
csv_text = "title;caption;media;channels;formats;scheduled_at\nPromo;Halo;;Instagram:Brand IG; Facebook Page;;2026-12-01 09:00\n\n".encode()
rows = B.parse_table("title,caption,channels,scheduled_at\n\"Promo\",\"Halo\",\"Instagram:Brand IG;Facebook Page\",2026-12-01 09:00\n".encode(), "x.csv")
assert rows == [{"title": "Promo", "caption": "Halo", "channels": "Instagram:Brand IG;Facebook Page", "scheduled_at": "2026-12-01 09:00"}], rows
accounts = [{"name": "A1", "channel": "Instagram", "account_name": "Brand IG"}, {"name": "A2", "channel": "Instagram", "account_name": "Second IG"},
            {"name": "A3", "channel": "Facebook Page", "account_name": "Brand FB"}, {"name": "A4", "channel": "LinkedIn", "account_name": "Co"}]
FM = {"Instagram": ["Post", "Reel", "Story", "Carousel"], "Facebook Page": ["Photo", "Video", "Text", "Album"], "LinkedIn": ["Text", "Photo", "Video"]}
ch = B.parse_channels("Instagram:brand ig; Facebook Page", "Instagram=reel", accounts, True, FM)
assert ch == [{"channel": "Instagram", "account": "A1", "post_format": "Reel", "active": 1},
              {"channel": "Facebook Page", "account": "A3", "post_format": "Photo", "active": 1}], ch
assert B.parse_channels("Facebook Page;LinkedIn", "", accounts, False, FM)[0]["post_format"] == "Text"
for bad in ("Instagram", "Twitter", "Instagram:Nope", ""):
    try:
        B.parse_channels(bad, "", accounts, True, FM); raise SystemExit("must fail: " + bad)
    except ValueError:
        pass
plan = B.plan_row({"title": "T", "caption": "Hi", "channels": "LinkedIn", "hashtags": "promo, #Promo", "scheduled_at": "2026-12-01 09:00"}, accounts, FM)
assert plan["base_caption"] == "Hi\n\n#promo" and plan["default_scheduled_at"] == dt.datetime(2026, 12, 1, 9, 0) and plan["status"] == "Draft"
for bad in ({"title": "", "channels": "LinkedIn"}, {"title": "x", "channels": "LinkedIn", "scheduled_at": "2020-01-01 09:00"}):
    try:
        B.plan_row(bad, accounts, FM); raise SystemExit("must fail")
    except ValueError:
        pass

# ------------------------------------------------------------------ comments
from energyx_social.services import comments as C
t = C.parse_remote_time("2026-11-20T10:00:00+0000")
assert t == dt.datetime(2026, 11, 20, 17, 0), t
row = NS(channel="YouTube", account="A1", account_label="YT", parent="SPOST-1", name="ROW1", permalink="https://y/1", get=lambda k, d=None: {"account_label": "YT", "permalink": "https://y/1"}.get(k, d))
DB["exists"].add(("Social Comment", json.dumps({"remote_comment_id": "old"}, sort_keys=True)))
DB["inserted"].clear()
n = C.store_comments(row, [{"id": "old", "text": "dup"}, {"id": "new1", "text": "Bagus!", "author": "Ani", "created": "2026-11-20T10:00:00Z"},
                           {"id": "", "text": "x"}, {"id": "r1", "text": "ya", "parent_id": "new1"}])
assert n == 2 and [d["remote_comment_id"] for d in DB["inserted"]] == ["new1", "r1"] and DB["inserted"][1]["parent_comment_id"] == "new1"

# ------------------------------------------------------------------ providers (fake client)
from energyx_social.services.providers.base import PublishContext
from energyx_social.services.providers import PROVIDERS
from energyx_social.services.providers.meta import MetaProvider
from energyx_social.services.providers.linkedin import LinkedInProvider, escape_commentary
from energyx_social.services.credentials import Account
assert set(PROVIDERS) == {"Instagram", "Facebook Page", "YouTube", "TikTok", "LinkedIn"}
assert escape_commentary("a_b (c) #tag @x") == "a\\_b \\(c\\) #tag \\@x"

class Resp:
    def __init__(self, body=None, headers=None, status=200):
        self.body, self.headers, self.status_code = body or {}, headers or {}, status
    def json(self): return self.body

class FakeClient:
    def __init__(self, script): self.calls, self.script = [], script
    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for key, resp in self.script:
            if key in f"{method} {url}" or key in str(kw.get("params")):
                return resp(kw) if callable(resp) else resp
        raise AssertionError(f"unexpected {method} {url}")

def account(channel, **kw):
    base = dict(name="A", channel=channel, account_name="x", account_id="123", app_id="", api_version="", token_expires_on=None,
                playlist_id="", enabled=True, access_token="TOKEN")
    base.update(kw)
    return Account(**base)

def media(url, kind="image"):
    return NS(public_url=url, kind=kind, local_path=None, mime=kind + "/x", source=url)

states = []
ig_ids = iter(["c1", "c2", "car"])
client = FakeClient([
    ("POST https://graph.facebook.com/v21.0/123/media_publish", Resp({"id": "MEDIA9"})),
    ("POST https://graph.facebook.com/v21.0/123/media", lambda kw: Resp({"id": next(ig_ids)})),
    ("status_code", Resp({"status_code": "FINISHED"})),
    ("permalink", Resp({"permalink": "https://instagram.com/p/x"})),
])
prov = MetaProvider(account("Instagram"), client)
ctx = PublishContext(post="P", row="R", title="t", caption="cap", post_format="Carousel",
                     media_items=[media("https://a/1.jpg"), media("https://a/2.mp4", "video")], save_state=states.append)
res = prov.publish(ctx)
assert res.remote_id == "MEDIA9" and res.permalink.endswith("/p/x"), res
assert states == ["children:c1", "children:c1,c2", "container:car", "published:MEDIA9"], states
posts = [c for c in client.calls if c[0] == "POST" and c[1].endswith("/123/media")]
assert posts[0][2]["data"]["image_url"] == "https://a/1.jpg" and posts[0][2]["data"]["is_carousel_item"] == "true"
assert posts[1][2]["data"]["media_type"] == "VIDEO" and posts[2][2]["data"] == {"media_type": "CAROUSEL", "children": "c1,c2", "caption": "cap"}
# resume: children sudah ada -> tidak dibuat ulang
client2 = FakeClient([("POST https://graph.facebook.com/v21.0/123/media_publish", Resp({"id": "M"})),
                      ("POST https://graph.facebook.com/v21.0/123/media", lambda kw: Resp({"id": "car2"})),
                      ("status_code", Resp({"status_code": "FINISHED"})), ("permalink", Resp({}))])
ctx = PublishContext(post="P", row="R", title="t", caption="cap", post_format="Carousel", provider_state="children:c1,c2",
                     media_items=[media("https://a/1.jpg"), media("https://a/2.jpg")], save_state=lambda v: None)
MetaProvider(account("Instagram"), client2).publish(ctx)
assert len([c for c in client2.calls if c[1].endswith("/123/media")]) == 1  # hanya container CAROUSEL

fb_ids = iter(["ph1", "ph2"]); states = []
client = FakeClient([("POST https://graph.facebook.com/v21.0/123/photos", lambda kw: Resp({"id": next(fb_ids)})),
                     ("POST https://graph.facebook.com/v21.0/123/feed", Resp({"id": "123_9"})), ("permalink_url", Resp({"permalink_url": "/x/1"}))])
res = MetaProvider(account("Facebook Page"), client).publish(PublishContext(
    post="P", row="R", title="t", caption="cap", post_format="Album", media_items=[media("https://a/1.jpg"), media("https://a/2.jpg")], save_state=states.append))
feed = [c for c in client.calls if c[1].endswith("/feed")][0][2]["data"]
assert json.loads(feed["attached_media[1]"]) == {"media_fbid": "ph2"} and feed["message"] == "cap" and res.remote_id == "123_9", feed
assert states[:2] == ["photos:ph1", "photos:ph1,ph2"]

# komentar Meta
client = FakeClient([("/username", Resp({})), ("comments", Resp({"data": [
    {"id": "1", "message": "hai", "from": {"id": "u1", "name": "Ani"}, "created_time": "2026-11-20T10:00:00+0000"},
    {"id": "2", "message": "balas Page", "from": {"id": "123", "name": "Page"}, "created_time": "2026-11-20T10:01:00+0000"}]}))])
got = MetaProvider(account("Facebook Page"), client).fetch_comments("123_9", "Photo")
assert [c["id"] for c in got] == ["1"]
client = FakeClient([("POST", Resp({"id": "rep1"}))])
assert MetaProvider(account("Instagram"), client).reply_comment("m", "c9", "hai") == "rep1"
assert client.calls[0][1].endswith("/c9/replies")

# LinkedIn
client = FakeClient([("POST https://api.linkedin.com/rest/posts", Resp(headers={"x-restli-id": "urn:li:share:77"}, status=201))])
st = []
res = LinkedInProvider(account("LinkedIn", account_id="urn:li:organization:5"), client).publish(PublishContext(
    post="P", row="R", title="t", caption="Halo (dunia) #tag", post_format="Text", save_state=st.append))
body = client.calls[0][2]["json"]
assert body["author"] == "urn:li:organization:5" and body["commentary"] == "Halo \\(dunia\\) #tag" and "content" not in body
assert res.permalink.endswith("urn:li:share:77") and st == ["published:urn:li:share:77"]
assert client.calls[0][2]["headers"]["LinkedIn-Version"] and client.calls[0][2]["headers"]["X-Restli-Protocol-Version"] == "2.0.0"
try:
    LinkedInProvider(account("LinkedIn", account_id="123"), client).publish(PublishContext(post="P", row="R", title="", caption="x", post_format="Text"))
    raise SystemExit("bad URN must fail")
except Exception as e:
    assert type(e).__name__ == "PermanentError"
client = FakeClient([("images", Resp({"value": {"uploadUrl": "https://up/1", "image": "urn:li:image:9"}})), ("PUT https://up/1", Resp()),
                     ("POST https://api.linkedin.com/rest/posts", Resp(headers={"x-restli-id": "urn:li:share:1"}, status=201))])
import tempfile
with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as fh: fh.write(b"x" * 10)
m = media("x"); m.local_path = fh.name
LinkedInProvider(account("LinkedIn", account_id="urn:li:person:1"), client).publish(PublishContext(post="P", row="R", title="", caption="x", post_format="Photo", media=m, save_state=lambda v: None))
assert client.calls[-1][2]["json"]["content"] == {"media": {"id": "urn:li:image:9"}}
os.unlink(fh.name)

# ------------------------------------------------------------------ Social Post: approval bertingkat + catatan revisi
sys.modules["energyx_social.services.library"].apply_asset = lambda *a, **k: None
from energyx_social.social_posting.doctype.social_post import social_post as SP
assert "Carousel" in SP.FORMATS["Instagram"] and SP.FORMATS["LinkedIn"] == ["Text", "Photo", "Video"] and SP.CAPTION_LIMITS["LinkedIn"] == 3000

def post(status, notes=(), needs=0, before=None):
    p = SP.SocialPost(status=status, needs_final_approval=needs, channels=[], media_items=[], approved_by=None, final_approved_by=None,
                      revision_notes=[Row(n) for n in notes])
    p.approved_on = p.final_approved_on = None
    p._before = before
    return p

def run(fn, roles, expect=None):
    ROLES["roles"] = set(roles)
    try:
        fn()
    except (Throw, PermissionError_) as e:
        assert expect and expect in str(e), (expect, str(e))
        return
    assert not expect, f"expected error {expect!r}"

OPEN = {"status": "Open", "note": "ganti caption", "note_type": "Caption", "name": "n1"}
# Draft -> Pending Approval: tidak boleh ada note Open; flag diambil dari settings
DB["single"]["require_final_approval"] = 1
p = post("Pending Approval", [OPEN], before=post("Draft"))
run(p._handle_transitions, ["Social Editor"], "catatan revisi")
p = post("Pending Approval", [dict(OPEN, status="Resolved")], before=post("Draft"))
run(p._handle_transitions, ["Social Editor"]); assert p.needs_final_approval == 1
# Level 1: Pending Approval -> Pending Final Approval (wajib bila needs)
p = post("Approved", needs=1, before=post("Pending Approval", needs=1))
run(p._handle_transitions, ["Social Manager"], "final approval")
p = post("Pending Final Approval", needs=1, before=post("Pending Approval", needs=1))
run(p._handle_transitions, ["Social Editor"], "Hanya Social Manager")
run(p._handle_transitions, ["Social Manager"]); assert p.approved_by == "mgr" and not p.final_approved_by
# Tanpa needs, tidak boleh ke Pending Final
p = post("Pending Final Approval", needs=0, before=post("Pending Approval", needs=0))
run(p._handle_transitions, ["Social Manager"], "tidak diaktifkan")
# Single-level
p = post("Approved", needs=0, before=post("Pending Approval", needs=0))
run(p._handle_transitions, ["Social Manager"]); assert p.approved_by == "mgr"
# Final approve: hanya Final Approver
p = post("Approved", needs=1, before=post("Pending Final Approval", needs=1))
run(p._handle_transitions, ["Social Manager"], "Social Final Approver")
run(p._handle_transitions, ["Social Final Approver"]); assert p.final_approved_by == "mgr"
# Reject butuh catatan Open; Final Approver menolak di level 2
p = post("Draft", [], needs=1, before=post("Pending Final Approval", needs=1))
run(p._handle_transitions, ["Social Final Approver"], "catatan revisi")
p = post("Draft", [OPEN], needs=1, before=post("Pending Final Approval", needs=1))
run(p._handle_transitions, ["Social Manager"], "tidak berwenang")
p.approved_by = "x"; p.final_approved_by = "y"
run(p._handle_transitions, ["Social Final Approver"]); assert p.approved_by is None and p.final_approved_by is None
# Catatan revisi: editor tidak boleh membuat/ubah/hapus
old = post("Pending Approval", [OPEN])
p = post("Pending Approval", [OPEN, {"status": "Open", "note": "baru", "note_type": "Media"}], before=old)
run(p._validate_revision_notes, ["Social Editor"], "Hanya reviewer")
p = post("Pending Approval", [OPEN, {"status": "Open", "note": "baru", "note_type": "Media"}], before=old)
run(p._validate_revision_notes, ["Social Manager"]); n = p.revision_notes[1]
assert n.raised_by == "mgr" and n.reviewer_level == "Level 1" and n.raised_on == NOW
p = post("Pending Approval", [dict(OPEN, note="diubah editor")], before=old)
run(p._validate_revision_notes, ["Social Editor"], "hanya dapat diubah oleh reviewer")
p = post("Pending Approval", [], before=old)
run(p._validate_revision_notes, ["Social Editor"], "tidak boleh dihapus")
p = post("Pending Approval", [dict(OPEN, status="Resolved", resolution="sudah")], before=old)
run(p._validate_revision_notes, ["Social Editor"]); assert p.revision_notes[0].resolved_by == "mgr"
p = post("Pending Approval", [dict(OPEN)], before=post("Pending Approval", [dict(OPEN, status="Resolved")]))
run(p._validate_revision_notes, ["Social Editor"], "membuka kembali")

# ------------------------------------------------------------------ install: transisi lama diperluas tanpa menimpa
from energyx_social.setup import install as I
assert "Social Final Approver" in I.ROLES and any(s[0] == "Pending Final Approval" for s in I.STATES)
assert I.CONDITIONS[("Pending Approval", "Approve", "Approved")] == "not doc.needs_final_approval"
triples = [(s, a, n) for s, a, n, _ in I.TRANSITIONS]
assert len(triples) == len(set(triples))

# ------------------------------------------------------------------ report aggregate
from energyx_social.social_posting.report.social_analytics import social_analytics as SA
def r(row, ch, acc, pub, **m):
    d = dict(row_name=row, post="P" + row, title="T" + row, channel=ch, account=acc, account_label=acc, post_format="Post",
             published_on=pub, permalink="", impressions=0, reach=0, likes=0, comments=0, shares=0)
    d.update(m)
    return d
data = [r("1", "Instagram", "ig", dt.datetime(2026, 11, 16, 9, 5), reach=100, likes=10),
        r("2", "Instagram", "ig", dt.datetime(2026, 11, 17, 9, 40), reach=100, likes=30),
        r("3", "Facebook Page", "fb", dt.datetime(2026, 11, 24, 20, 0), impressions=200, comments=4, shares=6)]
by = {g["label"]: g for g in SA.aggregate(data, "Hour of Day")}
assert by["09:00"]["posts"] == 2 and by["09:00"]["engagement_rate"] == 20.0 and by["20:00"]["engagement_rate"] == 5.0
assert [g["label"] for g in SA.aggregate(data, "Week")] == ["2026-11-16", "2026-11-23"]
assert SA.aggregate(data, "Channel")[0]["label"] == "Instagram"
assert [g["label"] for g in SA.aggregate(data, "Weekday")] == ["Monday", "Tuesday"]
s = SA.summary(data, SA.aggregate(data, "Hour of Day"), "Hour of Day")
assert "09:00" in s[-1]["value"]
assert SA.chart("Week", SA.aggregate(data, "Week"))["type"] == "line"
print("wave2/3 tests OK")
