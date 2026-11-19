"""Import existing Word observation documents and Excel issue trackers.

Word (.docx): each observation (a paragraph, or consecutive lines without a
screenshot between them; a numbered line "3. ..." always starts a new one) becomes
an issue. Screenshots that follow an observation are attached to it; screenshots at
the very top of the document go to the first observation.

Excel (.xlsx): the header row is detected by a column named like "Issue". Columns
recognised: S.No, Issue, Status / Vendor Status, Resolution, Test Result / Retest,
Module, Severity, Remarks (the unnamed column next to Issue is used as root cause).
"""

import difflib
import io
import os
import re

import frappe
from frappe.utils import cstr, now_datetime

from qa_tracker import intake
from qa_tracker.utils import add_screenshot, append_child, save_file

NUMBERED = re.compile(r"^\s*\d{1,3}\s*[\.\)]\s+")
IMAGE_MIME_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


# ---------------------------------------------------------------------------
def import_batch(batch_name):
	batch = frappe.get_doc("QA Import Batch", batch_name)
	file_doc = frappe.get_doc("File", {"file_url": batch.source_file})
	path = file_doc.get_full_path()
	log = []
	try:
		if path.lower().endswith(".docx"):
			names = import_docx(path, batch.site, batch.default_module, batch.test_cycle, batch.reported_by, batch.name, log)
		elif path.lower().endswith((".xlsx", ".xlsm")):
			names = import_xlsx(path, batch.site, batch.default_module, batch.test_cycle, batch.reported_by, batch.name, log)
		else:
			frappe.throw("Only .docx and .xlsx files can be imported")
		if batch.get("project") and names:
			frappe.db.sql("update `tabQA Issue` set project=%s where import_batch=%s", (batch.project, batch.name))
		batch.db_set({"status": "Completed", "issues_created": len(names), "log": "\n".join(log)})
		return len(names)
	except Exception:
		frappe.db.rollback()
		batch.db_set({"status": "Failed", "log": "\n".join(log) + "\n\n" + frappe.get_traceback()})
		frappe.db.commit()
		raise


# ---------------------------------------------------------------------------
# Word
# ---------------------------------------------------------------------------
def parse_docx(path):
	"""Return a list of observations: dict(lines=[...], images=[(filename, bytes)])."""
	import docx
	from docx.oxml.ns import qn

	document = docx.Document(path)
	parts = document.part.related_parts
	blocks = []  # sequence of ("text", str) / ("image", (name, bytes))

	def walk(el):
		for child in el.iterchildren():
			tag = child.tag
			if tag == qn("w:p"):
				txt = "".join(t.text or "" for t in child.iter(qn("w:t"))).strip()
				if txt:
					blocks.append(("text", txt))
				for blip in child.iter(qn("a:blip")):
					rid = blip.get(qn("r:embed"))
					part = parts.get(rid)
					if part is None:
						continue
					ext = os.path.splitext(str(part.partname))[1].lower()
					if ext in IMAGE_MIME_EXT:
						blocks.append(("image", (os.path.basename(str(part.partname)), part.blob)))
			elif tag == qn("w:tbl"):
				for cell in child.iter(qn("w:tc")):
					walk(cell)
			elif tag == qn("w:sdt"):
				walk(child)

	walk(document.element.body)

	obs = []
	leading_images = []
	current = None
	last = None
	for kind, value in blocks:
		if kind == "text":
			start_new = current is None or last == "image" or bool(NUMBERED.match(value))
			if start_new:
				current = {"lines": [value], "images": []}
				obs.append(current)
				if leading_images:
					current["images"].extend(leading_images)
					leading_images = []
			else:
				current["lines"].append(value)
		else:
			if current is None:
				leading_images.append(value)
			else:
				current["images"].append(value)
		last = kind
	if leading_images and not obs:
		obs.append({"lines": [], "images": leading_images})
	return obs


def import_docx(path, site, default_module=None, test_cycle=None, reported_by=None, batch=None, log=None):
	log = log if log is not None else []
	source = os.path.basename(path)
	names = []
	for i, ob in enumerate(parse_docx(path), 1):
		text = "\n".join(ob["lines"])
		clean, tags = intake.parse_tags(text)
		title = intake.make_title(clean, f"Screenshot observation {i} from {source}")
		doc = frappe.get_doc(
			{
				"doctype": "QA Issue",
				"title": title,
				"description": intake.text_to_html(clean),
				"issue_type": tags.get("issue_type") or intake.guess_type(clean),
				"severity": tags.get("severity") or "Medium",
				"site": tags.get("site") or site,
				"module": tags.get("module") or intake.guess_module(clean) or default_module,
				"test_cycle": test_cycle,
				"reported_by": reported_by,
				"source_channel": "Import",
				"source_document": source,
				"source_reference": f"Observation {i}",
				"import_batch": batch,
			}
		)
		doc.possible_duplicate_of = find_duplicate(title, doc.site)
		doc.flags.ignore_mandatory = True
		doc.insert(ignore_permissions=True)
		for j, (fname, blob) in enumerate(ob["images"], 1):
			ext = os.path.splitext(fname)[1] or ".png"
			url = save_file(doc.name, f"{doc.name}_{j}{ext}", blob)
			add_screenshot(doc.name, url, caption=f"{source} #{i}.{j}", user=reported_by or frappe.session.user)
		names.append(doc.name)
		log.append(f"{doc.name}: {title[:80]} ({len(ob['images'])} screenshots, module {doc.module})")
	return names


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def _find_header(ws):
	for row in ws.iter_rows(min_row=1, max_row=min(ws.max_row, 15)):
		values = [cstr(c.value).strip().lower() for c in row]
		if any(v in ("issue", "issues", "issue description", "description", "observation") for v in values):
			return row[0].row, values
	return None, None


def _col(values, *names, exclude=()):
	for i, v in enumerate(values):
		if any(n in v for n in names) and not any(x in v for x in exclude):
			return i
	return None


def map_status(vendor, test):
	v, t = cstr(vendor).lower(), cstr(test).lower()
	status = None
	if t and any(k in t for k in ("complete", "pass", "ok", "verified", "closed", "done")) and "not" not in t:
		return "Retest Passed"
	if t and any(k in t for k in ("fail", "not ok", "reopen")):
		return "Reopened"
	if v:
		if any(k in v for k in ("to be done", "pending", "open", "not ", "todo", "to do")):
			status = "Assigned"
		elif any(k in v for k in ("push", "progress", "wip", "working")):
			status = "In Progress"
		elif any(k in v for k in ("fixed", "complete", "done", "resolved", "closed")):
			status = "Ready for Retest"
	return status


def import_xlsx(path, site, default_module=None, test_cycle=None, reported_by=None, batch=None, log=None):
	import openpyxl

	log = log if log is not None else []
	wb = openpyxl.load_workbook(path, data_only=True)
	source = os.path.basename(path)
	names = []
	for ws in wb.worksheets:
		header_row, values = _find_header(ws)
		if not header_row:
			log.append(f"Sheet '{ws.title}': no 'Issue' header found - skipped")
			continue
		c_issue = _col(values, "issue", "description", "observation", exclude=("status",))
		c_sno = _col(values, "s.no", "s/n", "sno", "sl", "#", "no.")
		c_res = _col(values, "resolution", "fix", "action taken", "response")
		c_test = _col(values, "test result", "retest", "verification", "verified")
		c_status = _col(values, "status", exclude=("test",))
		c_module = _col(values, "module")
		c_sev = _col(values, "severity", "priority")
		c_remark = None
		if c_issue is not None and c_issue + 1 < len(values) and not values[c_issue + 1]:
			c_remark = c_issue + 1
		c_remark = _col(values, "remark", "comment", "root cause", "cause") if c_remark is None else c_remark

		for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
			row = list(row) + [None] * 10
			text = cstr(row[c_issue]).strip() if c_issue is not None else ""
			if not text:
				continue
			clean, tags = intake.parse_tags(text)
			module = tags.get("module")
			if not module and c_module is not None and row[c_module]:
				module = frappe.db.get_value("QA Module", {"module_name": cstr(row[c_module]).strip()}) or frappe.db.get_value(
					"QA Module", {"module_code": cstr(row[c_module]).strip().upper()}
				)
			module = module or intake.guess_module(clean) or default_module
			sev = cstr(row[c_sev]).strip().title() if c_sev is not None and row[c_sev] else None
			sev = {"Critical": "Blocker", "Blocker": "Blocker", "High": "High", "Low": "Low"}.get(sev, tags.get("severity") or "Medium")
			vendor = row[c_status] if c_status is not None else None
			test = row[c_test] if c_test is not None else None
			sno = cstr(row[c_sno]).strip() if c_sno is not None else ""
			title = intake.make_title(clean, "Imported issue")
			doc = frappe.get_doc(
				{
					"doctype": "QA Issue",
					"title": title,
					"description": intake.text_to_html(clean),
					"issue_type": tags.get("issue_type") or intake.guess_type(clean),
					"severity": sev,
					"site": tags.get("site") or site,
					"module": module,
					"test_cycle": test_cycle,
					"reported_by": reported_by,
					"root_cause": cstr(row[c_remark]).strip() if c_remark is not None and row[c_remark] else None,
					"resolution": cstr(row[c_res]).strip() if c_res is not None and row[c_res] else None,
					"source_channel": "Import",
					"source_document": source,
					"source_reference": f"{ws.title} / S.No {sno or '?'}",
					"import_batch": batch,
				}
			)
			doc.possible_duplicate_of = find_duplicate(title, doc.site)
			doc.flags.ignore_mandatory = True
			doc.insert(ignore_permissions=True)
			status = map_status(vendor, test)
			if status:
				frappe.db.set_value("QA Issue", doc.name, "status", status)
				if status == "Retest Passed":
					frappe.db.set_value("QA Issue", doc.name, {"retest_result": "Pass", "retest_notes": cstr(test)})
				append_child(
					doc.name,
					"updates",
					{
						"posted_on": now_datetime(),
						"posted_by": frappe.session.user,
						"party": "System",
						"channel": "System",
						"update_type": "Status Change",
						"message": f"Imported from {source} with status {status} (vendor: '{cstr(vendor)}', test: '{cstr(test)}')",
					},
				)
			names.append(doc.name)
			log.append(f"{doc.name}: [{status or 'New'}] {title[:80]}{'  ~dup of ' + doc.possible_duplicate_of if doc.possible_duplicate_of else ''}")
	return names


# ---------------------------------------------------------------------------
def find_duplicate(title, site=None, threshold=0.82):
	title_l = (title or "").lower().strip()
	if len(title_l) < 12:
		return None
	filters = {"site": site} if site else {}
	best, best_ratio = None, threshold
	for r in frappe.get_all("QA Issue", filters=filters, fields=["name", "title"], order_by="creation desc", limit=3000):
		ratio = difflib.SequenceMatcher(None, title_l, (r.title or "").lower()).ratio()
		if ratio > best_ratio:
			best, best_ratio = r.name, ratio
	return best


def import_path(path, site, default_module=None, test_cycle=None, reported_by=None):
	"""bench execute helper: import a file or every .docx/.xlsx in a folder.

	bench --site <site> execute qa_tracker.importer.import_path --kwargs "{'path': '/tmp/docs', 'site': 'Parklands'}"
	"""
	files = [path] if os.path.isfile(path) else [
		os.path.join(path, f) for f in sorted(os.listdir(path)) if f.lower().endswith((".docx", ".xlsx"))
	]
	total = []
	for f in files:
		log = []
		if f.lower().endswith(".docx"):
			total += import_docx(f, site, default_module, test_cycle, reported_by, None, log)
		else:
			total += import_xlsx(f, site, default_module, test_cycle, reported_by, None, log)
		print(f"== {os.path.basename(f)}\n" + "\n".join(log))
	frappe.db.commit()
	return len(total)
