"""Smoke test logika murni dengan stub `frappe` (frappe tidak terpasang di sandbox)."""
import sys, types
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m

class Document:
    def get(self, k, d=None): return getattr(self, k, d)
    def set(self, k, v): setattr(self, k, v)

def add_to_date(dt, **kw): return dt + timedelta(**{k: v for k, v in kw.items()})
frappe = mod("frappe", _=lambda s: s, throw=lambda m, *a: (_ for _ in ()).throw(Exception(m)),
             PermissionError=PermissionError, get_roles=lambda: ["Social Manager"],
             session=NS(user="u@x"), whitelist=lambda **k: (lambda f: f))
mod("frappe.utils", add_to_date=add_to_date, get_datetime=lambda x: x, now_datetime=datetime.now,
    get_url=lambda: "https://erp.example")
mod("frappe.utils.password", get_decrypted_password=None, set_encrypted_password=None)
mod("frappe.model"); mod("frappe.model.document", Document=Document)
frappe.utils = sys.modules["frappe.utils"]

sys.path.insert(0, "/home/claude/energyx_social")
from energyx_social.services.errors import *
from energyx_social.services.client import SocialClient
from energyx_social.services.providers.meta import MetaProvider
from energyx_social.services.providers.youtube import YouTubeProvider
from energyx_social.services.providers.tiktok import TikTokProvider, plan_chunks, CHUNK, MB
from energyx_social.social_posting.doctype.social_post_metric.social_post_metric import compute_engagement_rate

class Resp:
    def __init__(self, status=200, body=None, headers=None): self.status_code, self._b, self.headers = status, body, headers or {}
    def json(self):
        if self._b is None: raise ValueError
        return self._b

# --- redact
t = redact("GET ?access_token=EAAB1234567890abcdef Authorization: Bearer ya29.A0AfH6SMBxyz12345 x", ["superSecretValue"])
assert "EAAB1234567890abcdef" not in t and "ya29" not in t, t
assert "superSecretValue" not in redact("boom superSecretValue", ["superSecretValue"])

# --- client backoff
class FakeSession:
    def __init__(self, seq): self.seq, self.calls = list(seq), 0
    def request(self, *a, **k):
        self.calls += 1; r = self.seq.pop(0)
        if isinstance(r, Exception): raise r
        return r
sleeps = []
acct = NS(channel="Instagram", api_version="graph.facebook.com/v21.0", access_token="t", account_id="1")
meta = MetaProvider(acct)
c = SocialClient("Instagram", meta.map_error, sleep=sleeps.append, session=FakeSession([
    Resp(400, {"error": {"code": 4, "message": "limit"}}), Resp(500, None), Resp(200, {"id": "9"})]))
assert c.request("GET", "http://x").json()["id"] == "9" and len(sleeps) == 2 and sleeps[1] > sleeps[0] - 1
# permanen tidak diulang
c = SocialClient("Instagram", meta.map_error, sleep=sleeps.append, session=FakeSession([Resp(400, {"error": {"code": 100, "message": "bad"}})]))
try: c.request("GET", "http://x"); raise SystemExit("harus gagal")
except PermanentError: pass
# habis retry -> RateLimitError dengan reschedule_minutes
c = SocialClient("Instagram", meta.map_error, max_retries=2, sleep=lambda s: None,
                 session=FakeSession([Resp(429, None)] * 3))
try: c.request("GET", "http://x"); raise SystemExit("harus gagal")
except RateLimitError as e: assert e.reschedule_minutes == 15 and c.session.calls == 3

# --- error maps
assert isinstance(meta.map_error(Resp(400, {"error": {"code": 190, "message": "tok"}})), AuthError)
yt = YouTubeProvider(NS(channel="YouTube"))
assert isinstance(yt.map_error(Resp(403, {"error": {"message": "q", "errors": [{"reason": "quotaExceeded"}]}})), QuotaExceededError)
assert isinstance(yt.map_error(Resp(400, {"error": "invalid_grant", "error_description": "x"})), AuthError)
tk = TikTokProvider(NS(channel="TikTok"))
assert tk.map_error(Resp(200, {"data": {}, "error": {"code": "ok"}})) is None
assert isinstance(tk.map_error(Resp(200, {"error": {"code": "rate_limit_exceeded", "message": ""}})), RateLimitError)
assert isinstance(tk.map_error(Resp(401, {"error": {"code": "access_token_invalid", "message": ""}})), AuthError)

# --- chunk plan TikTok
assert plan_chunks(3 * MB) == (3 * MB, 1) and plan_chunks(10 * MB) == (10 * MB, 1)
for size in (10 * MB + 1, 25 * MB + 7, 999 * MB + 123):
    cs, n = plan_chunks(size); last = size - (n - 1) * cs
    assert cs >= 5 * MB and 5 * MB <= last <= 128 * MB, (size, cs, n, last)

# --- engagement
assert compute_engagement_rate(10, 5, 5, reach=200) == 10.0 and compute_engagement_rate(1, 0, 0) == 0.0

# --- Social Post: jadwal efektif + proteksi field sistem
from energyx_social.social_posting.doctype.social_post.social_post import SocialPost
class Row(NS):
    def set(self, k, v): setattr(self, k, v)
    def get(self, k, d=None): return getattr(self, k, d)
future = datetime.now() + timedelta(days=1)
p = SocialPost.__new__(SocialPost)
p.status, p.default_scheduled_at = "Approved", future
p.channels = [Row(active=1, status="Queued", scheduled_at_override=None, scheduled_at=None),
              Row(active=1, status="Queued", scheduled_at_override=datetime.now(), scheduled_at=None),
              Row(active=1, status="Published", scheduled_at_override=None, scheduled_at=None)]
p._sync_schedule()
assert [r.status for r in p.channels] == ["Scheduled", "Scheduled", "Published"]
p.default_scheduled_at = None; p.channels[0].scheduled_at_override = None; p.channels[0].status = "Queued"
p._sync_schedule(); assert p.channels[0].status == "Queued"
p.status = "Pending Approval"; p.channels[0].status = "Queued"; p._sync_schedule()
assert p.channels[0].scheduled_at is None  # bukan fase publish: tidak disentuh

class Old(NS):
    def get(self, k, d=None): return getattr(self, k, d)
old = Old(status="Draft", requested_by="a", approved_by=None, approved_on=None,
         channels=[Row(name="r1", status="Published", remote_id="X", permalink="u", error_log="", published_on=1,
                       attempts=2, provider_state="s", scheduled_at=None)])
p = SocialPost.__new__(SocialPost); p.get_doc_before_save = lambda: old
p.requested_by, p.approved_by, p.approved_on = "evil", "evil", "evil"
p.channels = [Row(name="r1", status="Queued", remote_id="HACK", permalink="", error_log="", published_on=None,
                  attempts=0, provider_state=None, scheduled_at=None),
              Row(name="new", status="Published", remote_id="HACK", permalink="", error_log="", published_on=None,
                  attempts=9, provider_state=None, scheduled_at=None)]
p._protect_system_fields()
assert p.channels[0].remote_id == "X" and p.channels[0].status == "Published"
assert p.channels[1].remote_id is None and p.channels[1].status == "Queued" and p.channels[1].attempts == 0
assert p.requested_by == "a" and p.approved_by is None
print("ALL OK")
