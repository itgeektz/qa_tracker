/* QA Tracker portal - Gap analysis screens: fast workshop capture + follow-up. Plain JS, no build step. */
(function () {
	"use strict";
	const Q = window.QAP;
	if (!Q) return;
	const { esc, h, ic, toast } = Q;
	const $ = (s, el) => (el || document).querySelector(s);
	async function call(method, args) {
		const res = await fetch("/api/method/qa_tracker.gap_analysis.portal." + method, {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.QA_CSRF, Accept: "application/json" },
			body: JSON.stringify(Object.assign(Q.project && Q.project() ? { project: Q.project() } : {}, args || {})), credentials: "same-origin",
		});
		let data = {};
		try { data = await res.json(); } catch (e) { /* ignore */ }
		if (!res.ok || data.exc || data.exception) {
			let msg = "Something went wrong. Try again.";
			try { const sm = JSON.parse(data._server_messages || "[]"); if (sm.length) msg = JSON.parse(sm[0]).message || msg; } catch (e) { /* ignore */ }
			throw new Error(String(msg).replace(/<[^>]+>/g, ""));
		}
		return data.message;
	}

	const FIT_CLS = { "Gap": "red", "Partial Fit": "amber", "Fit": "green", "Not Applicable": "gray" };
	const FIT_SHORT = { "Gap": "Gap", "Partial Fit": "Partial", "Fit": "Fit", "Not Applicable": "N/A" };
	const PRI_SHORT = { "Must Have": "Must", "Should Have": "Should", "Could Have": "Could", "Won't Have": "Won't" };
	const STAGES = ["Identified", "Analysed", "Approval", "Delivery", "Verify", "Closed"];
	const PILL = { Identified: "blue", Analysed: "teal", "Awaiting Approval": "amber", Approved: "violet", "In Progress": "violet",
		Delivered: "amber", Verified: "teal", Closed: "green", Deferred: "gray", Rejected: "gray" };
	const store = {
		get(k) { try { return localStorage.getItem("qa_gap_" + k); } catch (e) { return null; } },
		set(k, v) { try { localStorage.setItem("qa_gap_" + k, v); } catch (e) { /* private mode */ } },
	};
	const G = { boot: null, scope: "needs_you", assessment: store.get("assessment") || "", search: "", session: [],
		fit: store.get("fit") || "Gap", priority: store.get("priority") || "Should Have" };

	const pill = (s) => `<span class="pill ${PILL[s] || "gray"}">${esc(s)}</span>`;
	const fitPill = (f) => `<span class="pill ${FIT_CLS[f] || "gray"}">${esc(FIT_SHORT[f] || f)}</span>`;
	const bar = (i, labels) => `<div class="stages">${STAGES.map((s, k) => `<div class="st ${k < i ? "done" : k === i ? "cur" : ""}"><span></span>${labels ? `<em>${s}</em>` : ""}</div>`).join("")}</div>`;

	async function ensureBoot(force) {
		if (!G.boot || force || G.bootProject !== (Q.project && Q.project())) { G.boot = await call("boot"); G.bootProject = Q.project && Q.project(); }
		if (G.assessment && !G.boot.assessments.some((a) => a.name === G.assessment)) G.assessment = "";
		return G.boot;
	}
	const currentAssessment = () => (G.boot.assessments || []).find((a) => a.name === G.assessment);

	function assessmentSelect(id, withAll) {
		const opts = G.boot.assessments.map((a) => `<option value="${esc(a.name)}" ${a.name === G.assessment ? "selected" : ""}>${esc(a.name)}</option>`).join("");
		return `<select id="${id}" class="ga-sel">${withAll ? `<option value="">All assessments</option>` : `<option value="">Choose assessment…</option>`}${opts}
			${G.boot.can_capture ? `<option value="__new__">+ New assessment…</option>` : ""}</select>`;
	}

	function summaryStrip(a) {
		if (!a) return "";
		return `<div class="ga-sum"><div><b>${a.total}</b><span>Items</span></div><div><b class="t-green">${a.fit}</b><span>Fit</span></div>
			<div><b class="t-amber">${a.partial}</b><span>Partial</span></div><div><b class="t-red">${a.gap}</b><span>Gaps</span></div>
			<div><b>${a.fit_pct}%</b><span>Fit</span></div><div><b class="${a.must ? "t-red" : ""}">${a.must}</b><span>Open must</span></div></div>`;
	}

	// ------------------------------------------------------------------ new assessment sheet
	function newAssessmentSheet() {
		return new Promise((resolve) => {
			const b = Q.state.boot;
			const m = h(`<div class="modal sheet"><div class="sheet-box">
				<div class="sheet-head"><h3>New assessment</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
				<label class="lbl">Name</label><input id="an" placeholder="Parklands Pharmacy fit-gap">
				<label class="lbl">Site</label><div class="chips" id="asite">${b.sites.map((s) => `<button class="chip ${s.name === b.default_site ? "on" : ""}" data-v="${esc(s.name)}">${esc(s.name)}</button>`).join("")}</div>
				<label class="lbl">Area</label><select id="amod"><option value="">-</option>${b.modules.map((x) => `<option>${esc(x.name)}</option>`).join("")}</select>
				<label class="lbl">Business approver</label><select id="aapp"><option value="">-</option>${G.boot.approvers.map((u) => `<option value="${esc(u.value)}">${esc(u.label)}</option>`).join("")}</select>
				${(G.boot.vendors || []).length ? `<label class="lbl">Vendor / system assessed</label><select id="aven"><option value="">- not vendor specific -</option>${G.boot.vendors.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("")}</select>` : ""}
				<button class="btn primary block" data-go>Create and start capturing</button></div></div>`);
			document.body.appendChild(m);
			let site = b.default_site || null;
			m.querySelectorAll("#asite [data-v]").forEach((el) => (el.onclick = () => { site = el.dataset.v; m.querySelectorAll("#asite [data-v]").forEach((x) => x.classList.toggle("on", x === el)); }));
			const close = (v) => { m.remove(); resolve(v); };
			$("[data-x]", m).onclick = () => close(null);
			$("#an", m).focus();
			$("[data-go]", m).onclick = async () => {
				try {
					const a = await call("new_assessment", { name: $("#an", m).value, site, module: $("#amod", m).value || null, approver: $("#aapp", m).value || null, vendor: ($("#aven", m) || {}).value || null });
					toast("Assessment created", "ok");
					close(a);
				} catch (e) { toast(e.message, "err"); }
			};
		});
	}

	async function pickAssessment(sel, after) {
		if (sel.value === "__new__") {
			const a = await newAssessmentSheet();
			if (a) { await ensureBoot(true); G.assessment = a.name; store.set("assessment", a.name); }
			after();
			return;
		}
		G.assessment = sel.value; store.set("assessment", sel.value);
		after();
	}

	// ------------------------------------------------------------------ gaps home
	async function viewGaps(arg) {
		if (arg === "capture") return viewCapture();
		await ensureBoot(true);
		const b = G.boot;
		const scopes = [["needs_you", `Needs you${b.needs_you ? " · " + b.needs_you : ""}`], ["open", "Open"], ["done", "Closed"]];
		Q.app.innerHTML = Q.shell(`
			<section class="hello ga-head"><div><h1>Gap analysis</h1><p>${b.needs_you ? `${b.needs_you} item${b.needs_you > 1 ? "s" : ""} waiting for you.` : "Nothing waiting for you."}</p></div>
				${b.can_capture ? `<a class="btn primary" href="#/gaps/capture">${ic("bolt")} Capture</a>` : ""}</section>
			${assessmentSelect("gass", true)}
			${summaryStrip(currentAssessment())}
			<div class="search">${ic("search")}<input id="gq" placeholder="Search gaps or GAP number" value="${esc(G.search)}"></div>
			<div class="chips">${scopes.map(([k, l]) => `<button class="chip ${G.scope === k ? "on" : ""}" data-s="${k}">${l}</button>`).join("")}</div>
			<div id="glist" class="list"><div class="skel"></div><div class="skel"></div></div>`, { tab: "gaps" });
		Q.bindShell();
		$("#gass").onchange = (e) => pickAssessment(e.target, () => viewGaps());
		Q.app.querySelectorAll("[data-s]").forEach((el) => (el.onclick = () => { G.scope = el.dataset.s; viewGaps(); }));
		let t;
		$("#gq").oninput = (e) => { clearTimeout(t); t = setTimeout(() => { G.search = e.target.value; loadGaps(); }, 300); };
		loadGaps();
	}

	async function loadGaps() {
		const el = $("#glist");
		if (!el) return;
		const rows = await call("gaps", { scope: G.scope, assessment: G.assessment || null, search: G.search });
		if (!rows.length) {
			el.innerHTML = G.scope === "needs_you" && !G.search
				? `<div class="empty"><div class="em-ic">${ic("check")}</div><h3>You're all caught up</h3><p>Gaps waiting for your analysis, approval, delivery or verification show up here.</p>${G.boot.can_capture ? `<a class="btn primary" href="#/gaps/capture">${ic("bolt")} Start capturing</a>` : ""}</div>`
				: `<div class="empty"><h3>No gaps found</h3><p>Try another tab or assessment.</p></div>`;
			return;
		}
		el.innerHTML = rows.map(rowHtml).join("");
	}

	const rowHtml = (r) => `<a class="card ga-row fit-${(FIT_CLS[r.fit] || "gray")} ${r.needs_you ? "needs" : ""}" href="#/gap/${encodeURIComponent(r.name)}">
		<div class="tk-top"><span class="muted">${esc(r.code || r.name)}${r.module ? " · " + esc(r.module) : ""}</span>${pill(r.status)}</div>
		<div class="tk-title">${esc(r.title)}</div>
		<div class="ga-tags">${fitPill(r.fit)}<span class="pill gray">${esc(PRI_SHORT[r.priority] || r.priority || "")}</span>${r.approach ? `<span class="muted small">${esc(r.approach)}</span>` : ""}${r.regulatory ? `<span class="pill violet">Regulatory</span>` : ""}</div>
		${bar(r.stage)}<div class="muted small">${r.needs_you ? `<b class="needs-tag">Needs you</b> · ` : ""}${esc(r.ago)}</div></a>`;

	// ------------------------------------------------------------------ rapid capture
	async function viewCapture() {
		await ensureBoot(true);
		const b = G.boot;
		if (!b.can_capture) { location.hash = "#/gaps"; return; }
		const speech = window.SpeechRecognition || window.webkitSpeechRecognition;
		const a = currentAssessment();
		Q.app.innerHTML = Q.shell(`
			<section class="form cap">
			<div class="cap-top">${assessmentSelect("cass", false)}<button class="btn ghost" id="paste">${ic("doc")} Paste a list</button></div>
			${a ? summaryStrip(a) : `<p class="help">Choose or create the assessment (workshop) you're capturing for. Items are still saved without one.</p>`}
			<div class="cap-card">
				<div class="cap-row"><textarea id="req" rows="2" placeholder="Type a requirement and press Enter…"></textarea>
					${speech ? `<button class="iconbtn mic" id="mic" title="Dictate">${ic("mic")}</button>` : ""}</div>
				<div class="cap-label">Fit <span class="kbd-hint">Alt+1–4</span></div>
				<div class="seg fitseg" id="cfit">${b.fit.map((f, i) => `<button data-v="${esc(f)}" data-k="${i + 1}" class="f-${FIT_CLS[f]} ${G.fit === f ? "on" : ""}">${esc(FIT_SHORT[f])}</button>`).join("")}</div>
				<div class="cap-label">Priority <span class="kbd-hint">Alt+5–8</span></div>
				<div class="seg" id="cpri">${b.priority.map((p, i) => `<button data-v="${esc(p)}" data-k="${i + 5}" class="${G.priority === p ? "on" : ""}">${esc(PRI_SHORT[p])}</button>`).join("")}</div>
				<details id="more"><summary>More details (optional)</summary>
					<label class="lbl">Process / sub-process</label><input id="cproc" placeholder="Dispensing">
					<label class="lbl">How it's done today</label><textarea id="ccur" rows="2"></textarea>
					<label class="lbl">What the system does</label><textarea id="csys" rows="2"></textarea>
					<label class="ga-check"><input type="checkbox" id="creg"> Regulatory / compliance (SHA, MOH, PPB, KRA…)</label>
					<div class="shots small" id="cshots"><div class="drop">${ic("cam")}<span>Screenshot, photo or recording · paste or drop</span></div>${Q.sourceButtons(true)}<div class="thumbs"></div></div>
				</details>
				<button class="btn primary block" id="csave">${ic("check")} Save &amp; next <span class="kbd">Enter</span></button>
				<p class="muted small center">Tip: type tags in the text: <code>#gap</code> <code>#partial</code> <code>#fit</code> · <code>#must</code> <code>#should</code> · <code>#reg</code></p>
			</div>
			<div class="cap-list"><div class="cap-list-h"><h3>Captured now <span class="muted" id="ccount">${G.session.length ? "· " + G.session.length : ""}</span></h3><a class="muted small" href="#/gaps">All gaps</a></div>
				<div id="clist"></div></div>
			</section>`, { back: "#/gaps", title: "Capture gaps", nav: false });
		Q.bindShell();
		const picker = Q.shotPicker($("#cshots"));
		Q.setPicker(picker);
		$("#cass").onchange = (e) => pickAssessment(e.target, () => viewCapture());
		const req = $("#req");
		req.focus();
		const setChip = (id, key, val) => {
			G[key] = val; store.set(key, val);
			Q.app.querySelectorAll(`#${id} [data-v]`).forEach((x) => x.classList.toggle("on", x.dataset.v === val));
		};
		Q.app.querySelectorAll("#cfit [data-v]").forEach((el) => (el.onclick = () => { setChip("cfit", "fit", el.dataset.v); req.focus(); }));
		Q.app.querySelectorAll("#cpri [data-v]").forEach((el) => (el.onclick = () => { setChip("cpri", "priority", el.dataset.v); req.focus(); }));
		req.oninput = () => { req.style.height = "auto"; req.style.height = Math.min(180, req.scrollHeight) + "px"; };
		const save = async () => {
			const title = req.value.trim();
			if (!title) { req.focus(); return; }
			const btn = $("#csave"); btn.disabled = true;
			const values = { fit_status: G.fit, priority: G.priority };
			if ($("#cproc").value.trim()) values.process_name = $("#cproc").value.trim();
			if ($("#ccur").value.trim()) values.current_process = $("#ccur").value.trim();
			if ($("#csys").value.trim()) values.system_behaviour = $("#csys").value.trim();
			if ($("#creg").checked) values.regulatory = 1;
			try {
				await picker.whenReady();
				const row = await call("quick_add", { assessment: G.assessment || null, title, values, images: picker.shots, files: picker.files });
				G.session.unshift(row);
				req.value = ""; req.style.height = "auto";
				["#cproc", "#ccur", "#csys"].forEach((s) => ($(s).value = "")); $("#creg").checked = false; picker.clear();
				renderSession();
				toast(`Saved ${row.code || row.name}`, "ok");
				refreshSummary();
			} catch (e) { toast(e.message, "err"); }
			btn.disabled = false; req.focus();
		};
		$("#csave").onclick = save;
		req.onkeydown = (e) => {
			if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); save(); return; }
			if (e.altKey && /^[1-8]$/.test(e.key)) {
				e.preventDefault();
				const k = +e.key;
				if (k <= 4) setChip("cfit", "fit", b.fit[k - 1]); else setChip("cpri", "priority", b.priority[k - 5]);
			}
		};
		// Alt+digit also works when focus is elsewhere on the page (and on Mac, where Alt+digit types symbols)
		document.onkeydown = (e) => {
			if (!$("#req")) { document.onkeydown = null; return; }
			if (e.altKey && /^Digit[1-8]$/.test(e.code) && document.activeElement !== req) {
				e.preventDefault();
				const k = +e.code.slice(5);
				if (k <= 4) setChip("cfit", "fit", b.fit[k - 1]); else setChip("cpri", "priority", b.priority[k - 5]);
			}
		};
		if (speech && $("#mic")) setupMic(speech, $("#mic"), req);
		$("#paste").onclick = pasteListSheet;
		renderSession();
	}

	function setupMic(SR, btn, target) {
		let rec = null, on = false, base = "";
		btn.onclick = () => {
			if (on) { rec && rec.stop(); return; }
			rec = new SR();
			rec.lang = navigator.language || "en-US";
			rec.interimResults = true; rec.continuous = false;
			base = target.value ? target.value.replace(/\s*$/, " ") : "";
			rec.onresult = (ev) => {
				let txt = "";
				for (let i = 0; i < ev.results.length; i++) txt += ev.results[i][0].transcript;
				target.value = base + txt;
				target.dispatchEvent(new Event("input"));
			};
			rec.onerror = (ev) => { toast(ev.error === "not-allowed" ? "Allow microphone access to dictate" : "Couldn't hear that. Try again.", "err"); };
			rec.onend = () => { on = false; btn.classList.remove("rec"); target.focus(); };
			rec.start(); on = true; btn.classList.add("rec");
			toast("Listening… speak the requirement");
		};
	}

	async function refreshSummary() {
		if (!G.assessment) return;
		try {
			const a = await call("assessment", { name: G.assessment });
			const i = G.boot.assessments.findIndex((x) => x.name === a.name);
			if (i >= 0) G.boot.assessments[i] = a;
			const old = $(".cap .ga-sum");
			if (old) old.replaceWith(h(summaryStrip(a)));
		} catch (e) { /* ignore */ }
	}

	function renderSession() {
		const el = $("#clist");
		if (!el) return;
		$("#ccount").textContent = G.session.length ? "· " + G.session.length : "";
		if (!G.session.length) { el.innerHTML = `<p class="muted small">Items you capture appear here. Tap the Fit or Priority badge to change it.</p>`; return; }
		el.innerHTML = G.session.map((r, i) => `<div class="cap-item fit-${FIT_CLS[r.fit] || "gray"}" data-i="${i}">
			<button class="pill ${FIT_CLS[r.fit] || "gray"} tap" data-cycle="fit" title="Change fit">${esc(FIT_SHORT[r.fit])}</button>
			<button class="pill gray tap" data-cycle="priority" title="Change priority">${esc(PRI_SHORT[r.priority] || "")}</button>
			<a class="cap-t" href="#/gap/${encodeURIComponent(r.name)}">${esc(r.title)}<span class="muted small"> · ${esc(r.code || r.name)}</span></a>
			<button class="iconbtn sm" data-del title="Remove">${ic("trash")}</button></div>`).join("");
		el.querySelectorAll(".cap-item").forEach((row) => {
			const r = G.session[+row.dataset.i];
			row.querySelectorAll("[data-cycle]").forEach((b) => (b.onclick = async () => {
				const key = b.dataset.cycle;
				const list = key === "fit" ? G.boot.fit : G.boot.priority;
				const cur = key === "fit" ? r.fit : r.priority;
				const next = list[(list.indexOf(cur) + 1) % list.length];
				try {
					await call("set_fields", { name: r.name, values: key === "fit" ? { fit_status: next } : { priority: next } });
					if (key === "fit") r.fit = next; else r.priority = next;
					renderSession(); refreshSummary();
				} catch (e) { toast(e.message, "err"); }
			}));
			row.querySelector("[data-del]").onclick = async () => {
				if (!confirmInline(row)) return;
				try { await call("remove", { name: r.name }); G.session.splice(+row.dataset.i, 1); renderSession(); refreshSummary(); toast("Removed"); }
				catch (e) { toast(e.message, "err"); }
			};
		});
	}

	function confirmInline(row) {
		if (row.dataset.confirm) return true;
		row.dataset.confirm = "1";
		const b = row.querySelector("[data-del]");
		b.classList.add("warn"); b.title = "Tap again to remove";
		toast("Tap the bin again to remove");
		setTimeout(() => { delete row.dataset.confirm; b.classList.remove("warn"); }, 3000);
		return false;
	}

	function pasteListSheet() {
		const b = G.boot;
		const m = h(`<div class="modal sheet"><div class="sheet-box">
			<div class="sheet-head"><h3>Paste a list</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			<p class="muted small">One requirement per line, from Excel, Word or notes. Bullets and numbers are removed. Tags per line override the defaults: <code>#gap</code> <code>#partial</code> <code>#fit</code> <code>#na</code> · <code>#must</code> <code>#should</code> <code>#could</code> <code>#wont</code> · <code>#reg</code></p>
			<textarea id="pl" rows="9" placeholder="1. Dispense against prescription #fit&#10;2. Controlled drugs register report #must #reg&#10;3. Pharmacy token queue per branch #partial"></textarea>
			<div class="muted small" id="plc">0 items</div>
			<label class="lbl">Default fit</label><div class="seg fitseg" id="pfit">${b.fit.map((f) => `<button data-v="${esc(f)}" class="f-${FIT_CLS[f]} ${f === G.fit ? "on" : ""}">${esc(FIT_SHORT[f])}</button>`).join("")}</div>
			<label class="lbl">Default priority</label><div class="seg" id="ppri">${b.priority.map((p) => `<button data-v="${esc(p)}" class="${p === G.priority ? "on" : ""}">${esc(PRI_SHORT[p])}</button>`).join("")}</div>
			<button class="btn primary block" data-go>Add all</button></div></div>`);
		document.body.appendChild(m);
		let fit = G.fit, pri = G.priority;
		const seg = (id, set) => m.querySelectorAll(`#${id} [data-v]`).forEach((el) => (el.onclick = () => { set(el.dataset.v); m.querySelectorAll(`#${id} [data-v]`).forEach((x) => x.classList.toggle("on", x === el)); }));
		seg("pfit", (v) => (fit = v)); seg("ppri", (v) => (pri = v));
		const ta = $("#pl", m);
		ta.oninput = () => { const n = ta.value.split("\n").filter((l) => l.trim()).length; $("#plc", m).textContent = `${n} item${n === 1 ? "" : "s"}`; };
		ta.focus();
		$("[data-x]", m).onclick = () => m.remove();
		$("[data-go]", m).onclick = async (e) => {
			if (!ta.value.trim()) { ta.focus(); return; }
			e.currentTarget.disabled = true;
			try {
				const rows = await call("bulk_add", { assessment: G.assessment || null, text: ta.value, fit_status: fit, priority: pri });
				G.session = rows.concat(G.session);
				m.remove(); renderSession(); refreshSummary();
				toast(`${rows.length} items added`, "ok");
			} catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
		};
	}

	// ------------------------------------------------------------------ gap detail
	async function viewGap(name) {
		Q.app.innerHTML = Q.shell(`<div class="skel tall"></div>`, { back: "#/gaps", title: esc(name), nav: false });
		Q.bindShell();
		await ensureBoot();
		renderGap(await call("gap", { name }));
	}

	function renderGap(g) {
		const b = G.boot, v = g.values;
		const sel = (id, list, cur, labels) => `<select id="${id}"><option value="">-</option>${list.map((o) => {
			const val = typeof o === "object" ? o.value : o, lab = typeof o === "object" ? o.label : (labels ? labels[o] || o : o);
			return `<option value="${esc(val)}" ${val === cur ? "selected" : ""}>${esc(lab)}</option>`; }).join("")}</select>`;
		const isVid = (u) => /\.(webm|mp4|mov|m4v)(\?|$)/i.test(u || "");
		const isImg = (u) => /\.(png|jpe?g|gif|webp|bmp)(\?|$)/i.test(u || "");
		const gal = (arr, label) => arr.length ? `<div class="gal-l">${label}</div><div class="gal">${arr.filter(isImg).map((s) => `<img src="${esc(s)}" data-lb="${esc(s)}" alt="" loading="lazy">`).join("")}</div>
			${arr.some(isVid) ? `<div class="vids">${arr.filter(isVid).map((v) => `<figure><video src="${esc(v)}" controls preload="metadata" playsinline></video></figure>`).join("")}</div>` : ""}
			${arr.some((u) => !isImg(u) && !isVid(u)) ? `<div class="doc-list">${arr.filter((u) => !isImg(u) && !isVid(u)).map((u) => { const n = u.split("/").pop(); return `<a class="doc-chip" href="${esc(u)}" target="_blank" rel="noopener"><span class="doc-ic k-${Q.docKind(n).toLowerCase()}">${esc(Q.docKind(n))}</span><span class="doc-name">${esc(n)}</span></a>`; }).join("")}</div>` : ""}` : "";
		const resForm = g.can_edit ? `
			<div class="ga-form">
				<label class="lbl">Resolution approach</label><div class="chips wrap" id="gap_appr">${b.approaches.map((x) => `<button class="chip ${v.resolution_approach === x ? "on" : ""}" data-v="${esc(x)}">${esc(x)}</button>`).join("")}</div>
				<label class="lbl">Proposed solution</label><textarea id="g_sol" rows="2">${esc(v.proposed_solution || "")}</textarea>
				<label class="lbl">Interim workaround</label><textarea id="g_wa" rows="2">${esc(v.workaround || "")}</textarea>
				<div class="ga-grid">
					<div><label class="lbl">Business owner</label>${sel("g_owner", b.approvers, v.business_owner)}</div>
					<div><label class="lbl">Delivered by</label>${sel("g_dev", b.developers, v.assigned_to)}</div>
					<div><label class="lbl">Effort (days)</label><input id="g_eff" type="number" min="0" step="0.5" value="${esc(v.effort_days || "")}"></div>
					<div><label class="lbl">Target release</label><input id="g_rel" value="${esc(v.target_release || "")}"></div>
				</div>
				<button class="btn secondary block" id="g_save">Save details</button>
			</div>` : `
			<div class="kvs">${[["Approach", v.resolution_approach], ["Proposed", v.proposed_solution], ["Workaround", v.workaround], ["Business owner", g.owner_name],
				["Delivered by", g.assignee_name], ["Effort", v.effort_days ? v.effort_days + " days" : null], ["Release", v.target_release]]
				.filter((x) => x[1]).map((x) => `<div class="kv"><span>${x[0]}</span><b>${esc(x[1])}</b></div>`).join("") || `<p class="muted small">No resolution yet.</p>`}</div>`;
		Q.app.innerHTML = Q.shell(`
			<section class="tkt">
				<div class="tkt-head"><span class="muted">${esc(g.code || g.name)}${g.module ? " · " + esc(g.module) : ""}</span>${pill(g.status)}</div>
				<h1 ${g.can_edit ? 'contenteditable="true" id="g_title" class="editable" title="Tap to edit"' : ""}>${esc(g.title)}</h1>
				${g.merged_into ? `<a class="mergedban" href="#/gap/${encodeURIComponent(g.merged_into)}">${ic("merge")}<span>This gap was a duplicate and was merged into <b>${esc(g.merged_into)}</b>.</span>${ic("arrow")}</a>` : ""}
				${(g.similar || []).length ? `<div class="dupban">${ic("merge")}<span>Possible duplicate${g.similar.length > 1 ? "s" : ""}: ${g.similar.map((x) => `<a href="#/gap/${encodeURIComponent(x.name)}" title="${esc(x.title)}">${esc(x.name)}</a>`).join(", ")}</span><button class="btn ghost sm" data-merge>Review & merge</button></div>` : ""}
				${(g.merged_from || []).length ? `<div class="muted small">Includes merged ${g.merged_from.map((x) => `<a href="#/gap/${encodeURIComponent(x.name)}" title="${esc(x.title)}">${esc(x.name)}</a>`).join(", ")}</div>` : ""}
				<div class="muted small">${g.assessment ? esc(g.assessment) + " · " : ""}${g.raised ? "raised by " + esc(g.raised) : ""}</div>
				<div class="stagebox">${bar(g.stage, true)}</div>
				<div class="cap-label">Fit</div>
				<div class="seg fitseg ${g.can_edit ? "" : "ro"}" id="g_fit">${b.fit.map((f) => `<button data-v="${esc(f)}" class="f-${FIT_CLS[f]} ${v.fit_status === f ? "on" : ""}">${esc(FIT_SHORT[f])}</button>`).join("")}</div>
				<div class="cap-label">Priority</div>
				<div class="seg ${g.can_edit ? "" : "ro"}" id="g_pri">${b.priority.map((p) => `<button data-v="${esc(p)}" class="${v.priority === p ? "on" : ""}">${esc(PRI_SHORT[p])}</button>`).join("")}</div>
				${g.actions.length ? `<div class="actions">${g.actions.map((a, i) => `<button class="btn ${a.style}" data-a="${i}">${a.style === "success" ? ic("check") : a.style === "danger" ? ic("x") : ""}${esc(a.label)}</button>`).join("")}</div>` : ""}
				${g.decision && g.decision !== "Pending" ? `<div class="note"><div class="muted small">Decision: ${esc(g.decision)}</div>${esc(g.decision_notes || "")}</div>` : ""}
				${g.delivery_notes ? `<div class="note"><div class="muted small">Delivered${g.delivered_in_build ? " in " + esc(g.delivered_in_build) : ""}</div>${esc(g.delivery_notes)}</div>` : ""}
				${v.requirement ? `<div class="desc">${v.requirement}</div>` : ""}
				${v.current_process ? `<div class="kv"><span>Today</span><b>${esc(v.current_process)}</b></div>` : ""}
				${v.system_behaviour ? `<div class="kv"><span>System</span><b>${esc(v.system_behaviour)}</b></div>` : ""}
				<h3 class="sec">Resolution</h3>${resForm}
				${gal(g.evidence, "Evidence")}${gal(g.verification_evidence, "Verification evidence")}
				${g.issues.length ? `<div class="gal-l">Related QA tickets</div>${g.issues.map((x) => `<a class="link-row" href="#/t/${encodeURIComponent(x.name)}">${esc(x.name)} · ${esc(x.title || "")} <span class="muted">${esc(x.status || "")}</span></a>`).join("")}` : ""}
				${g.tests.length ? `<div class="gal-l">Verification test cases</div>${g.tests.map((x) => `<div class="link-row">${esc(x.name)} · ${esc(x.title || "")}</div>`).join("")}` : ""}
			</section>
			<section class="timeline"><h3>Updates</h3>
				${g.timeline.length ? g.timeline.map((u) => u.type === "Status Change" ? `<div class="sys">${esc(u.text)} · ${esc(u.ago)}</div>` :
					`<div class="bubble ${u.mine ? "mine" : ""}"><div class="b-head"><b>${esc(u.by)}</b><span>${esc(u.type)} · ${esc(u.ago)}</span></div>
					<div class="b-text">${esc(u.text)}</div>${u.file && /\.(png|jpe?g|gif|webp)$/i.test(u.file) ? `<img src="${esc(u.file)}" data-lb="${esc(u.file)}" alt="">` : u.file && /\.(webm|mp4|mov|m4v)$/i.test(u.file) ? `<video class="b-vid" src="${esc(u.file)}" controls preload="metadata" playsinline></video>` : u.file ? `<a class="doc-chip in-bubble" href="${esc(u.file)}" target="_blank" rel="noopener"><span class="doc-ic k-${Q.docKind(u.file).toLowerCase()}">${esc(Q.docKind(u.file))}</span><span class="doc-name">${esc(u.file.split("/").pop())}</span></a>` : ""}</div>`).join("")
					: `<p class="muted">No updates yet.</p>`}
			</section>
			<div class="composer" id="gcomp"><div class="thumbs"></div><div class="c-row">
				<button class="iconbtn" id="gatt" aria-label="Attach">${ic("clip")}</button>
				${Q.canRecordScreen ? `<button class="iconbtn rec-ic" id="grec" aria-label="Record screen" title="Record screen">${ic("rec")}</button>` : ""}
				<textarea id="gmsg" rows="1" placeholder="Add an update…"></textarea>
				<button class="iconbtn send" id="gsend" aria-label="Send">${ic("send")}</button></div></div>
			${g.can_merge ? `<p class="center"><button class="btn ghost sm" data-merge>${ic("merge")} Merge duplicates…</button></p>` : ""}
			${Q.state.boot.desk ? `<p class="center"><a class="muted small" href="${esc(g.desk_url)}">Open in Desk</a></p>` : ""}`,
			{ back: "#/gaps", title: esc(g.code || g.name), nav: false });
		Q.bindShell();
		Q.app.querySelectorAll("[data-lb]").forEach((im) => (im.onclick = () => Q.lightbox(im.dataset.lb)));
		Q.app.querySelectorAll("[data-merge]").forEach((btn) => (btn.onclick = () => Q.mergeSheet({
			kind: "gap", name: g.name, title: g.title,
			candidates: (txt) => call("merge_candidates", { name: g.name, txt: txt || null }),
			merge: (target, sources) => call("merge", { target, sources }),
			open: (n) => { location.hash = "#/gap/" + encodeURIComponent(n); viewGap(n); },
		})));
		const quickSet = async (values) => {
			try { renderGap(await call("set_fields", { name: g.name, values })); toast("Saved", "ok"); } catch (e) { toast(e.message, "err"); }
		};
		if (g.can_edit) {
			Q.app.querySelectorAll("#g_fit [data-v]").forEach((el) => (el.onclick = () => quickSet({ fit_status: el.dataset.v })));
			Q.app.querySelectorAll("#g_pri [data-v]").forEach((el) => (el.onclick = () => quickSet({ priority: el.dataset.v })));
			const t = $("#g_title");
			t.onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); t.blur(); } };
			t.onblur = () => { const val = t.textContent.trim(); if (val && val !== g.title) quickSet({ title: val }); };
			let approach = v.resolution_approach;
			Q.app.querySelectorAll("#gap_appr [data-v]").forEach((el) => (el.onclick = () => {
				approach = el.dataset.v; Q.app.querySelectorAll("#gap_appr [data-v]").forEach((x) => x.classList.toggle("on", x === el));
			}));
			$("#g_save").onclick = () => quickSet({ resolution_approach: approach, proposed_solution: $("#g_sol").value, workaround: $("#g_wa").value,
				business_owner: $("#g_owner").value || null, assigned_to: $("#g_dev").value || null, effort_days: $("#g_eff").value, target_release: $("#g_rel").value });
		}
		Q.app.querySelectorAll("[data-a]").forEach((btn) => (btn.onclick = () => gapAction(g, g.actions[+btn.dataset.a])));
		const picker = Q.shotPicker($("#gcomp"));
		Q.setPicker(picker);
		$("#gatt").onclick = () => picker.pick();
		if ($("#grec")) $("#grec").onclick = () => picker.record();
		const msg = $("#gmsg");
		msg.oninput = () => { msg.style.height = "auto"; msg.style.height = Math.min(140, msg.scrollHeight) + "px"; };
		$("#gsend").onclick = async (e) => {
			if (!msg.value.trim() && !picker.shots.length && !picker.files.length && !picker.uploading) { msg.focus(); return; }
			e.currentTarget.disabled = true;
			try { await picker.whenReady(); renderGap(await call("update", { name: g.name, text: msg.value, images: picker.shots, files: picker.files })); toast("Update posted", "ok"); }
			catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
		};
	}

	function gapAction(g, a) {
		const run = async (vals, btn) => {
			if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner sm"></span>'; }
			try {
				const ng = await call("act", Object.assign({ name: g.name, action: a.action }, vals || {}));
				toast(`${a.label}: done`, "ok");
				G.boot = null; await ensureBoot(); Q.refreshBoot && Q.refreshBoot().catch(() => {});
				renderGap(ng); return true;
			} catch (err) {
				toast(err.message, "err");
				if (btn) { btn.disabled = false; btn.textContent = a.label; }
				return false;
			}
		};
		if (a.action === "Submit for Approval" && (!g.values.resolution_approach || !g.values.business_owner)) {
			toast("Choose the resolution approach and business owner, then Save details", "err");
			const f = $(".ga-form"); if (f) f.scrollIntoView({ behavior: "smooth" });
			return;
		}
		if (!(a.notes || a.build || a.shots)) return run({});
		const m = h(`<div class="modal sheet"><div class="sheet-box">
			<div class="sheet-head"><h3>${esc(a.label)}</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			${a.notes ? `<label class="lbl">${esc(a.notes)}</label><textarea id="gan" rows="3"></textarea>` : ""}
			${a.build ? `<label class="lbl">Build / release</label><input id="gab" value="${esc(g.delivered_in_build || g.values.target_release || "")}">` : ""}
			${a.shots ? `<div class="shots small" id="gash"><div class="drop">${ic("cam")}<span>Evidence (optional) · paste or drop</span></div>${Q.sourceButtons(true)}<div class="thumbs"></div></div>` : ""}
			<button class="btn ${a.style} block" data-go>${esc(a.label)}</button></div></div>`);
		document.body.appendChild(m);
		const prev = Q.state.picker;
		const pk = a.shots ? Q.shotPicker($("#gash", m)) : null;
		const close = () => { if (pk) pk.destroy(); m.remove(); };
		$("[data-x]", m).onclick = close;
		m.onclick = (e) => { if (e.target === m) close(); };
		if ($("#gan", m)) $("#gan", m).focus();
		$("[data-go]", m).onclick = async (e) => {
			const notes = $("#gan", m) ? $("#gan", m).value.trim() : null;
			if (a.notes_required && !notes) { toast("Please add a note", "err"); $("#gan", m).focus(); return; }
			if (pk) await pk.whenReady();
			const ok = await run({ notes, build: $("#gab", m) ? $("#gab", m).value.trim() : null, images: pk ? pk.shots : [], files: pk ? pk.files : [] }, e.currentTarget);
			if (ok) close(); else Q.state.picker = prev;
		};
	}

	Q.routes.gaps = viewGaps;
	Q.routes.gap = viewGap;
})();
