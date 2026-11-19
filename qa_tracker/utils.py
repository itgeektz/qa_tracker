"""Shared helpers."""

import re

import frappe
from frappe.utils import get_url, now_datetime

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
ISSUE_REF_RE = re.compile(r"\b(ISS-\d{3,7})\b", re.I)


def settings():
	return frappe.get_cached_doc("QA Settings")


def site_base_url():
	return (settings().public_base_url or "").rstrip("/") or get_url()


def issue_url(name, portal=False):
	if portal:
		return f"{site_base_url()}/qa#/t/{name}"
	return f"{site_base_url()}/app/qa-issue/{name}"


def portal_url(name):
	return issue_url(name, portal=True)


def party_for_user(user):
	if not user or user in ("Guest",):
		return "Tester"
	roles = set(frappe.get_roles(user))
	if "Vendor Developer" in roles and "QA Lead" not in roles:
		return "Developer"
	if "QA Lead" in roles or user == "Administrator":
		return "QA Lead"
	if "UAT User" in roles and "QA Tester" not in roles:
		return "UAT"
	return "Tester"


def is_image(filename):
	return bool(filename) and filename.lower().split("?")[0].endswith(IMAGE_EXT)


def digits(phone):
	return re.sub(r"\D", "", phone or "")


def find_user(email=None, phone=None, full_name=None, channel=None, external_id=None):
	"""Map a channel sender to an enabled system user."""
	if channel and external_id:
		linked = frappe.db.get_value("QA Channel Link", {"channel": channel, "external_id": str(external_id)}, "user")
		if linked and frappe.db.get_value("User", linked, "enabled"):
			return linked
	if email:
		user = frappe.db.get_value("User", {"name": email.strip().lower(), "enabled": 1}) or frappe.db.get_value(
			"User", {"email": email.strip(), "enabled": 1}
		)
		if user:
			return user
	d = digits(phone)
	if len(d) >= 9:
		tail = d[-9:]
		for r in frappe.get_all(
			"User",
			filters={"enabled": 1},
			or_filters={"mobile_no": ["is", "set"], "phone": ["is", "set"]},
			fields=["name", "mobile_no", "phone"],
		):
			if digits(r.mobile_no).endswith(tail) or digits(r.phone).endswith(tail):
				return r.name
	if full_name:
		users = frappe.get_all("User", filters={"full_name": full_name, "enabled": 1}, pluck="name", limit=2)
		if len(users) == 1:
			return users[0]
	return None


def user_contact(user):
	if not user:
		return {}
	return frappe.db.get_value("User", user, ["email", "mobile_no", "full_name"], as_dict=True) or {}


def append_child(parent, parentfield, values, child_doctype=None):
	"""Insert a child row directly (bypasses workflow edit locks and avoids
	'document modified' clashes when messages arrive while someone has the form open)."""
	meta = frappe.get_meta("QA Issue")
	child_doctype = child_doctype or meta.get_field(parentfield).options
	idx = frappe.db.sql(
		f"select ifnull(max(idx), 0) from `tab{child_doctype}` where parent=%s and parentfield=%s",
		(parent, parentfield),
	)[0][0]
	row = frappe.get_doc(
		dict(doctype=child_doctype, parent=parent, parenttype="QA Issue", parentfield=parentfield, idx=idx + 1, **values)
	)
	row.db_insert()
	frappe.db.set_value("QA Issue", parent, "modified_by", frappe.session.user)  # bumps modified
	return row


def append_update(
	issue,
	message,
	party=None,
	channel="Web",
	update_type="Comment",
	screenshot=None,
	user=None,
	sender_name=None,
	notify=True,
	attachment=None,
	attachment_name=None,
):
	user = user or frappe.session.user
	row = append_child(
		issue,
		"updates",
		{
			"posted_on": now_datetime(),
			"posted_by": user if user and user != "Guest" else None,
			"party": party or party_for_user(user),
			"channel": channel,
			"update_type": update_type,
			"message": message,
			"screenshot": screenshot,
			"attachment": attachment,
			"attachment_name": attachment_name,
			"sender_name": sender_name or (frappe.utils.get_fullname(user) if user and user != "Guest" else None),
			"source_message": frappe.flags.qa_source_message,
		},
	)
	if notify:
		from qa_tracker import notify as _notify

		_notify.on_update_posted(issue, row)
	frappe.publish_realtime("doc_update", {"doctype": "QA Issue", "name": issue}, doctype="QA Issue", docname=issue)
	return row


def save_file(issue, filename, content, is_private=1):
	"""Save bytes as a File attached to the issue and return its URL."""
	frappe.flags.qa_skip_file_hook = True
	try:
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": filename,
				"content": content,
				"attached_to_doctype": "QA Issue",
				"attached_to_name": issue,
				"is_private": is_private,
			}
		)
		f.flags.ignore_permissions = True
		f.insert()
		return f.file_url
	finally:
		frappe.flags.qa_skip_file_hook = False


def add_screenshot(issue, file_url, caption=None, field="screenshots", user=None):
	if frappe.db.exists("QA Screenshot", {"parent": issue, "parentfield": field, "image": file_url}):
		return
	user = user or frappe.session.user
	append_child(
		issue,
		field,
		{"image": file_url, "caption": caption, "added_by": user if user != "Guest" else None},
		child_doctype="QA Screenshot",
	)


def html2text(html):
	"""HTML -> plain text, across Frappe versions."""
	if not html:
		return ""
	try:
		from frappe.core.utils import html2text as _h2t

		return _h2t(html, wrap=False)
	except Exception:
		import re as _re

		text = _re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", html)
		return frappe.utils.strip_html(text)


def refresh_issue_code(issue):
	"""Recompute the SITE-MODULE code after site/module were changed with db.set_value."""
	doc = frappe.get_doc("QA Issue", issue)
	old = doc.issue_code
	doc.set_issue_code()
	if doc.issue_code != old:
		frappe.db.set_value("QA Issue", issue, "issue_code", doc.issue_code, update_modified=False)


def link_file_to_issue(file_url, issue, file_name=None):
	"""Register an existing private file (e.g. an email attachment, which belongs to the
	Communication) against the issue too, so everyone who can read the issue can view it."""
	if frappe.db.exists("File", {"file_url": file_url, "attached_to_doctype": "QA Issue", "attached_to_name": issue}):
		return
	frappe.flags.qa_skip_file_hook = True
	try:
		f = frappe.get_doc(
			{
				"doctype": "File",
				"file_url": file_url,
				"file_name": file_name or file_url.rsplit("/", 1)[-1],
				"attached_to_doctype": "QA Issue",
				"attached_to_name": issue,
				"is_private": 1 if file_url.startswith("/private/") else 0,
			}
		)
		f.flags.ignore_permissions = True
		f.insert()
	except Exception:
		frappe.log_error(title="QA Tracker: could not link file to issue", message=frappe.get_traceback())
	finally:
		frappe.flags.qa_skip_file_hook = False


VIDEO_EXT = (".webm", ".mp4", ".mov", ".m4v", ".ogg", ".mkv")
DOC_EXT = {
	".pdf": "PDF",
	".xlsx": "Spreadsheet", ".xls": "Spreadsheet", ".xlsm": "Spreadsheet", ".csv": "Spreadsheet", ".ods": "Spreadsheet",
	".docx": "Document", ".doc": "Document", ".odt": "Document", ".rtf": "Document", ".txt": "Document",
	".pptx": "Document", ".ppt": "Document",
	".zip": "Other", ".log": "Other", ".json": "Other", ".xml": "Other", ".har": "Other",
}


def is_video(name):
	return bool(name) and name.lower().split("?")[0].endswith(VIDEO_EXT)


def file_kind(name):
	"""Recording / PDF / Spreadsheet / Document / Other, or None if the type isn't allowed."""
	n = (name or "").lower().split("?")[0]
	if n.endswith(VIDEO_EXT):
		return "Recording"
	for ext, kind in DOC_EXT.items():
		if n.endswith(ext):
			return kind
	return None


def max_upload_bytes():
	"""The site's upload limit (Frappe default 10 MB, configurable with max_file_size)."""
	try:
		from frappe.core.api.file import get_max_file_size

		return int(get_max_file_size())
	except Exception:
		return int(frappe.conf.get("max_file_size") or 10 * 1024 * 1024)


def attach_existing_file(file_url, doctype, name):
	"""Link a file the current user just uploaded (via /api/method/upload_file) to a document.

	Only the uploader (or a System Manager) can link an unattached file, so people
	can't attach other users' private files by guessing URLs."""
	if not file_url or not isinstance(file_url, str):
		return None
	files = frappe.get_all("File", filters={"file_url": file_url},
		fields=["name", "owner", "attached_to_doctype", "attached_to_name", "file_name", "is_private"])
	if not files:
		frappe.throw(frappe._("Uploaded file not found: {0}").format(file_url))
	mine = [f for f in files if f.owner == frappe.session.user or "System Manager" in frappe.get_roles()]
	if not mine:
		frappe.throw(frappe._("You can only attach files you uploaded"), frappe.PermissionError)
	if any(f.attached_to_doctype == doctype and f.attached_to_name == name for f in files):
		return file_url
	free = [f for f in mine if not f.attached_to_name]
	frappe.flags.qa_skip_file_hook = True
	try:
		if free:
			frappe.db.set_value("File", free[0].name, {"attached_to_doctype": doctype, "attached_to_name": name})
		else:
			src = mine[0]
			frappe.get_doc({"doctype": "File", "file_url": file_url, "file_name": src.file_name,
				"attached_to_doctype": doctype, "attached_to_name": name, "is_private": src.is_private}).insert(ignore_permissions=True)
	finally:
		frappe.flags.qa_skip_file_hook = False
	return file_url


def parse_files(files=None, videos=None):
	"""[{url, duration, name}] or [url] -> allowed attachments (recordings and documents)."""
	items = []
	for value in (files, videos):
		if not value:
			continue
		value = frappe.parse_json(value) if isinstance(value, str) else value
		items.extend(value or [])
	out = []
	for v in items:
		if isinstance(v, str):
			v = {"url": v}
		if not (v and v.get("url")):
			continue
		kind = file_kind(v["url"])
		if not kind:
			frappe.throw(frappe._("This file type can't be attached: {0}").format(v["url"].rsplit("/", 1)[-1]))
		out.append({"url": v["url"], "duration": (v.get("duration") or "")[:12] if kind == "Recording" else "",
			"kind": kind, "name": (v.get("name") or v["url"].rsplit("/", 1)[-1])[:140]})
	return out[:15]


parse_videos = parse_files  # backwards compatible name


def add_attachment(parent, parenttype, item, caption=None, field="media_files"):
	"""Add an uploaded recording / document row to a document's Recordings & Files table."""
	url = item["url"] if isinstance(item, dict) else item
	if frappe.db.exists("QA Attachment", {"parent": parent, "parentfield": field, "file": url}):
		return
	idx = frappe.db.sql("select ifnull(max(idx),0) from `tabQA Attachment` where parent=%s and parentfield=%s", (parent, field))[0][0]
	frappe.get_doc({"doctype": "QA Attachment", "parent": parent, "parenttype": parenttype, "parentfield": field,
		"idx": idx + 1, "file": url, "file_type": (item.get("kind") if isinstance(item, dict) else None) or file_kind(url) or "Other",
		"caption": caption, "duration": item.get("duration") if isinstance(item, dict) else None,
		"added_by": frappe.session.user if frappe.session.user != "Guest" else None}).db_insert()
	frappe.db.set_value(parenttype, parent, "modified_by", frappe.session.user)
