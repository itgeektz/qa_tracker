# Copyright (c) 2026, QA Tracker contributors
# License: MIT
"""Merge duplicate tickets (QA Issue) and gaps (Gap Item) into one, and suggest similar ones.

Merging keeps one record (the *target*). From each duplicate (*source*) it copies screenshots,
recordings, files and the whole timeline, moves links (test runs, gap links, chat threads),
raises the target's severity / priority to the highest, and marks the source **Merged** with a
pointer to the target. Chat replies to the source then land on the target.
"""

import re

import frappe
from frappe import _
from frappe.utils import cstr, now_datetime, strip_html

from qa_tracker import access

STOP = set(
	"the a an and or of to in on for with is are was were be been not no this that from at by it as "
	"when after before into while also only can cannot can't dont don't does doesnt doesn't did "
	"issue problem error showing shows show screen page please kindly getting get".split()
)
SEV_RANK = {"Blocker": 0, "High": 1, "Medium": 2, "Low": 3}
MOSCOW_RANK = {"Must Have": 0, "Should Have": 1, "Could Have": 2, "Won't Have": 3}

KINDS = {
	"QA Issue": dict(
		tables=("screenshots", "retest_screenshots", "uat_screenshots", "media_files"),
		closed=("UAT Accepted", "Closed", "Rejected", "Merged"),
		update_doctype="QA Issue Update",
	),
	"Gap Item": dict(
		tables=("evidence", "verification_evidence"),
		closed=("Closed", "Rejected", "Merged"),
		update_doctype="Gap Update",
	),
}


# ---------------------------------------------------------------- similarity
def _tokens(text):
	words = re.findall(r"[a-z0-9]+", cstr(text).lower())
	return {w for w in words if len(w) >= 3 and w not in STOP and not w.isdigit()}


def _project_root(project):
	chain = access.ancestors("QA Project", project) if project else []
	return chain[-1] if chain else None


def similar(doctype, name, limit=8, min_score=0.2):
	"""Open records in the same project tree whose titles look alike."""
	if doctype not in KINDS:
		frappe.throw(_("Unsupported"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	extra = strip_html(cstr(doc.get("description") or doc.get("requirement") or ""))[:300]
	toks = _tokens(doc.title)
	if len(toks) < 2:
		toks |= _tokens(extra)
	if not toks:
		return []
	filters = {"name": ["!=", name], "status": ["not in", list(KINDS[doctype]["closed"])]}
	root = _project_root(doc.get("project"))
	if root:
		filters["project"] = ["in", sorted(access.descendants("QA Project", root))]
	words = sorted(toks, key=len, reverse=True)[:6]
	fields = ["name", "title", "status", "module", "site", "modified", "project"]
	fields.append("severity" if doctype == "QA Issue" else "priority")
	rows = frappe.get_list(doctype, filters=filters, or_filters=[["title", "like", f"%{w}%"] for w in words],
		fields=fields, limit=80, order_by="modified desc")
	out = []
	for r in rows:
		t = _tokens(r.title)
		if not t:
			continue
		score = len(toks & t) / len(toks | t)
		if r.module and r.module == doc.get("module"):
			score += 0.15
		if r.site and r.site == doc.get("site"):
			score += 0.05
		if score >= min_score:
			r.score = round(min(score, 1), 2)
			out.append(r)
	out.sort(key=lambda r: -r.score)
	return out[:limit]


@frappe.whitelist()
def similar_issues(name, limit=8):
	return similar("QA Issue", name, int(limit))


@frappe.whitelist()
def similar_gaps(name, limit=8):
	return similar("Gap Item", name, int(limit))


@frappe.whitelist()
def search(doctype, txt, exclude=None):
	"""Find records to merge with: by number or title words."""
	if doctype not in KINDS:
		frappe.throw(_("Unsupported"))
	txt = (txt or "").strip()
	if not txt:
		return []
	prefix = "ISS" if doctype == "QA Issue" else "GAP"
	filters = {"status": ["!=", "Merged"]}
	if exclude:
		filters["name"] = ["!=", exclude]
	m = re.match(rf"^({prefix}-)?(\d+)$", txt, re.I)
	or_filters = None
	if m:
		filters["name"] = f"{prefix}-{int(m.group(2)):05d}"
	else:
		or_filters = [["title", "like", f"%{txt}%"]]
		if doctype == "QA Issue":
			or_filters.append(["issue_code", "like", f"%{txt}%"])
	return frappe.get_list(doctype, filters=filters, or_filters=or_filters,
		fields=["name", "title", "status", "module", "site", "project"], limit=15, order_by="modified desc")


# ---------------------------------------------------------------- permission
def can_merge(doctype, doc, user=None):
	user = user or frappe.session.user
	if access.is_admin(user):
		return True
	roles = set(frappe.get_roles(user))
	if not access.can_access(doctype, doc, user):
		return False
	if doctype == "QA Issue":
		return "QA Lead" in roles and (not doc.get("project") or access.is_project_lead(user, doc.project))
	return bool(roles & {"GA Analyst", "QA Lead"}) and (
		not doc.get("project") or access.vendor_of(user, doc.project) is None)


# ---------------------------------------------------------------- merge
def _next_idx(child_doctype, parent, field):
	return frappe.db.sql(
		f"select ifnull(max(idx), 0) from `tab{child_doctype}` where parent=%s and parentfield=%s", (parent, field)
	)[0][0]


def _copy_rows(src, target, parenttype, field):
	meta = frappe.get_meta(parenttype)
	child = meta.get_field(field).options
	idx = _next_idx(child, target, field)
	n = 0
	for row in src.get(field) or []:
		idx += 1
		vals = row.as_dict(no_default_fields=True)
		for k in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
			vals.pop(k, None)
		frappe.get_doc(dict(doctype=child, parent=target, parenttype=parenttype, parentfield=field, idx=idx, **vals)).db_insert()
		n += 1
	return n


def _add_update(doctype, target, message, update_type="Comment"):
	child = KINDS[doctype]["update_doctype"]
	idx = _next_idx(child, target, "updates")
	vals = dict(doctype=child, parent=target, parenttype=doctype, parentfield="updates", idx=idx + 1,
		posted_on=now_datetime(), posted_by=frappe.session.user, message=message)
	if doctype == "QA Issue":
		from qa_tracker.utils import party_for_user

		vals.update(party=party_for_user(frappe.session.user), channel="Portal", update_type="Status Change" if update_type != "Comment" else "Comment",
			sender_name=frappe.utils.get_fullname(frappe.session.user))
	else:
		vals.update(update_type="Decision" if update_type != "Comment" else "Comment")
	frappe.get_doc(vals).db_insert()


def _copy_timeline(doctype, src, target):
	child = KINDS[doctype]["update_doctype"]
	idx = _next_idx(child, target, "updates")
	for row in src.get("updates") or []:
		idx += 1
		vals = row.as_dict(no_default_fields=True)
		for k in ("name", "parent", "parenttype", "parentfield", "idx", "doctype"):
			vals.pop(k, None)
		vals["message"] = f"[{src.name}] {vals.get('message') or ''}".strip()
		frappe.get_doc(dict(doctype=child, parent=target, parenttype=doctype, parentfield="updates", idx=idx, **vals)).db_insert()


def _move_files(doctype, src, target):
	"""Private files belong to the record they are attached to; re-attach so target readers can open them."""
	frappe.db.sql(
		"""update `tabFile` set attached_to_name=%s where attached_to_doctype=%s and attached_to_name=%s""",
		(target, doctype, src),
	)


def merge(doctype, target, sources):
	if doctype not in KINDS:
		frappe.throw(_("Unsupported"))
	if isinstance(sources, str):
		sources = frappe.parse_json(sources) if sources.strip().startswith("[") else sources.split(",")
	sources = [cstr(x).strip() for x in dict.fromkeys(sources or [])]
	sources = [x for x in sources if x and x != target]
	if not sources:
		frappe.throw(_("Pick at least one other record to merge"))
	tgt = frappe.get_doc(doctype, target)
	if tgt.status == "Merged":
		frappe.throw(_("{0} was itself merged into {1}. Merge into that one instead.").format(tgt.name, tgt.merged_into))
	if not can_merge(doctype, tgt):
		frappe.throw(_("You can't merge into {0}").format(tgt.name), frappe.PermissionError)
	label = "ticket" if doctype == "QA Issue" else "gap"
	merged = []
	for name in sources:
		src = frappe.get_doc(doctype, name)
		if src.status == "Merged":
			frappe.throw(_("{0} is already merged into {1}").format(src.name, src.merged_into))
		if not can_merge(doctype, src):
			frappe.throw(_("You can't merge {0}").format(src.name), frappe.PermissionError)
		root_t, root_s = _project_root(tgt.get("project")), _project_root(src.get("project"))
		if root_t and root_s and root_t != root_s:
			frappe.throw(_("{0} belongs to another project ({1}). Only records of the same project can be merged.").format(src.name, src.project))
		counts = {f: _copy_rows(src, tgt.name, doctype, f) for f in KINDS[doctype]["tables"]}
		_copy_timeline(doctype, src, tgt.name)
		_move_files(doctype, src.name, tgt.name)
		desc = strip_html(cstr(src.get("description") or src.get("requirement") or "")).strip()
		who = src.get("reporter_name") or (frappe.utils.get_fullname(src.reported_by) if src.get("reported_by") else "") or (
			frappe.utils.get_fullname(src.get("raised_by")) if src.get("raised_by") else "")
		files = sum(counts.values())
		_add_update(doctype, tgt.name, _("Merged {0} into this {1}: {2}{3}{4}{5}").format(
			src.name, label, src.title, f" (reported by {who})" if who else "", f" · {files} file(s) moved" if files else "",
			f"\n{desc[:1500]}" if desc and desc != src.title else ""), "Merge")
		_add_update(doctype, src.name, _("Merged into {0} ({1}). Follow that {2} from now on.").format(tgt.name, tgt.title, label), "Merge")
		if doctype == "QA Issue":
			_relink_issue(src, tgt)
		else:
			_relink_gap(src, tgt)
		# re-point anything already merged into the source
		frappe.db.sql(f"update `tab{doctype}` set merged_into=%s where merged_into=%s", (tgt.name, src.name))
		frappe.db.set_value(doctype, src.name, {"status": "Merged", "merged_into": tgt.name})
		for todo in frappe.get_all("ToDo", filters={"reference_type": doctype, "reference_name": src.name, "status": "Open"}, pluck="name"):
			frappe.db.set_value("ToDo", todo, "status", "Cancelled")
		merged.append(src)
	_raise_rank(doctype, tgt, merged)
	frappe.db.set_value(doctype, tgt.name, "modified", now_datetime())
	from qa_tracker.compat import after_commit

	names = [s.name for s in merged]
	after_commit(lambda: _notify(doctype, tgt.name, names))
	try:
		frappe.publish_realtime("doc_update", {"doctype": doctype, "name": tgt.name}, doctype=doctype, docname=tgt.name)
	except Exception:
		pass
	return {"target": tgt.name, "merged": names}


def _relink_issue(src, tgt):
	frappe.db.sql("update `tabQA Test Execution` set issue=%s where issue=%s", (tgt.name, src.name))
	frappe.db.sql("update `tabQA Issue` set possible_duplicate_of=%s where possible_duplicate_of=%s and name!=%s", (tgt.name, src.name, tgt.name))
	frappe.db.sql("update `tabQA Channel Message` set issue=%s where issue=%s", (tgt.name, src.name))
	frappe.db.set_value("QA Issue", tgt.name, {
		"retest_count": max(tgt.retest_count or 0, src.retest_count or 0),
		"reopen_count": max(tgt.reopen_count or 0, src.reopen_count or 0),
	}, update_modified=False)
	if frappe.db.exists("DocType", "Gap Issue Link"):
		for gap in frappe.get_all("Gap Issue Link", filters={"issue": src.name}, fields=["name", "parent"]):
			if frappe.db.exists("Gap Issue Link", {"parent": gap.parent, "issue": tgt.name}):
				frappe.db.delete("Gap Issue Link", {"name": gap.name})
			else:
				frappe.db.set_value("Gap Issue Link", gap.name, "issue", tgt.name, update_modified=False)


def _relink_gap(src, tgt):
	for table, key in (("linked_issues", "issue"), ("linked_test_cases", "test_case")):
		have = {r.get(key) for r in tgt.get(table) or []}
		child = frappe.get_meta("Gap Item").get_field(table).options
		idx = _next_idx(child, tgt.name, table)
		for row in src.get(table) or []:
			if row.get(key) and row.get(key) not in have:
				idx += 1
				have.add(row.get(key))
				frappe.get_doc({"doctype": child, "parent": tgt.name, "parenttype": "Gap Item", "parentfield": table, "idx": idx, key: row.get(key)}).db_insert()


def _raise_rank(doctype, tgt, merged):
	if doctype == "QA Issue":
		best = min([tgt.severity] + [s.severity for s in merged], key=lambda v: SEV_RANK.get(v, 9))
		if best != tgt.severity:
			frappe.db.set_value("QA Issue", tgt.name, "severity", best, update_modified=False)
			_add_update(doctype, tgt.name, _("Severity raised to {0} (highest of the merged tickets)").format(best))
	else:
		best = min([tgt.priority] + [s.priority for s in merged], key=lambda v: MOSCOW_RANK.get(v, 9))
		if best != tgt.priority:
			frappe.db.set_value("Gap Item", tgt.name, "priority", best, update_modified=False)
			_add_update(doctype, tgt.name, _("Priority raised to {0} (highest of the merged gaps)").format(best))


def _notify(doctype, target, sources):
	if doctype != "QA Issue":
		return
	from qa_tracker import notify

	tgt = frappe.get_doc("QA Issue", target)
	for name in sources:
		src = frappe.get_doc("QA Issue", name)
		text = _("{0} was a duplicate and has been merged into {1}: {2}\nAll updates now happen on {1}. Reply '{1} your update' to add details.").format(
			src.name, tgt.name, tgt.title)
		seen = set()
		for person in (notify._reporter(src), notify._developer(src) if src.assigned_to else None):
			if not person or (person.user and person.user in seen):
				continue
			seen.add(person.user)
			notify.send_to(person, src, _("{0} merged into {1}").format(src.name, tgt.name), text)
	notify.post_teams(tgt, _("{0} merged into {1}").format(", ".join(sources), tgt.name), tgt.title)


def resolve(doctype, name, depth=0):
	"""Follow merged_into to the record that is still alive."""
	nxt = frappe.db.get_value(doctype, name, "merged_into") if name else None
	if nxt and depth < 10:
		return resolve(doctype, nxt, depth + 1)
	return name


@frappe.whitelist()
def merge_issues(target, sources):
	return merge("QA Issue", target, sources)


@frappe.whitelist()
def merge_gaps(target, sources):
	return merge("Gap Item", target, sources)
