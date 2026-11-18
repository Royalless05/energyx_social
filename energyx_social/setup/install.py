import frappe

ROLES = ("Social Editor", "Social Manager")

STATES = [  # (state, style, allow_edit)
    ("Draft", "Inverse", "All"),
    ("Pending Approval", "Warning", "Social Manager"),
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
    ("Approved", "Hold", "On Hold", "Social Manager"),
    ("On Hold", "Resume", "Approved", "Social Manager"),
    ("Draft", "Cancel", "Cancelled", "Social Manager"),
    ("Pending Approval", "Cancel", "Cancelled", "Social Manager"),
    ("Approved", "Cancel", "Cancelled", "Social Manager"),
    ("On Hold", "Cancel", "Cancelled", "Social Manager"),
    ("Cancelled", "Reopen", "Draft", "Social Manager"),
]
WORKFLOW = "Social Post Approval"


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
                {"state": s, "action": a, "next_state": n, "allowed": r, "allow_self_approval": 1}
                for s, a, n, r in TRANSITIONS
            ],
        }).insert(ignore_permissions=True)
    frappe.db.commit()
