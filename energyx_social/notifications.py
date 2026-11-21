"""Notifikasi in-app (Notification Log). Email mengikuti Notification Settings masing-masing user.

Tidak pernah melempar galat: kegagalan notifikasi tidak boleh menggagalkan publikasi atau penyimpanan.
"""
import frappe

POST = "Social Post"
SKIP_USERS = ("Administrator", "Guest")


def users_with_role(role: str) -> list:
    users = frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")
    if not users:
        return []
    return frappe.get_all("User", filters={"name": ["in", users], "enabled": 1}, pluck="name")


def notify(users, subject: str, post: str, body: str = ""):
    """Kirim Notification Log ke tiap user (tanpa duplikat, tanpa diri sendiri)."""
    actor = frappe.session.user
    for user in {u for u in (users or []) if u and u not in SKIP_USERS and u != actor}:
        try:
            frappe.get_doc({
                "doctype": "Notification Log", "for_user": user, "type": "Alert", "subject": subject,
                "email_content": body or subject, "document_type": POST if post else None, "document_name": post,
                "from_user": actor if actor not in SKIP_USERS else None,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(title="SocialX: gagal membuat notifikasi", reference_doctype=POST, reference_name=post)


def on_post_update(doc, method=None):
    """doc_events on_update: perubahan status lewat workflow/form."""
    before = doc.get_doc_before_save()
    if not before or before.status == doc.status:
        return
    old, new = before.status, doc.status
    title = doc.title or doc.name
    requester = [doc.requested_by]
    if new == "Pending Approval":
        notify(users_with_role("Social Manager"), f"Menunggu approval: {title}", doc.name,
               f"Postingan '{title}' diajukan oleh {doc.requested_by} dan menunggu persetujuan.")
    elif old == "Pending Approval" and new == "Pending Final Approval":
        notify(users_with_role("Social Final Approver"), f"Menunggu final approval: {title}", doc.name,
               f"Postingan '{title}' sudah disetujui {doc.approved_by} dan menunggu final approval.")
        notify(requester, f"Lolos approval tingkat 1: {title}", doc.name,
               f"Postingan '{title}' disetujui {doc.approved_by}; menunggu final approval.")
    elif old == "Pending Approval" and new == "Approved":
        notify(requester, f"Disetujui: {title}", doc.name, f"Postingan '{title}' disetujui oleh {doc.approved_by}.")
    elif old == "Pending Final Approval" and new == "Approved":
        notify(requester, f"Disetujui (final): {title}", doc.name,
               f"Postingan '{title}' mendapat final approval dari {doc.final_approved_by}.")
    elif old in ("Pending Approval", "Pending Final Approval") and new == "Draft":
        open_notes = [n for n in (getattr(doc, "revision_notes", None) or []) if n.status != "Resolved"]
        detail = "; ".join(f"[{n.note_type}] {n.note}" for n in open_notes[:5])
        notify(requester, f"Ditolak, perlu revisi: {title}", doc.name,
               f"Postingan '{title}' dikembalikan ke Draft ({len(open_notes)} catatan revisi). {detail}"[:1000])
    elif new == "On Hold":
        notify(requester, f"Ditahan: {title}", doc.name, f"Postingan '{title}' ditahan sementara.")
    elif new == "Cancelled":
        notify(requester, f"Dibatalkan: {title}", doc.name, f"Postingan '{title}' dibatalkan.")


def notify_publish_result(post: str, status: str):
    """Dipanggil publisher saat status induk berubah jadi Published/Partial."""
    data = frappe.db.get_value(POST, post, ["title", "requested_by"], as_dict=True)
    if not data:
        return
    title = data.title or post
    if status == "Published":
        notify([data.requested_by], f"Berhasil terbit: {title}", post, f"Postingan '{title}' sudah terbit di semua kanal.")
    elif status == "Partial":
        notify([data.requested_by], f"Sebagian terbit: {title}", post,
               f"Postingan '{title}' terbit di sebagian kanal. Buka dokumen untuk melihat kanal yang belum berhasil.")


def notify_channel_failed(post: str, channel: str, message: str):
    """Dipanggil publisher saat satu kanal gagal permanen (bukan dijadwalkan ulang)."""
    data = frappe.db.get_value(POST, post, ["title", "requested_by"], as_dict=True)
    if not data:
        return
    title = data.title or post
    recipients = [data.requested_by] + users_with_role("Social Manager")
    notify(recipients, f"Gagal publish ({channel}): {title}", post, f"{channel}: {message[:300]}")
