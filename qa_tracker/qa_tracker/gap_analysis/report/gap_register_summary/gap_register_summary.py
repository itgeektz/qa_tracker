# Copyright (c) 2026, QA Tracker contributors
# License: MIT
"""Fit-gap matrix: how much of each area the system covers, and what is left to deliver."""

import frappe
from frappe import _
from frappe.utils import flt

GROUPS = {
	"Module": "module", "Site": "site", "Assessment": "assessment", "Resolution Approach": "resolution_approach",
	"Priority": "priority", "Gap Type": "gap_type", "Responsible Party": "responsible_party", "Business Owner": "business_owner",
	"Status": "status",
}
OPEN = ("Identified", "Analysed", "Awaiting Approval", "Approved", "In Progress", "Delivered", "Verified")


def execute(filters=None):
	filters = frappe._dict(filters or {})
	label = filters.group_by or "Module"
	field = GROUPS.get(label, "module")
	cond = {k: filters[k] for k in ("site", "module", "assessment", "priority") if filters.get(k)}
	if filters.regulatory_only:
		cond["regulatory"] = 1
	rows = frappe.get_all("Gap Item", filters=cond, fields=[f"{field} as grp", "fit_status", "status", "priority",
		"effort_days", "estimated_cost", "decision"])
	data = {}
	for r in rows:
		key = r.grp or _("(not set)")
		d = data.setdefault(key, frappe._dict(group=key, total=0, fit=0, partial=0, gap=0, na=0, open=0, must_open=0,
			approved=0, awaiting=0, delivered=0, closed=0, rejected=0, effort=0.0, cost=0.0))
		d.total += 1
		d[{"Fit": "fit", "Partial Fit": "partial", "Gap": "gap"}.get(r.fit_status, "na")] += 1
		is_gap = r.fit_status in ("Gap", "Partial Fit")
		if is_gap and r.status in OPEN:
			d.open += 1
			if r.priority == "Must Have":
				d.must_open += 1
		if r.status == "Awaiting Approval":
			d.awaiting += 1
		if r.decision == "Approved":
			d.approved += 1
		if r.status in ("Delivered", "Verified"):
			d.delivered += 1
		if r.status == "Closed":
			d.closed += 1
		if r.status in ("Rejected", "Deferred"):
			d.rejected += 1
		if is_gap and r.status not in ("Rejected", "Deferred"):
			d.effort += flt(r.effort_days)
			d.cost += flt(r.estimated_cost)
	out = sorted(data.values(), key=lambda x: -x.total)
	for d in out:
		counted = d.fit + d.partial + d.gap
		d.fit_pct = round(100.0 * (d.fit + 0.5 * d.partial) / counted, 1) if counted else 0

	opt = {"module": "QA Module", "site": "QA Site", "assessment": "Gap Assessment", "business_owner": "User"}.get(field)
	columns = [
		{"fieldname": "group", "label": _(label), "fieldtype": "Link" if opt else "Data", "options": opt, "width": 200},
		{"fieldname": "total", "label": _("Items"), "fieldtype": "Int", "width": 70},
		{"fieldname": "fit", "label": _("Fit"), "fieldtype": "Int", "width": 60},
		{"fieldname": "partial", "label": _("Partial"), "fieldtype": "Int", "width": 70},
		{"fieldname": "gap", "label": _("Gap"), "fieldtype": "Int", "width": 60},
		{"fieldname": "na", "label": _("N/A"), "fieldtype": "Int", "width": 55},
		{"fieldname": "fit_pct", "label": _("Fit %"), "fieldtype": "Percent", "width": 80},
		{"fieldname": "open", "label": _("Open Gaps"), "fieldtype": "Int", "width": 90},
		{"fieldname": "must_open", "label": _("Open Must-Haves"), "fieldtype": "Int", "width": 120},
		{"fieldname": "awaiting", "label": _("Awaiting Approval"), "fieldtype": "Int", "width": 120},
		{"fieldname": "approved", "label": _("Approved"), "fieldtype": "Int", "width": 85},
		{"fieldname": "delivered", "label": _("Delivered / Verifying"), "fieldtype": "Int", "width": 130},
		{"fieldname": "closed", "label": _("Closed"), "fieldtype": "Int", "width": 70},
		{"fieldname": "rejected", "label": _("Rejected / Deferred"), "fieldtype": "Int", "width": 130},
		{"fieldname": "effort", "label": _("Effort (days)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "cost", "label": _("Est. Cost"), "fieldtype": "Currency", "width": 110},
	]
	chart = {
		"data": {
			"labels": [str(d.group) for d in out[:15]],
			"datasets": [{"name": _("Fit"), "values": [d.fit for d in out[:15]]},
				{"name": _("Partial Fit"), "values": [d.partial for d in out[:15]]},
				{"name": _("Gap"), "values": [d.gap for d in out[:15]]}],
		},
		"type": "bar", "barOptions": {"stacked": 1}, "colors": ["#29CD42", "#ECAD4B", "#E24C4C"],
	}
	total_counted = sum(d.fit + d.partial + d.gap for d in out)
	overall = round(100.0 * sum(d.fit + 0.5 * d.partial for d in out) / total_counted, 1) if total_counted else 0
	summary = [
		{"value": overall, "label": _("Overall fit"), "datatype": "Percent", "indicator": "Green" if overall >= 80 else "Orange"},
		{"value": sum(d.open for d in out), "label": _("Open gaps"), "datatype": "Int", "indicator": "Blue"},
		{"value": sum(d.must_open for d in out), "label": _("Open must-haves"), "datatype": "Int", "indicator": "Red"},
		{"value": sum(d.effort for d in out), "label": _("Effort (days)"), "datatype": "Float", "indicator": "Grey"},
	]
	return columns, out, None, chart, summary
