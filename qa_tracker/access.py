# Copyright (c) 2026, QA Tracker contributors
# License: MIT
"""Multi-project, multi-vendor access rules.

* System Managers (and Administrator) see everything.
* Everyone else sees the projects they are an active member of (QA Project > Team) and every
  sub-project below them.
* A member with a Vendor set is vendor staff: they only see records of their vendor.
* Allocation rows (QA Project > Allocations) narrow a member to site subtrees and/or areas.
  No allocation rows = the whole project. Records with no site / area yet stay visible to them.
* People always see tickets they reported themselves.

Each membership becomes one or more *grants*: (projects, vendor, sites, modules), where
None means "any". A record is visible when at least one grant matches it.
"""

import frappe
from frappe import _

# project role -> Frappe role that carries the workflow rights
ROLE_MAP = {
	"QA Lead": "QA Lead",
	"Tester": "QA Tester",
	"Developer": "Vendor Developer",
	"UAT User": "UAT User",
	"Viewer": "QA Viewer",
	"Gap Analyst": "GA Analyst",
	"Gap Approver": "GA Approver",
}

# doctype -> how it is scoped
#   vendor / site / module: fieldnames used for the grant's limits (None = not limited by it)
#   container: vendor staff / allocated people also see records with those fields blank (cycles, workshops)
#   blank_project_ok: records without a project are visible to every member (shared libraries)
#   own: fields that always grant access to that user
RULES = {
	"QA Issue": dict(vendor="vendor", site="site", module="module", own=("reported_by", "owner")),
	"QA Test Cycle": dict(vendor="vendor", site="site", container=True),
	"QA Test Case": dict(module="module", blank_project_ok=True),
	"QA Test Execution": dict(module="module", own=("tester",)),
	"QA Import Batch": dict(site="site", own=("owner",)),
	"QA Module": dict(blank_project_ok=True),
	"Gap Assessment": dict(vendor="vendor", site="site", module="module", container=True),
	"Gap Item": dict(vendor="vendor", site="site", module="module", own=("owner",)),
}


def is_admin(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _scope_cache():
	c = getattr(frappe.local, "qa_scope_cache", None)
	if c is None:
		c = {}
		frappe.local.qa_scope_cache = c
	return c


def clear_cache():
	frappe.local.qa_scope_cache = {}


# ---------------------------------------------------------------- trees
def descendants(doctype, name):
	"""name and everything under it (QA Project / QA Site trees)."""
	if not name:
		return set()
	key = ("desc", doctype, name)
	c = _scope_cache()
	if key not in c:
		lr = frappe.db.get_value(doctype, name, ["lft", "rgt"])
		if not lr or not lr[0]:
			c[key] = {name}
		else:
			c[key] = set(frappe.get_all(doctype, filters={"lft": [">=", lr[0]], "rgt": ["<=", lr[1]]}, pluck="name")) | {name}
	return c[key]


def ancestors(doctype, name):
	"""name and its parents, nearest first."""
	if not name:
		return []
	key = ("anc", doctype, name)
	c = _scope_cache()
	if key not in c:
		lr = frappe.db.get_value(doctype, name, ["lft", "rgt"])
		if not lr or not lr[0]:
			c[key] = [name]
		else:
			rows = frappe.get_all(doctype, filters={"lft": ["<=", lr[0]], "rgt": [">=", lr[1]]}, fields=["name", "lft"], order_by="lft desc")
			c[key] = [r.name for r in rows] or [name]
	return c[key]


# ---------------------------------------------------------------- scope
def scope(user=None):
	"""None means 'everything'. Otherwise a dict with
	grants: [dict(projects, vendor, sites, modules)], projects: all visible projects,
	full: projects seen without any limit, vendor: {project: {vendors}} for vendor staff."""
	user = user or frappe.session.user
	if is_admin(user):
		return None
	cache = _scope_cache()
	if ("scope", user) in cache:
		return cache[("scope", user)]
	rows = frappe.db.sql(
		"""select parent, vendor from `tabQA Project Member`
		where parenttype='QA Project' and user=%s and is_active=1""",
		user,
		as_dict=True,
	)
	alloc = {}
	if rows:
		for a in frappe.db.sql(
			"""select parent, site, module from `tabQA Project Allocation` where parenttype='QA Project' and user=%s""",
			user,
			as_dict=True,
		):
			alloc.setdefault(a.parent, []).append(a)
	grants = []
	for r in rows:
		projs = frozenset(descendants("QA Project", r.parent))
		for a in alloc.get(r.parent) or [None]:
			grants.append(
				frappe._dict(
					projects=projs,
					vendor=r.vendor or None,
					sites=frozenset(descendants("QA Site", a.site)) if a and a.site else None,
					modules=frozenset([a.module]) if a and a.module else None,
				)
			)
	full, vend, projects = set(), {}, set()
	for g in grants:
		projects |= g.projects
		if not g.vendor and g.sites is None and g.modules is None:
			full |= g.projects
		elif g.vendor:
			for p in g.projects:
				vend.setdefault(p, set()).add(g.vendor)
	for p in full:
		vend.pop(p, None)
	s = frappe._dict(grants=grants, full=full, vendor=vend, projects=projects)
	cache[("scope", user)] = s
	return s


def my_projects(user=None):
	"""Projects the user may pick in the portal, in tree order with depth and path."""
	s = scope(user)
	filters = {} if s is None else {"name": ["in", list(s.projects) or ["-"]]}
	rows = frappe.get_all(
		"QA Project",
		filters=filters,
		fields=["name", "project_code", "client", "status", "root_site", "go_live_date", "parent_qa_project", "lft", "rgt"],
		order_by="lft asc",
	)
	names = {r.name for r in rows}
	for r in rows:
		chain = [a for a in ancestors("QA Project", r.name)[1:] if a in names]
		r.depth = len(chain)
		r.path = " › ".join(list(reversed(chain)) + [r.name])
	return rows


def grants_for(user, project):
	s = scope(user)
	if s is None:
		return None
	return [g for g in s.grants if project in g.projects]


def vendor_of(user, project):
	"""The vendor a user works for in a project (None for client staff / admins)."""
	gs = grants_for(user, project)
	if gs is None or not gs or any(not g.vendor for g in gs):
		return None
	return sorted({g.vendor for g in gs})[0]


def limits(user, project):
	"""(sites, modules) the user is allocated to in a project; None = no limit."""
	gs = grants_for(user, project)
	if gs is None or not gs:
		return None, None
	sites = None if any(g.sites is None for g in gs) else set().union(*[g.sites for g in gs])
	mods = None if any(g.modules is None for g in gs) else set().union(*[g.modules for g in gs])
	return sites, mods


def is_project_lead(user, project):
	"""QA Lead (client side) of this project or of a parent project."""
	if is_admin(user):
		return True
	if not project:
		return False
	return bool(
		frappe.db.sql(
			"""select 1 from `tabQA Project Member` where parenttype='QA Project' and user=%s and is_active=1
			and project_role='QA Lead' and ifnull(vendor, '')='' and parent in %s limit 1""",
			(user, tuple(ancestors("QA Project", project))),
		)
	)


def _q(vals):
	return ", ".join(frappe.db.escape(v) for v in sorted(vals))


def _field_cond(t, field, vals, blank_ok):
	cond = f"{t}.`{field}` in ({_q(vals)})" if vals else "1=0"
	return f"(ifnull({t}.`{field}`, '') = '' or {cond})" if blank_ok else cond


def condition(doctype, user=None):
	rule = RULES[doctype]
	user = user or frappe.session.user
	s = scope(user)
	if s is None:
		return ""
	t = f"`tab{doctype}`"
	container = rule.get("container")
	groups = {}
	for g in s.grants:
		key = (
			g.vendor if rule.get("vendor") else None,
			g.sites if rule.get("site") else None,
			g.modules if rule.get("module") else None,
		)
		groups.setdefault(key, set()).update(g.projects)
	parts = []
	for (vendor, sites, mods), projs in groups.items():
		conds = [f"{t}.`project` in ({_q(projs)})"]
		if vendor:
			conds.append(_field_cond(t, rule["vendor"], [vendor], container))
		# a record with no site / area yet is not specific to one place: people with limits still see it
		if sites is not None:
			conds.append(_field_cond(t, rule["site"], sites, True))
		if mods is not None:
			conds.append(_field_cond(t, rule["module"], mods, True))
		parts.append("(" + " and ".join(conds) + ")")
	if rule.get("blank_project_ok"):
		parts.append(f"ifnull({t}.`project`, '') = ''")
	for f in rule.get("own") or ():
		parts.append(f"{t}.`{f}` = {frappe.db.escape(user)}")
	return "(" + " or ".join(parts) + ")" if parts else "1=0"


def _match(value, allowed, blank_ok):
	if allowed is None:
		return True
	if not value:
		return bool(blank_ok)
	return value in allowed


def can_access(doctype, doc, user=None):
	"""Row check used by has_permission, the portal and chat commands."""
	rule = RULES.get(doctype)
	if not rule:
		return True
	user = user or frappe.session.user
	s = scope(user)
	if s is None:
		return True
	for f in rule.get("own") or ():
		if doc.get(f) and doc.get(f) == user:
			return True
	project = doc.get("project")
	if not project:
		return bool(rule.get("blank_project_ok"))
	container = rule.get("container")
	for g in s.grants:
		if project not in g.projects:
			continue
		if rule.get("vendor") and g.vendor and not _match(doc.get(rule["vendor"]), {g.vendor}, container):
			continue
		if rule.get("site") and not _match(doc.get(rule["site"]), g.sites, True):
			continue
		if rule.get("module") and not _match(doc.get(rule["module"]), g.modules, True):
			continue
		return True
	return False


def check(doctype, doc, user=None):
	if not can_access(doctype, doc, user):
		frappe.throw(_("You don't have access to {0} {1}").format(_(doctype), doc.get("name") or ""), frappe.PermissionError)


def check_project(project, user=None):
	"""May this user create records in this project?"""
	s = scope(user)
	if s is None or not project:
		return
	if project not in s.projects:
		frappe.throw(_("You are not a member of project {0}").format(project), frappe.PermissionError)


# ---------------------------------------------------------------- Frappe hooks
def has_permission(doc, ptype=None, user=None, **kwargs):
	# Hooks can only restrict (never grant beyond role permissions). Return True = "no objection":
	# Frappe 16 treats None as a denial, Frappe 14/15 treat True and None the same.
	if doc.doctype == "QA Project":
		return _project_perm(doc, ptype, user)
	if doc.doctype == "QA Vendor":
		return bool(_vendor_visible(doc.name, user) or ptype == "create")
	if doc.doctype not in RULES:
		return True
	if doc.is_new() and not doc.get("project"):
		return True  # defaults are filled in validate, then checked again on save
	return bool(can_access(doc.doctype, doc, user))


def _project_perm(doc, ptype, user):
	user = user or frappe.session.user
	s = scope(user)
	if s is None:
		return True
	if doc.is_new():
		# new top-level projects: QA Leads (role check is done by Frappe); sub-projects: leads of the parent
		return not doc.get("parent_qa_project") or is_project_lead(user, doc.parent_qa_project)
	if doc.name not in s.projects:
		return False
	if ptype in ("write", "delete", "submit", "cancel", "amend", "share"):
		return is_project_lead(user, doc.name)
	return True


def _vendor_names(user=None):
	s = scope(user)
	if s is None:
		return None
	names = set()
	for vs in s.vendor.values():
		names |= vs
	for p in s.full:
		names |= {v.vendor for v in project_vendors(p)}
	return names


def _vendor_visible(vendor, user=None):
	names = _vendor_names(user)
	return names is None or vendor in names


def _make_pqc(doctype):
	def pqc(user=None, **kwargs):
		return condition(doctype, user)

	return pqc


for _dt in RULES:
	globals()["pqc_" + frappe.scrub(_dt)] = _make_pqc(_dt)


def pqc_qa_project(user=None, **kwargs):
	s = scope(user)
	if s is None:
		return ""
	return f"`tabQA Project`.name in ({_q(s.projects)})" if s.projects else "1=0"


def pqc_qa_vendor(user=None, **kwargs):
	names = _vendor_names(user)
	if names is None:
		return ""
	return f"`tabQA Vendor`.name in ({_q(names)})" if names else "1=0"


# ---------------------------------------------------------------- sites
def project_root_site(project):
	"""The site tree root of a project, inherited from the nearest parent project that has one."""
	for p in ancestors("QA Project", project):
		r = frappe.db.get_value("QA Project", p, "root_site")
		if r:
			return r
	return None


def site_roots(user=None, project=None):
	"""Root sites the user may use. None = all sites."""
	s = scope(user)
	projects = [project] if project else (None if s is None else list(s.projects))
	if projects is None:
		return None
	if not projects:
		return []
	roots = [project_root_site(p) for p in projects]
	if any(not r for r in roots):
		return None
	return sorted(set(roots))


def pqc_qa_site(user=None, **kwargs):
	roots = site_roots(user)
	if roots is None:
		return ""
	if not roots:
		return "1=0"
	return (
		"exists (select 1 from `tabQA Site` r where r.name in (%s) "
		"and `tabQA Site`.lft >= r.lft and `tabQA Site`.rgt <= r.rgt)" % _q(roots)
	)


def sites_for_project(project):
	"""Active sites of a project's tree (all sites when the project has no root), with a path label."""
	root = project_root_site(project) if project else None
	filters = {"is_active": 1}
	if root:
		lft, rgt = frappe.db.get_value("QA Site", root, ["lft", "rgt"]) or (0, 0)
		filters.update({"lft": [">=", lft], "rgt": ["<=", rgt]})
	rows = frappe.get_all(
		"QA Site", filters=filters, fields=["name", "site_code", "parent_qa_site", "is_group", "lft", "site_type"], order_by="lft"
	)
	by = {r.name: r for r in rows}
	for r in rows:
		path, p, seen = [r.name], r.parent_qa_site, 0
		while p and p in by and seen < 8:
			path.insert(0, p)
			p, seen = by[p].parent_qa_site, seen + 1
		r.path = " › ".join(path)
	return rows


# ---------------------------------------------------------------- members / vendors (inherited down the tree)
def project_vendors(project):
	"""Vendors of a project and of its parent projects (nearest first)."""
	if not project:
		return []
	chain = ancestors("QA Project", project)
	rows = frappe.get_all(
		"QA Project Vendor",
		filters={"parenttype": "QA Project", "parent": ["in", chain]},
		fields=["vendor", "vendor_lead", "scope", "parent"],
		order_by="idx",
	)
	rows.sort(key=lambda r: chain.index(r.parent))
	seen, out = set(), []
	for r in rows:
		if r.vendor not in seen:
			seen.add(r.vendor)
			out.append(r)
	return out


def members_for(project, inherited=True):
	"""Active team rows of a project (and of its parents), nearest first."""
	if not project:
		return []
	chain = ancestors("QA Project", project) if inherited else [project]
	rows = frappe.db.sql(
		"""select m.name, m.parent, m.user, u.full_name, m.project_role, m.vendor, m.is_active
		from `tabQA Project Member` m join `tabUser` u on u.name = m.user
		where m.parenttype='QA Project' and m.parent in %s and u.enabled=1""",
		(tuple(chain),),
		as_dict=True,
	)
	rows.sort(key=lambda r: (chain.index(r.parent), r.full_name or r.user))
	return rows


def default_project_for(user):
	s = scope(user)
	if s is not None and len(s.projects) == 1:
		return next(iter(s.projects))
	dp = frappe.db.get_single_value("QA Settings", "default_project")
	if dp and (s is None or dp in s.projects):
		return dp
	if s is not None and s.projects:
		return sorted(s.projects)[0]
	return dp


# ---------------------------------------------------------------- defaults on save
def apply_defaults(doc, user=None):
	"""Fill project and vendor on a ticket / gap / cycle when they are missing."""
	user = user or doc.get("reported_by") or doc.owner or frappe.session.user
	if not doc.get("project"):
		doc.project = default_project_for(user)
	if doc.meta.has_field("vendor") and not doc.get("vendor"):
		v = vendor_of(user, doc.project) if doc.project else None
		if not v and doc.get("module"):
			v = frappe.db.get_value("QA Module", doc.module, "vendor")
		if not v:
			vs = project_vendors(doc.project)
			if len(vs) == 1:
				v = vs[0].vendor
		if v:
			doc.vendor = v


def validate_scoped(doc, method=None):
	"""doc_events validate for gaps, cycles and imports."""
	if not doc.get("project") and doc.get("assessment"):
		p, v = frappe.db.get_value("Gap Assessment", doc.assessment, ["project", "vendor"]) or (None, None)
		doc.project = p
		if doc.meta.has_field("vendor") and not doc.get("vendor"):
			doc.vendor = v
	if doc.doctype != "QA Import Batch" or not doc.get("project"):
		apply_defaults(doc)
	if doc.is_new() and doc.get("project") and not doc.flags.ignore_permissions:
		check_project(doc.project)


def default_assignee(doc):
	"""Module default assignee, else the vendor lead of the ticket's vendor in its project."""
	if doc.get("module"):
		a = frappe.db.get_value("QA Module", doc.module, "default_assignee")
		if a:
			return a
	for v in project_vendors(doc.get("project")):
		if v.vendor_lead and (not doc.get("vendor") or v.vendor == doc.vendor):
			return v.vendor_lead
	return None


def sla_days(vendor, severity):
	if not vendor:
		return None
	field = {"Blocker": "sla_blocker_days", "High": "sla_high_days", "Medium": "sla_medium_days", "Low": "sla_low_days"}.get(severity)
	return frappe.db.get_value("QA Vendor", vendor, field) if field else None


def developers(project=None, vendor=None):
	"""People who can be assigned a ticket: members (of the project or its parents) with the Developer role."""
	if not project:
		users = frappe.get_all("Has Role", filters={"role": "Vendor Developer", "parenttype": "User"}, pluck="parent")
		return frappe.get_all("User", filters={"name": ["in", users or ["-"]], "enabled": 1}, fields=["name", "full_name"])
	rows = [r for r in members_for(project) if r.is_active and r.project_role in ("Developer", "QA Lead")]
	rows.sort(key=lambda r: (r.project_role != "Developer", r.full_name or r.user))
	if vendor:
		rows = [r for r in rows if r.vendor in (vendor, None, "")]
	seen, out = set(), []
	for r in rows:
		if r.user not in seen:
			seen.add(r.user)
			out.append(frappe._dict(name=r.user, full_name=r.full_name, vendor=r.vendor))
	return out


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def developer_query(doctype, txt, searchfield, start, page_len, filters):
	filters = filters or {}
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	rows = developers(filters.get("project"), filters.get("vendor"))
	txt = (txt or "").lower()
	rows = [r for r in rows if txt in (r.name or "").lower() or txt in (r.full_name or "").lower()]
	return [(r.name, r.full_name) for r in rows[int(start) : int(start) + int(page_len)]]
