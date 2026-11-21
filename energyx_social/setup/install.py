import frappe

ROLES = ("Social Editor", "Social Manager", "Social Final Approver")

STATES = [  # (state, style, allow_edit)
    ("Draft", "Inverse", "All"),
    ("Pending Approval", "Warning", "Social Manager"),
    ("Pending Final Approval", "Warning", "Social Manager"),
    ("Approved", "Info", "Social Manager"),
    ("Publishing", "Primary", "System Manager"),
    ("Published", "Success", "System Manager"),
    ("Partial", "Warning", "System Manager"),
    ("On Hold", "Danger", "Social Manager"),
    ("Cancelled", "Danger", "Social Manager"),
]
TRANSITIONS = [  # (state, action, next_state, allowed)
    ("Draft", "Submit for Approval", "Pending Approval", "All"),
    ("Pending Approval", "Approve", "Approved", "Social Manager"),
    ("Pending Approval", "Reject", "Draft", "Social Manager"),
    ("Pending Approval", "Approve", "Pending Final Approval", "Social Manager"),
    ("Pending Final Approval", "Final Approve", "Approved", "Social Final Approver"),
    ("Pending Final Approval", "Request Revision", "Draft", "Social Final Approver"),
    ("Pending Final Approval", "Cancel", "Cancelled", "Social Manager"),
    ("Approved", "Hold", "On Hold", "Social Manager"),
    ("On Hold", "Resume", "Approved", "Social Manager"),
    ("Draft", "Cancel", "Cancelled", "Social Manager"),
    ("Pending Approval", "Cancel", "Cancelled", "Social Manager"),
    ("Approved", "Cancel", "Cancelled", "Social Manager"),
    ("On Hold", "Cancel", "Cancelled", "Social Manager"),
    ("Cancelled", "Reopen", "Draft", "Social Manager"),
]
WORKFLOW = "Social Post Approval"
# Approval bertingkat dikendalikan flag doc.needs_final_approval (diisi dari Social Posting Settings).
CONDITIONS = {
    ("Pending Approval", "Approve", "Approved"): "not doc.needs_final_approval",
    ("Pending Approval", "Approve", "Pending Final Approval"): "doc.needs_final_approval",
}


def after_install():
    ensure_setup()


def after_migrate():
    ensure_setup()


def ensure_setup():
    """Idempoten: hanya membuat yang belum ada (tidak menimpa kustomisasi)."""
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)

    for state, style, _ in STATES:
        if not frappe.db.exists("Workflow State", state):
            frappe.get_doc({"doctype": "Workflow State", "workflow_state_name": state, "style": style}) \
                .insert(ignore_permissions=True)
    for action in {t[1] for t in TRANSITIONS}:
        if not frappe.db.exists("Workflow Action Master", action):
            frappe.get_doc({"doctype": "Workflow Action Master", "workflow_action_name": action}) \
                .insert(ignore_permissions=True)

    if not frappe.db.exists("Workflow", WORKFLOW):
        frappe.get_doc({
            "doctype": "Workflow",
            "workflow_name": WORKFLOW,
            "document_type": "Social Post",
            "is_active": 1,
            "workflow_state_field": "status",
            "send_email_alert": 0,
            "states": [{"state": s, "doc_status": "0", "allow_edit": role} for s, _, role in STATES],
            "transitions": [
                {"state": s, "action": a, "next_state": n, "allowed": r, "allow_self_approval": 1,
                 "condition": CONDITIONS.get((s, a, n))}
                for s, a, n, r in TRANSITIONS
            ],
        }).insert(ignore_permissions=True)
    else:
        _extend_workflow()
    frappe.db.commit()


def _extend_workflow():
    """Workflow lama (Gelombang 1) diperluas di tempat: hanya MENAMBAH state/transisi yang belum ada dan
    mengisi kondisi yang masih kosong. Kustomisasi yang sudah dibuat tidak ditimpa."""
    wf = frappe.get_doc("Workflow", WORKFLOW)
    changed = False
    have_states = {row.state for row in wf.states}
    for state, _style, role in STATES:
        if state not in have_states:
            wf.append("states", {"state": state, "doc_status": "0", "allow_edit": role})
            changed = True
    have = {(t.state, t.action, t.next_state): t for t in wf.transitions}
    for s, a, n, r in TRANSITIONS:
        t = have.get((s, a, n))
        if t is None:
            wf.append("transitions", {"state": s, "action": a, "next_state": n, "allowed": r,
                                      "allow_self_approval": 1, "condition": CONDITIONS.get((s, a, n))})
            changed = True
        elif CONDITIONS.get((s, a, n)) and not t.condition:
            t.condition = CONDITIONS[(s, a, n)]
            changed = True
    if changed:
        wf.save(ignore_permissions=True)
