/* QA Tracker - management dashboard and drill-through list (plain JS, no build step) */
(function () {
	"use strict";
	const Q = window.QAP;
	if (!Q) return;
	const { esc, h, ic, toast, api } = Q;
	const $ = (s, el) => (el || document).querySelector(s);
	const st = Q.state;
	st.dash = st.dash || { vendor: "", site: "", level: "" };
	const n0 = (v) => (v === null || v === undefined ? "–" : v);
	const pctTxt = (v) => (v === null || v === undefined ? "–" : v + "%");
	const RAG_TXT = { red: "At risk", amber: "Watch", green: "On track" };

	function drill(filters, title) {
		const d = st.dash;
		st.drill = Object.assign({ vendor: d.vendor || undefined, site: d.site || undefined, level: d.level || undefined }, filters);
		st.drillTitle = title;
		location.hash = "#/list";
	}

	// ------------------------------------------------------------------ small charts
	function hbars(items, key) {
		const max = Math.max(1, ...items.map((x) => x.v));
		return `<div class="hbars">${items.map((x, i) => `<button class="hb" data-${key}="${i}" ${x.title ? `title="${esc(x.title)}"` : ""}>
			<span class="hb-l">${esc(x.label)}</span><span class="hb-t"><i style="width:${Math.max(x.v ? 3 : 0, (100 * x.v) / max)}%" class="${x.cls || ""}"></i>${x.red ? `<em style="width:${(100 * x.red) / max}%"></em>` : ""}</span>
			<b>${x.v}</b>${x.red ? `<small class="red">${x.red} blk</small>` : `<small></small>`}</button>`).join("")}</div>`;
	}

	function trendSvg(trend) {
		const W = 680, H = 210, L = 34, R = 12, T = 14, B = 34;
		const max = Math.max(1, ...trend.map((w) => Math.max(w.opened, w.closed, w.backlog)));
		const step = Math.ceil(max / 4 / 5) * 5 || 1, top = step * 4;
		const cw = (W - L - R) / trend.length, bw = Math.min(14, cw / 3);
		const y = (v) => T + (H - T - B) * (1 - v / top);
		const ticks = [0, 1, 2, 3, 4].map((i) => i * step);
		const fmt = (d) => { const [, m, dd] = d.split("-"); return `${+dd} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m - 1]}`; };
		const line = trend.map((w, i) => `${i ? "L" : "M"}${(L + cw * i + cw / 2).toFixed(1)} ${y(w.backlog).toFixed(1)}`).join("");
		return `<svg viewBox="0 0 ${W} ${H}" class="trend" role="img" aria-label="Tickets opened and closed per week, with open backlog">
			${ticks.map((t) => `<line x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}" class="grid"/><text x="${L - 6}" y="${y(t) + 4}" text-anchor="end" class="ax">${t}</text>`).join("")}
			${trend.map((w, i) => { const x = L + cw * i + cw / 2; return `<g><title>Week of ${fmt(w.week)}: ${w.opened} opened, ${w.closed} closed, ${w.backlog} open at week end</title>
				<rect x="${x - bw - 1}" y="${y(w.opened)}" width="${bw}" height="${y(0) - y(w.opened)}" rx="2" class="b-open"/>
				<rect x="${x + 1}" y="${y(w.closed)}" width="${bw}" height="${y(0) - y(w.closed)}" rx="2" class="b-closed"/>
				${i % 2 === trend.length % 2 ? "" : `<text x="${x}" y="${H - 12}" text-anchor="middle" class="ax">${fmt(w.week)}</text>`}</g>`; }).join("")}
			<path d="${line}" class="l-backlog"/>
			${trend.map((w, i) => `<circle cx="${L + cw * i + cw / 2}" cy="${y(w.backlog)}" r="2.6" class="d-backlog"/>`).join("")}
		</svg>
		<div class="legend"><span><i class="k-open"></i>Opened</span><span><i class="k-closed"></i>Closed</span><span><i class="k-backlog"></i>Open at week end</span></div>`;
	}

	// ------------------------------------------------------------------ dashboard
	async function viewDash() {
		const b = st.boot;
		if (!b.dashboard) { location.hash = "#/tickets"; return; }
		Q.app.innerHTML = Q.shell(`<div class="skel tall"></div><div class="skel"></div><div class="skel"></div>`, { tab: "dash" });
		Q.bindShell();
		let d;
		try {
			d = await api("dashboard", { vendor: st.dash.vendor || null, site: st.dash.site || null, level: st.dash.level || null });
		} catch (e) { toast(e.message, "err"); return; }
		render(d);
	}

	function render(d) {
		const k = d.kpis, b = st.boot;
		const title = d.project || "All my projects";
		const goLive = d.days_to_go_live === null ? "" : d.days_to_go_live >= 0 ? `Go-live in <b class="${d.days_to_go_live <= 14 && k.blockers ? "red" : ""}">${d.days_to_go_live} days</b> (${esc(d.go_live)})` : `Live since ${esc(d.go_live)}`;
		const opt = (arr, cur, blank, lab) => `<option value="">${esc(blank)}</option>` + arr.map((x) => { const v = x.name || x; return `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(lab ? lab(x) : v)}</option>`; }).join("");
		const tiles = [
			["open", "Open tickets", k.open, `${k.total} in total · ${k.done} done`, "", { open: 1 }],
			["blockers", "Open blockers", k.blockers, `${k.high} high`, k.blockers ? "red" : "", { severity: "Blocker" }],
			["overdue", "Past fix date", k.overdue, "vendor SLA target missed", k.overdue ? "amber" : "", { overdue: 1 }],
			["age", "Average age", k.avg_age, "days, open tickets", k.avg_age > 14 ? "amber" : "", null],
			["flow", "Last 7 days", `+${k.opened_7} / −${k.closed_7}`, `opened / closed · ${k.fixed_7} fixed`, k.opened_7 > k.closed_7 ? "amber" : "green", null],
			["mttr", "Time to fix", n0(k.mttr), "days, avg of last 30 days", "", null],
			["fp", "Fixed first time", pctTxt(k.first_pass), "passed retest without reopening", k.first_pass !== null && k.first_pass < 70 ? "amber" : "", null],
			["sla", "Fixed within SLA", pctTxt(k.sla_met), "of fixes that had a target date", k.sla_met !== null && k.sla_met < 80 ? "amber" : "", null],
		];
		const sp = d.subprojects;
		Q.app.innerHTML = Q.shell(`
		<section class="dash">
			<div class="dash-head">
				<div class="crumbs"><a href="#" data-proj="all">All my projects</a>${d.crumbs.map((c) => ` › <a href="#" data-proj="${esc(c)}">${esc(c)}</a>`).join("")}</div>
				<h1>${esc(title)}</h1>
				<p class="muted">${[d.client ? esc(d.client) : "", d.status ? esc(d.status) : "", goLive].filter(Boolean).join(" · ")}${d.scope_note ? ` · <b>${esc(d.scope_note)}</b>` : ""}</p>
				<div class="dash-filters">
					<select id="fv">${opt(d.options.vendors, st.dash.vendor, "All vendors")}</select>
					<select id="fs">${opt(d.options.sites, st.dash.site, "All sites", (x) => x.path)}</select>
					<select id="fl">${opt(d.options.levels, st.dash.level, "All support levels", (x) => "Support " + x)}</select>
					${st.dash.vendor || st.dash.site || st.dash.level ? `<button class="btn ghost sm" id="fclear">Clear filters</button>` : ""}
					<span class="muted small grow-r">Updated ${esc(d.generated)}</span>
				</div>
			</div>

			<div class="kpis">${tiles.map(([id, lbl, v, sub, cls, f]) => `<button class="kpi ${cls}" ${f ? `data-kpi="${id}"` : "disabled"}><span>${esc(lbl)}</span><b>${esc(String(v))}</b><small>${esc(sub)}</small></button>`).join("")}</div>

			${sp.length ? `<div class="panel"><div class="panel-h"><h2>${d.project ? "Sub-projects" : "Projects"}</h2><span class="muted small">Red: open blockers or 5+ past fix date · Amber: anything past fix date or open High</span></div>
				<div class="tbl-wrap"><table class="dtbl"><thead><tr><th></th><th>Project</th><th>Open</th><th>Blockers</th><th>Past fix date</th><th>7 days +/−</th><th>Done</th><th>Go-live</th><th></th></tr></thead><tbody>
				${sp.map((p, i) => `<tr><td><span class="rag rag-${p.rag}" title="${RAG_TXT[p.rag]}"></span></td><td><b>${esc(p.name)}</b><div class="muted small">${esc(p.code || "")} · ${esc(p.status || "")}</div></td>
					<td>${p.open}</td><td class="${p.blockers ? "red" : ""}">${p.blockers}</td><td class="${p.overdue ? "amber" : ""}">${p.overdue}</td>
					<td>+${p.opened_7} / −${p.closed_7}</td><td>${p.total ? Math.round((100 * p.done) / p.total) + "%" : "–"}</td>
					<td>${p.days_to_go_live === null ? "–" : p.days_to_go_live >= 0 ? `${p.days_to_go_live} d` : "live"}</td>
					<td><button class="btn ghost sm" data-sub="${i}">Open ${ic("arrow")}</button></td></tr>`).join("")}
				</tbody></table></div></div>` : ""}

			<div class="panel"><div class="panel-h"><h2>Weekly flow</h2><span class="muted small">Opened and closed each week; the line is how many were still open at week end</span></div>${trendSvg(d.trend)}</div>

			<div class="grid2">
				<div class="panel"><div class="panel-h"><h2>Where tickets are</h2></div>${hbars(d.stages.map((x) => ({ label: x.stage, v: x.count, red: x.blockers, cls: x.stage === "Done" ? "ok" : x.stage === "Parked" ? "mute" : "" })), "stage")}</div>
				<div class="panel"><div class="panel-h"><h2>Support levels</h2><span class="muted small">Open tickets held at each level</span></div>
					<div class="lvls">${d.levels.map((l, i) => `<button class="lvlcard" data-lvl="${i}"><span class="lvl lvl-${l.level}">${l.level}</span><b>${l.open}</b><small>open</small>
						<div class="muted small">${l.blockers ? `<span class="red">${l.blockers} blocker${l.blockers > 1 ? "s" : ""}</span> · ` : ""}${l.overdue ? `<span class="amber">${l.overdue} late</span> · ` : ""}${l.unassigned} unassigned · avg ${l.avg_age} d</div></button>`).join("")}</div>
					<p class="muted small">L1 hospital helpdesk · L2 application support · L3 vendor engineering</p></div>
			</div>

			<div class="grid2">
				<div class="panel"><div class="panel-h"><h2>Severity by support level</h2><span class="muted small">Open tickets</span></div>
					<table class="heat"><thead><tr><th></th>${d.levels_list.map((l) => `<th>${l}</th>`).join("")}<th>Total</th></tr></thead><tbody>
					${d.matrix.map((r, ri) => { const tot = r.cells.reduce((a, c) => a + c, 0); return `<tr><th>${Q.sevDot(r.severity)}${esc(r.severity)}</th>${r.cells.map((c, ci) => `<td><button class="hc ${c ? (ri === 0 ? "h-red" : ri === 1 ? "h-amber" : "h-blue") : ""}" data-heat="${ri}-${ci}" ${c ? "" : "disabled"}>${c || "·"}</button></td>`).join("")}<td><b>${tot}</b></td></tr>`; }).join("")}
					</tbody></table></div>
				<div class="panel"><div class="panel-h"><h2>Age of open tickets</h2></div>${hbars(d.ageing.map((a, i) => ({ label: a.bucket, v: a.count, red: a.blockers, cls: i >= 3 ? "warn" : "" })), "age")}</div>
			</div>

			${d.vendors.length ? `<div class="panel"><div class="panel-h"><h2>Vendors</h2><span class="muted small">Tap a vendor to filter the whole dashboard</span></div>
				<div class="tbl-wrap"><table class="dtbl"><thead><tr><th>Vendor</th><th>Open</th><th>Blockers</th><th>Past fix date</th><th>Avg age (d)</th><th>Fixed first time</th><th>Within SLA</th><th>Fixed</th></tr></thead><tbody>
				${d.vendors.map((v, i) => `<tr class="click" data-ven="${i}"><td><b>${esc(v.label)}</b></td><td>${v.open}</td><td class="${v.blockers ? "red" : ""}">${v.blockers}</td><td class="${v.overdue ? "amber" : ""}">${v.overdue}</td><td>${v.avg_age}</td><td>${pctTxt(v.first_pass)}</td><td>${pctTxt(v.sla_met)}</td><td>${v.fixed}</td></tr>`).join("")}
				</tbody></table></div></div>` : ""}

			<div class="grid2">
				<div class="panel"><div class="panel-h"><h2>By site</h2><span class="muted small">Groups open their branches</span></div>${hbars(d.sites.map((x) => ({ label: x.label || x.site, v: x.open, red: x.blockers, title: x.group ? "Group: tap to look inside" : "" })), "site")}</div>
				<div class="panel"><div class="panel-h"><h2>Busiest areas</h2><span class="muted small">Top 10, open tickets</span></div>${d.areas.length ? hbars(d.areas.map((x) => ({ label: x.module || "No area yet", v: x.open, red: x.blockers })), "area") : `<p class="muted">No open tickets.</p>`}</div>
			</div>

			${d.oldest.length ? `<div class="panel"><div class="panel-h"><h2>Oldest blockers and high tickets</h2></div><div class="olist">
				${d.oldest.map((o) => `<a class="orow" href="#/t/${encodeURIComponent(o.name)}">${Q.sevDot(o.severity)}<b>${esc(o.name)}</b><span class="ot">${esc(o.title)}</span>
					<span class="muted small">${[o.vendor, "Support " + o.level, o.status, o.assigned_to || "unassigned"].filter(Boolean).map(esc).join(" · ")}</span>
					<span class="oage ${o.age > 14 ? "red" : o.age > 7 ? "amber" : ""}">${o.age} d${o.overdue ? " · late" : ""}</span></a>`).join("")}</div></div>` : ""}

			${d.gaps && d.gaps.total ? `<div class="panel"><div class="panel-h"><h2>Gap analysis</h2><a class="muted small" href="#/gaps">Open gap tracker ${ic("arrow")}</a></div>
				<div class="kpis small">${[
					["Requirements", d.gaps.total, `${d.gaps.fit} fit · ${d.gaps.partial} partial · ${d.gaps.gap} gap`, ""],
					["Fit today", pctTxt(d.gaps.fit_pct), "of assessed requirements", ""],
					["Open must-haves", d.gaps.open_must, "not yet delivered", d.gaps.open_must ? "red" : ""],
					["Open regulatory", d.gaps.open_reg, "SHA, MoH, PPB, KRA…", d.gaps.open_reg ? "amber" : ""],
					["Awaiting approval", d.gaps.awaiting_approval, "business sign-off", ""],
					["To deliver", d.gaps.to_deliver, "approved, vendor working", ""],
					["To verify", d.gaps.to_verify, "delivered, check it", d.gaps.to_verify ? "amber" : ""],
					["Done", d.gaps.done, "verified or closed", "green"],
				].map(([l, v, s, c]) => `<a class="kpi ${c}" href="#/gaps"><span>${esc(l)}</span><b>${esc(String(v))}</b><small>${esc(s)}</small></a>`).join("")}</div></div>` : ""}
		</section>`, { tab: "dash" });
		Q.bindShell();
		bind(d);
	}

	function bind(d) {
		const A = Q.app;
		const setF = (key, val) => { st.dash[key] = val; viewDash(); };
		$("#fv", A).onchange = (e) => setF("vendor", e.target.value);
		$("#fs", A).onchange = (e) => setF("site", e.target.value);
		$("#fl", A).onchange = (e) => setF("level", e.target.value);
		if ($("#fclear", A)) $("#fclear", A).onclick = () => { st.dash = { vendor: "", site: "", level: "" }; viewDash(); };
		A.querySelectorAll("[data-proj]").forEach((el) => (el.onclick = (e) => { e.preventDefault(); st.dash.site = ""; Q.switchProject(el.dataset.proj).then(() => { location.hash = "#/dash"; }); }));
		A.querySelectorAll("[data-sub]").forEach((el) => (el.onclick = () => { st.dash.site = ""; Q.switchProject(d.subprojects[+el.dataset.sub].name).then(() => { location.hash = "#/dash"; }); }));
		const kpiF = { open: [{}, "Open tickets"], blockers: [{ severity: "Blocker" }, "Open blockers"], overdue: [{ overdue: 1 }, "Past fix date"] };
		A.querySelectorAll("[data-kpi]").forEach((el) => (el.onclick = () => { const [f, t] = kpiF[el.dataset.kpi]; drill(f, t); }));
		A.querySelectorAll("[data-stage]").forEach((el) => (el.onclick = () => { const s = d.stages[+el.dataset.stage].stage; drill({ stage: s, open: 0 }, `Stage: ${s}`); }));
		A.querySelectorAll("[data-lvl]").forEach((el) => (el.onclick = () => { const l = d.levels[+el.dataset.lvl].level; drill({ level: l }, `Support ${l}, open`); }));
		A.querySelectorAll("[data-heat]").forEach((el) => (el.onclick = () => { const [r, c] = el.dataset.heat.split("-").map(Number); drill({ severity: d.sevs[r], level: d.levels_list[c] }, `${d.sevs[r]} at ${d.levels_list[c]}`); }));
		A.querySelectorAll("[data-age]").forEach((el) => (el.onclick = () => { const a = d.ageing[+el.dataset.age].bucket; drill({ age: a }, `Open, ${a} old`); }));
		A.querySelectorAll("[data-ven]").forEach((el) => (el.onclick = () => setF("vendor", d.vendors[+el.dataset.ven].vendor)));
		A.querySelectorAll("[data-site]").forEach((el) => (el.onclick = () => {
			const s = d.sites[+el.dataset.site];
			if (!s.site) return drill({ site: "-" }, "Open, no site yet");
			if (s.group) setF("site", s.site); else drill({ site: s.site }, `Open at ${s.site}`);
		}));
		A.querySelectorAll("[data-area]").forEach((el) => (el.onclick = () => { const m = d.areas[+el.dataset.area].module; drill({ module: m }, `Open in ${m || "no area"}`); }));
	}

	// ------------------------------------------------------------------ drill-through list
	async function viewList() {
		const f = st.drill || { open: 1 };
		Q.app.innerHTML = Q.shell(`<section><div class="list-head"><h1>${esc(st.drillTitle || "Tickets")}</h1>
			<div class="chips">${Object.entries(f).filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => `<span class="chip on">${esc(k === "open" ? (v ? "open only" : "open and closed") : k === "overdue" ? "past fix date" : `${k}: ${v}`)}</span>`).join("")}</div></div>
			<div id="dlist"><div class="skel"></div><div class="skel"></div></div></section>`, { back: st.boot.dashboard ? "#/dash" : "#/tickets", title: "Tickets", nav: false });
		Q.bindShell();
		let rows = [];
		try { rows = await api("tickets", { scope: f.open === 0 ? "all" : "open", drill: JSON.stringify(f) }); } catch (e) { toast(e.message, "err"); }
		const box = $("#dlist");
		if (!rows.length) { box.innerHTML = `<div class="empty"><h3>No tickets</h3><p>Nothing matches these filters.</p></div>`; return; }
		box.innerHTML = rows.map((r) => `<a class="card tk" href="#/t/${encodeURIComponent(r.name)}">
			${r.thumb ? `<img class="tk-img" src="${esc(r.thumb)}" alt="" loading="lazy">` : `<div class="tk-img none">${ic("cam")}</div>`}
			<div class="tk-body"><div class="tk-top"><span class="muted">${Q.sevDot(r.severity)}${esc(r.name)}${r.module ? " · " + esc(r.module) : ""}</span>${Q.stagePill(r.status)}</div>
			<div class="tk-title">${esc(r.title)}</div>${Q.stageBar(r.stage)}
			<div class="muted small">${r.level ? `<span class="lvl lvl-${esc(r.level)}">${esc(r.level)}</span> · ` : ""}${r.vendor ? `<span class="vtag">${esc(r.vendor)}</span> · ` : ""}${r.project ? esc(r.project) + " · " : ""}${esc(r.ago)}</div></div></a>`).join("")
			+ (rows.length >= 30 ? `<p class="muted small center">Showing the 30 most recently changed. Narrow the filters to see others.</p>` : "");
	}

	Q.routes.dash = viewDash;
	Q.routes.list = viewList;
})();
