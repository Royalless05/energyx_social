"""Social Analytics: engagement per post / akun / kanal / minggu / jam / hari terbit.

Sumber: snapshot terbaru Social Post Metric tiap kanal (nilai platform bersifat kumulatif), difilter menurut
tanggal terbit kanal. Engagement rate gabungan = (likes + comments + shares) / reach (fallback impressions).
"""
import datetime

import frappe
from frappe import _

from energyx_social.social_posting.doctype.social_post_metric.social_post_metric import compute_engagement_rate

VIEWS = ("Post", "Account", "Channel", "Week", "Hour of Day", "Weekday")
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SUMS = ("impressions", "reach", "likes", "comments", "shares")


def execute(filters=None):
    filters = frappe._dict(filters or {})
    view = filters.get("group_by") or "Post"
    if view not in VIEWS:
        frappe.throw(_("View tidak valid."))
    rows = fetch(filters)
    data = aggregate(rows, view)
    return columns(view), data, None, chart(view, data), summary(rows, data, view)


def fetch(f):
    cond, params = ["c.status = 'Published'", "c.published_on between %(frm)s and %(to)s"], {
        "frm": f"{f.from_date} 00:00:00", "to": f"{f.to_date} 23:59:59"}
    if f.get("channel"):
        cond.append("c.channel = %(channel)s")
        params["channel"] = f.channel
    if f.get("account"):
        cond.append("c.account = %(account)s")
        params["account"] = f.account
    return frappe.db.sql(f"""
        select c.name as row_name, c.parent as post, p.title, c.channel, c.account, c.account_label, c.post_format,
               c.published_on, c.permalink,
               ifnull(m.impressions,0) impressions, ifnull(m.reach,0) reach, ifnull(m.likes,0) likes,
               ifnull(m.comments,0) comments, ifnull(m.shares,0) shares
        from `tabSocial Post Channel` c
        join `tabSocial Post` p on p.name = c.parent
        left join (
            select x.* from `tabSocial Post Metric` x
            join (select post_channel, max(`date`) d from `tabSocial Post Metric` group by post_channel) l
              on l.post_channel = x.post_channel and l.d = x.`date`
        ) m on m.post_channel = c.name
        where c.parenttype = 'Social Post' and {' and '.join(cond)}
        order by c.published_on
    """, params, as_dict=True)


def group_key(row, view):
    pub = row["published_on"]
    if view == "Post":
        return row["row_name"]
    if view == "Account":
        return f"{row['channel']} - {row['account_label'] or row['account']}"
    if view == "Channel":
        return row["channel"]
    if view == "Week":
        monday = pub.date() - datetime.timedelta(days=pub.weekday())
        return monday.isoformat()
    if view == "Hour of Day":
        return f"{pub.hour:02d}:00"
    return WEEKDAYS[pub.weekday()]


def aggregate(rows, view):
    groups = {}
    for row in rows:
        key = group_key(row, view)
        g = groups.setdefault(key, {"label": key, "posts": 0, **{k: 0 for k in SUMS}})
        g["posts"] += 1
        for k in SUMS:
            g[k] += int(row[k] or 0)
        if view == "Post":
            g.update(title=row["title"], channel=row["channel"], account=row["account_label"], post=row["post"],
                     published_on=row["published_on"], link=row["permalink"], post_format=row["post_format"])
    out = list(groups.values())
    for g in out:
        g["engagement_rate"] = compute_engagement_rate(g["likes"], g["comments"], g["shares"], g["reach"], g["impressions"])
    if view == "Weekday":
        out.sort(key=lambda g: WEEKDAYS.index(g["label"]))
    elif view in ("Week", "Hour of Day"):
        out.sort(key=lambda g: g["label"])
    else:
        out.sort(key=lambda g: g["engagement_rate"], reverse=True)
    return out


def columns(view):
    label = {"Post": "Post", "Account": "Account", "Channel": "Channel", "Week": "Week Starting",
             "Hour of Day": "Hour", "Weekday": "Weekday"}[view]
    cols = []
    if view == "Post":
        cols += [{"label": _("Post"), "fieldname": "post", "fieldtype": "Link", "options": "Social Post", "width": 140},
                 {"label": _("Title"), "fieldname": "title", "fieldtype": "Data", "width": 220},
                 {"label": _("Channel"), "fieldname": "channel", "fieldtype": "Data", "width": 110},
                 {"label": _("Account"), "fieldname": "account", "fieldtype": "Data", "width": 130},
                 {"label": _("Format"), "fieldname": "post_format", "fieldtype": "Data", "width": 80},
                 {"label": _("Published"), "fieldname": "published_on", "fieldtype": "Datetime", "width": 150}]
    else:
        cols += [{"label": _(label), "fieldname": "label", "fieldtype": "Data", "width": 200},
                 {"label": _("Posts"), "fieldname": "posts", "fieldtype": "Int", "width": 70}]
    cols += [{"label": _(k.title()), "fieldname": k, "fieldtype": "Int", "width": 100} for k in SUMS]
    cols.append({"label": _("Engagement %"), "fieldname": "engagement_rate", "fieldtype": "Percent", "width": 110})
    if view == "Post":
        cols.append({"label": _("Link"), "fieldname": "link", "fieldtype": "Data", "options": "URL", "width": 160})
    return cols


def chart(view, data):
    if not data:
        return None
    top = data[:15] if view in ("Post", "Account", "Channel") else data
    names = [(g.get("title") or g["label"])[:28] if view == "Post" else g["label"] for g in top]
    return {
        "data": {"labels": names, "datasets": [{"name": _("Engagement %"), "values": [g["engagement_rate"] for g in top]}]},
        "type": "line" if view == "Week" else "bar",
    }


def summary(rows, data, view):
    posts = len({r["row_name"] for r in rows})
    totals = {k: sum(int(r[k] or 0) for r in rows) for k in SUMS}
    rate = compute_engagement_rate(totals["likes"], totals["comments"], totals["shares"], totals["reach"], totals["impressions"])
    out = [{"label": _("Published Posts"), "value": posts, "datatype": "Int"},
           {"label": _("Impressions"), "value": totals["impressions"], "datatype": "Int"},
           {"label": _("Engagement %"), "value": rate, "datatype": "Percent"}]
    if view in ("Hour of Day", "Weekday") and data:
        best = max(data, key=lambda g: g["engagement_rate"])
        out.append({"label": _("Best slot (by engagement)"), "value": f"{best['label']} ({best['engagement_rate']}%, {best['posts']} posts)",
                    "datatype": "Data"})
    return out
