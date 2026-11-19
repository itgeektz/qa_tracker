# Copyright (c) 2026, QA Tracker contributors
# License: MIT

import frappe
from frappe import _

BUCKETS = [
	("logged", _("Logged"), ["New", "Triaged"]),
	("with_dev", _("With Developer"), ["Assigned", "In Progress", "Reopened"]),
	("retest", _("Awaiting Retest"), ["Ready for Retest", "Answered"]),
	("confirmed", _("Retested / Confirmed"), ["Retest Passed", "Confirmed"]),
	("uat", _("In UAT"), ["In UAT"]),
	("done", _("Done"), ["UAT Accepted", "Closed"]),
	("parked", _("Deferred / Rejected / Merged"), ["Deferred", "Rejected", "Merged"]),
]
GROUPS = {
	"Reporter (Tester)": "reported_by",
	"Assigned Developer": "assigned_to",
	"Module": "module",
	"Site": "site",
	"Test Cycle": "test_cycle",
	"Severity": "severity",
	"Source Channel": "source_channel",
}


def execute(filters=None):
	filters = frappe._dict(filters or {})
	field = GROUPS.get(filters.group_by or "Reporter (Tester)", "reported_by")
	conditions = {}
	for f in ("site", "module", "test_cycle", "severity"):
		if filters.get(f):
			conditions[f] = filters.get(f)
	if filters.from_date:
		conditions["reported_on"] = [">=", filters.from_date]

	rows = frappe.get_all("QA Issue", filters=conditions, fields=[f"{field} as grp", "status", "severity", "reopen_count"])
	data = {}
	for r in rows:
		key = r.grp or _("(not set)")
		d = data.setdefault(key, frappe._dict(group=key, total=0, blockers_open=0, reopened=0, **{b[0]: 0 for b in BUCKETS}))
		d.total += 1
		for bkey, _label, states in BUCKETS:
			if r.status in states:
				d[bkey] += 1
		if r.severity == "Blocker" and r.status not in ("UAT Accepted", "Closed", "Rejected", "Deferred"):
			d.blockers_open += 1
		if r.reopen_count:
			d.reopened += 1
	out = sorted(data.values(), key=lambda x: -x.total)
	for d in out:
		d.done_pct = round(100.0 * d.done / d.total, 1) if d.total else 0

	label = filters.group_by or "Reporter (Tester)"
	opt = "User" if field in ("reported_by", "assigned_to") else {"module": "QA Module", "site": "QA Site", "test_cycle": "QA Test Cycle"}.get(field)
	columns = [
		{"fieldname": "group", "label": _(label), "fieldtype": "Link" if opt else "Data", "options": opt, "width": 220},
		{"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 80},
	]
	columns += [{"fieldname": b[0], "label": b[1], "fieldtype": "Int", "width": 120} for b in BUCKETS]
	columns += [
		{"fieldname": "blockers_open", "label": _("Open Blockers"), "fieldtype": "Int", "width": 110},
		{"fieldname": "reopened", "label": _("Ever Reopened"), "fieldtype": "Int", "width": 110},
		{"fieldname": "done_pct", "label": _("% Done"), "fieldtype": "Percent", "width": 90},
	]
	chart = {
		"data": {
			"labels": [str(d.group) for d in out[:15]],
			"datasets": [{"name": b[1], "values": [d[b[0]] for d in out[:15]]} for b in BUCKETS[:6]],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
	return columns, out, None, chart
