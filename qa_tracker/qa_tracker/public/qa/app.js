/* QA Tracker portal - plain JS, no build step (works on Frappe v14 - v17). */
(function () {
	"use strict";

	// ------------------------------------------------------------------ utils
	const $ = (sel, el) => (el || document).querySelector(sel);
	const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
	const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
	const STAGES = ["Logged", "Developer", "Retest", "Confirmed", "UAT", "Done"];
	const ICON = {
		plus: '<path d="M12 5v14M5 12h14"/>',
		back: '<path d="M15 6l-6 6 6 6"/>',
		cam: '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
		clip: '<path d="M15 7l-6.5 6.5a2 2 0 0 0 2.8 2.8L18 9.6a4 4 0 0 0-5.7-5.7L5.6 10.6a6 6 0 0 0 8.5 8.5L20 13"/>',
		send: '<path d="M4 12l16-8-6 16-2.5-6.5z"/>',
		edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
		x: '<path d="M6 6l12 12M18 6L6 18"/>',
		list: '<path d="M9 6h11M9 12h11M9 18h11M4 6h1M4 12h1M4 18h1"/>',
		play: '<path d="M7 5l12 7-12 7z"/>',
		search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
		undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
		pen: '<path d="M4 20c4-1 6-3 8-6s4-7 8-10"/>',
		arrow: '<path d="M5 19L19 5M10 5h9v9"/>',
		box: '<rect x="4" y="6" width="16" height="12" rx="1"/>',
		blur: '<path d="M4 4h4v4H4zM10 4h4v4h-4zM16 4h4v4h-4zM4 10h4v4H4zM16 10h4v4h-4zM4 16h4v4H4zM10 16h4v4h-4zM16 16h4v4h-4z"/>',
		check: '<path d="M5 12l5 5 9-10"/>',
		desk: '<rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
		out: '<path d="M14 4h5v16h-5M10 8l-4 4 4 4M6 12h11"/>',
		refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>',
		rec: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5" fill="currentColor"/>',
		video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3z"/>',
		stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
		grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><path d="M14 16.5h6M17 13.5v6"/>',
		external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
		down: '<path d="m6 9 6 6 6-6"/>',
		users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18.5 14.8c1.7.7 2.8 2.5 3 5.2"/>',
		merge: '<path d="M6 3v6a6 6 0 0 0 6 6h6"/><path d="m15 12 3 3-3 3"/><path d="M6 21v-6"/><circle cx="6" cy="3" r="0.5"/>',
		chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
		up: '<path d="m6 15 6-6 6 6"/>',
		timer: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9.5 3h5"/>',
		mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
		bolt: '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
		trash: '<path d="M5 7h14M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
		doc: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>',
	};
	const ic = (n, cls) => `<svg class="ic ${cls || ""}" viewBox="0 0 24 24" aria-hidden="true">${ICON[n] || ""}</svg>`;

	async function api(method, args) {
		const res = await fetch("/api/method/qa_tracker.portal." + method, {
			method: "POST",
			headers: { "Content-Type": "application/json", "X-Frappe-CSRF-Token": window.QA_CSRF, Accept: "application/json" },
			body: JSON.stringify(Object.assign(state.project ? { project: state.project } : {}, args || {})),
			credentials: "same-origin",
		});
		let data = {};
		try { data = await res.json(); } catch (e) { /* ignore */ }
		if (!res.ok || data.exc || data.exception) {
			let msg = "Something went wrong. Try again.";
			try {
				const sm = JSON.parse(data._server_messages || "[]");
				if (sm.length) msg = JSON.parse(sm[0]).message || msg;
			} catch (e) { /* ignore */ }
			if (res.status === 403 && msg.startsWith("Something")) msg = "You don't have permission for that.";
			if (res.status === 401 || /login/i.test(msg)) { location.href = "/login?redirect-to=/qa"; }
			throw new Error(msg.replace(/<[^>]+>/g, ""));
		}
		return data.message;
	}

	function toast(msg, kind) {
		document.querySelectorAll(".toast").forEach((x) => x.remove());
		const t = h(`<div class="toast ${kind || ""}">${esc(msg)}</div>`);
		document.body.appendChild(t);
		setTimeout(() => t.classList.add("show"), 10);
		setTimeout(() => { t.classList.remove("show"); setTimeout(() => t.remove(), 300); }, 3200);
	}

	const stagePill = (status) => {
		const map = {
			"New": "blue", "Triaged": "blue", "Assigned": "violet", "In Progress": "violet", "Reopened": "red",
			"Ready for Retest": "amber", "Answered": "amber", "Retest Passed": "teal", "Confirmed": "teal",
			"In UAT": "violet", "UAT Accepted": "green", "Closed": "green", "Deferred": "gray", "Rejected": "gray",
		};
		return `<span class="pill ${map[status] || "gray"}">${esc(status)}</span>`;
	};
	const stageBar = (i, labels) => `<div class="stages">${STAGES.map((s, k) =>
		`<div class="st ${k < i ? "done" : k === i ? "cur" : ""}"><span></span>${labels ? `<em>${s}</em>` : ""}</div>`).join("")}</div>`;
	const sevDot = (s) => `<span class="sev sev-${(s || "medium").toLowerCase()}" title="${esc(s)}"></span>`;

	// ------------------------------------------------------------------ images
	function readImage(file) {
		return new Promise((resolve, reject) => {
			if (!file || !/^image\//.test(file.type)) return reject(new Error("Only images can be attached"));
			const fr = new FileReader();
			fr.onload = () => {
				const img = new Image();
				img.onload = () => {
					const max = 2000;
					let { width: w, height: hh } = img;
					const big = file.size > 1.5 * 1024 * 1024 || w > max || hh > max;
					if (!big) return resolve({ name: file.name || "screenshot.png", data: fr.result });
					const k = Math.min(1, max / Math.max(w, hh));
					const c = document.createElement("canvas");
					c.width = Math.round(w * k); c.height = Math.round(hh * k);
					c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
					resolve({ name: (file.name || "screenshot").replace(/\.\w+$/, "") + ".jpg", data: c.toDataURL("image/jpeg", 0.85) });
				};
				img.onerror = () => reject(new Error("Could not read image"));
				img.src = fr.result;
			};
			fr.readAsDataURL(file);
		});
	}

	// Shot list widget: thumbnails + add (file/camera/capture/record) + paste + annotate.
	// Images are sent inline as data URLs; videos are uploaded first and sent as file URLs.
	const isVideoFile = (f) => /^video\//.test(f.type || "") || /\.(webm|mp4|mov|m4v|mkv)$/i.test(f.name || "");
	const DOC_RE = /\.(pdf|xlsx|xls|xlsm|csv|ods|docx|doc|odt|rtf|txt|pptx|ppt|zip|log|json|xml|har)$/i;
	const isDocFile = (f) => DOC_RE.test(f.name || "");
	const docKind = (name) => /\.pdf$/i.test(name) ? "PDF" : /\.(xlsx|xls|xlsm|csv|ods)$/i.test(name) ? "Excel" : /\.(docx|doc|odt|rtf)$/i.test(name) ? "Word" : /\.(pptx|ppt)$/i.test(name) ? "Slides" : "File";
	const ACCEPT = "image/*,video/*,.pdf,.xlsx,.xls,.xlsm,.csv,.ods,.docx,.doc,.odt,.rtf,.txt,.pptx,.ppt,.zip,.log,.json,.xml,.har";
	const fmtDur = (sec) => { sec = Math.max(0, Math.round(sec || 0)); return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0"); };
	const fmtMB = (b) => (b / 1048576).toFixed(b < 10485760 ? 1 : 0) + " MB";

	function uploadFile(blob, name, onProgress) {
		return new Promise((resolve, reject) => {
			const max = (state.boot && state.boot.max_upload) || 10 * 1048576;
			if (blob.size > max) return reject(new Error(`This recording is ${fmtMB(blob.size)}; the site allows up to ${fmtMB(max)}. Record a shorter clip.`));
			const fd = new FormData();
			fd.append("file", blob, name);
			fd.append("is_private", "1");
			fd.append("folder", "Home/Attachments");
			const xhr = new XMLHttpRequest();
			xhr.open("POST", "/api/method/upload_file");
			xhr.setRequestHeader("X-Frappe-CSRF-Token", window.QA_CSRF);
			xhr.setRequestHeader("Accept", "application/json");
			xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(Math.round((100 * e.loaded) / e.total)); };
			xhr.onload = () => {
				let data = {};
				try { data = JSON.parse(xhr.responseText); } catch (e) { /* ignore */ }
				if (xhr.status >= 200 && xhr.status < 300 && data.message && data.message.file_url) return resolve(data.message.file_url);
				let msg = "Upload failed.";
				try { const sm = JSON.parse(data._server_messages || "[]"); if (sm.length) msg = JSON.parse(sm[0]).message || msg; } catch (e) { /* ignore */ }
				if (xhr.status === 413) msg = "The recording is too large for the server. Record a shorter clip.";
				reject(new Error(String(msg).replace(/<[^>]+>/g, "")));
			};
			xhr.onerror = () => reject(new Error("Upload failed - check your connection."));
			xhr.send(fd);
		});
	}

	function videoDuration(url) {
		return new Promise((resolve) => {
			const v = document.createElement("video");
			v.preload = "metadata";
			v.onloadedmetadata = () => {
				if (v.duration === Infinity) { // webm from MediaRecorder: seek to get the real length
					v.currentTime = 1e7;
					v.ontimeupdate = () => { v.ontimeupdate = null; resolve(v.duration); };
				} else resolve(v.duration);
			};
			v.onerror = () => resolve(0);
			v.src = url;
		});
	}

	function shotPicker(container, opts) {
		const shots = [];
		const videos = [];   // {url, duration, preview, name, progress, error}
		const input = h(`<input type="file" accept="${ACCEPT}" multiple hidden>`);
		const camera = h('<input type="file" accept="image/*" capture="environment" hidden>');
		const camvideo = h('<input type="file" accept="video/*" capture="environment" hidden>');
		container.appendChild(input); container.appendChild(camera); container.appendChild(camvideo);
		const render = () => {
			const grid = $(".thumbs", container);
			grid.innerHTML = "";
			shots.forEach((s, i) => {
				const t = h(`<div class="thumb"><img src="${s.data}" alt=""><button class="t-edit" title="Mark up">${ic("edit")}</button><button class="t-del" title="Remove">${ic("x")}</button></div>`);
				$(".t-del", t).onclick = (e) => { e.stopPropagation(); shots.splice(i, 1); render(); };
				$(".t-edit", t).onclick = (e) => { e.stopPropagation(); annotate(s.data).then((d) => { if (d) { s.data = d; s.name = s.name.replace(/\.\w+$/, "") + ".png"; render(); } }); };
				$("img", t).onclick = () => annotate(s.data).then((d) => { if (d) { s.data = d; render(); } });
				grid.appendChild(t);
			});
			videos.forEach((v, i) => {
				if (v.doc) {
					const t = h(`<div class="doc-chip ${v.url ? "" : "busy"}"><span class="doc-ic k-${docKind(v.name).toLowerCase()}">${esc(docKind(v.name))}</span>
						<span class="doc-name">${esc(v.name)}<em>${v.url ? fmtMB(v.size) : (v.progress || 0) + "%"}</em></span>
						<button class="t-del" title="Remove">${ic("x")}</button></div>`);
					$(".t-del", t).onclick = (e) => { e.stopPropagation(); videos.splice(i, 1); render(); };
					grid.appendChild(t);
					return;
				}
				const t = h(`<div class="thumb vid ${v.url ? "" : "busy"}"><video src="${esc(v.preview)}" muted preload="metadata" playsinline></video>
					<span class="vid-badge">${v.url ? ic("play") + fmtDur(v.duration) : v.error ? "Failed" : (v.progress || 0) + "%"}</span>
					<button class="t-del" title="Remove">${ic("x")}</button></div>`);
				$(".t-del", t).onclick = (e) => { e.stopPropagation(); videos.splice(i, 1); render(); };
				$("video", t).onclick = () => lightbox(v.preview, true);
				grid.appendChild(t);
			});
			container.classList.toggle("has-shots", shots.length + videos.length > 0);
			if (opts && opts.onChange) opts.onChange(shots);
		};
		const addVideo = async (blob, name, duration, isDoc) => {
			const preview = isDoc ? null : URL.createObjectURL(blob);
			const v = { preview, name, duration: duration || 0, progress: 0, url: null, doc: !!isDoc, size: blob.size };
			videos.push(v); render();
			if (!isDoc && !v.duration) { v.duration = await videoDuration(preview); }
			try {
				v.url = await uploadFile(blob, name, (p) => { v.progress = p; render(); });
				toast(v.doc ? `${name} attached` : "Recording attached", "ok");
			} catch (e) {
				v.error = e.message; toast(e.message, "err");
				videos.splice(videos.indexOf(v), 1);
			}
			render();
		};
		const add = async (files) => {
			for (const f of files) {
				if (isVideoFile(f)) { addVideo(f, f.name || "recording.mp4"); continue; }
				if (isDocFile(f)) { addVideo(f, f.name, 0, true); continue; }
				if (!/^image\//.test(f.type || "")) { toast(`${f.name}: this file type can't be attached`, "err"); continue; }
				try { shots.push(await readImage(f)); } catch (e) { toast(e.message, "err"); }
			}
			render();
		};
		input.onchange = () => { add(Array.from(input.files)); input.value = ""; };
		camera.onchange = () => { add(Array.from(camera.files)); camera.value = ""; };
		camvideo.onchange = () => { add(Array.from(camvideo.files)); camvideo.value = ""; };
		const doCamera = () => {
			if (isTouch || !canWebcam) { camera.click(); return; }
			cameraPhoto().then((shot) => { if (shot) { shots.push(shot); render(); } }).catch((err) => toast(err.message, "err"));
		};
		const takeToolbox = (tb) => {
			tb.shots.forEach((x) => shots.push(x));
			tb.recs.forEach((r) => addVideo(r.blob, r.name, r.duration));
			render();
			if (tb.shots.length) toast(`${tb.shots.length} screenshot${tb.shots.length > 1 ? "s" : ""} added - click one to mark up or blur`, "ok");
		};
		const doScreen = async () => {
			try {
				if (canFloat) {
					const display = await getShare(10);
					if (!display) return;
					const tb = await floatingToolbox("snap", {}, display);
					if (!tb.fallback) return takeToolbox(tb);
					// pop-up blocked (no recent click): show the capture panel with a "Pop out toolbox" button
					const r = await captureScreen(display);
					if (r && r.float) { const t2 = await r.float; if (!t2.fallback) takeToolbox(t2); else display.getTracks().forEach((t) => t.stop()); return; }
					if (r) { shots.push(r); render(); }
					return;
				}
				const shot = await captureScreen();
				if (shot) { shots.push(shot); render(); }
			} catch (err) { toast(err.message, "err"); }
		};
		const doRecord = () => recordScreen().then((r) => {
			if (!r) return;
			if (r.toolbox) takeToolbox(r.toolbox); else addVideo(r.blob, r.name, r.duration);
		}).catch((err) => toast(err.message, "err"));
		container.querySelectorAll("[data-src]").forEach((b) => (b.onclick = (e) => {
			e.stopPropagation();
			const src = b.dataset.src;
			if (src === "camera") doCamera();
			else if (src === "camvideo") camvideo.click();
			else if (src === "screen") doScreen();
			else if (src === "record") doRecord();
			else input.click();
		}));
		const drop = $(".drop", container);
		if (drop) {
			drop.onclick = () => input.click();
			drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
			drop.ondragleave = () => drop.classList.remove("over");
			drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove("over"); add(Array.from(e.dataTransfer.files)); };
		}
		const pasteHandler = (e) => {
			const items = Array.from((e.clipboardData || {}).items || []).filter((it) => it.type.startsWith("image/"));
			if (!items.length) return;
			e.preventDefault();
			add(items.map((it) => { const f = it.getAsFile(); return new File([f], "pasted-" + Date.now() + ".png", { type: f.type }); }));
			toast("Screenshot pasted");
		};
		document.addEventListener("paste", pasteHandler);
		render();
		return {
			shots,
			get files() { return videos.filter((v) => v.url).map((v) => ({ url: v.url, name: v.name, duration: v.doc ? "" : fmtDur(v.duration) })); },
			get videos() { return this.files; },
			get uploading() { return videos.some((v) => !v.url && !v.error); },
			async whenReady() {
				if (!videos.some((v) => !v.url && !v.error)) return;
				toast("Waiting for the recording to finish uploading…");
				while (videos.some((v) => !v.url && !v.error)) await new Promise((r) => setTimeout(r, 300));
			},
			pick: () => input.click(),
			camera: doCamera,
			screen: doScreen,
			record: doRecord,
			clear: () => { shots.length = 0; videos.length = 0; render(); },
			destroy: () => document.removeEventListener("paste", pasteHandler),
		};
	}

	// Screen capture / recording need getDisplayMedia (desktop Chrome, Edge, Firefox)
	const canCaptureScreen = !!(navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) && !/Android|iPhone|iPad/i.test(navigator.userAgent);

	// Mark this tab so we can tell when someone shares the QA Tracker tab itself (Chrome).
	const SELF_HANDLE = "qa-tracker-" + Math.random().toString(36).slice(2);
	try {
		if (navigator.mediaDevices && navigator.mediaDevices.setCaptureHandleConfig)
			navigator.mediaDevices.setCaptureHandleConfig({ handle: SELF_HANDLE, exposeOrigin: true, permittedOrigins: [location.origin] });
	} catch (e) { /* not supported */ }

	// Screen capture panel: share a tab / window / screen, see a live preview, then
	// "Capture now" (for a tab or another window) or "Capture in 5 s" (time to switch to MedX).
	async function getShare(fps) {
		try {
			return await navigator.mediaDevices.getDisplayMedia({
				video: { displaySurface: "browser", frameRate: fps || 5 },
				audio: false,
				preferCurrentTab: false,
				selfBrowserSurface: "exclude",   // don't offer the QA Tracker tab itself
				surfaceSwitching: "include",     // lets you switch the shared tab from Chrome's sharing bar
				monitorTypeSurfaces: "include",
			});
		} catch (e) { return null; } // cancelled or blocked
	}
	async function captureScreen(existing) {
		if (!canCaptureScreen) throw new Error("Screen capture isn't available here. Use your snipping tool and paste (Ctrl+V).");
		const stream = existing || await getShare(5);
		if (!stream) return null;
		const track = stream.getVideoTracks()[0];
		const surface = (track.getSettings && track.getSettings().displaySurface) || "";
		const video = document.createElement("video");
		video.srcObject = stream; video.muted = true; video.playsInline = true;
		const stop = () => stream.getTracks().forEach((t) => t.stop());
		const oldTitle = document.title;

		const isSelf = () => {
			try { const ch = track.getCaptureHandle && track.getCaptureHandle(); return !!(ch && ch.handle === SELF_HANDLE); } catch (e) { return false; }
		};
		const tipText = () => {
			const sf = (track.getSettings && track.getSettings().displaySurface) || surface;
			if (sf === "browser" && isSelf())
				return { warn: true, text: "You're sharing this QA Tracker tab, so the screenshot would show QA Tracker. In Chrome's sharing bar click \u201cShare this tab instead\u201d while on the MedX tab, or stop sharing and choose the MedX tab." };
			if (sf === "browser") return { text: "You're sharing a browser tab. Capture now takes that tab even while you stay here." };
			if (sf === "window") return { text: "You're sharing a window. If that window is this browser, press Capture in 5 s and switch to the MedX tab." };
			return { text: "You're sharing your screen. Press Capture in 5 s, then bring MedX to the front." };
		};

		return new Promise((resolve) => {
			const tip = tipText().text;
			const m = h(`<div class="modal sheet"><div class="sheet-box cap-box">
				<div class="sheet-head"><h3>Capture screen</h3><button class="iconbtn" data-x aria-label="Cancel">${ic("x")}</button></div>
				<p class="muted small">${esc(tip)}</p>
				<div class="cap-prev"><div class="cap-wait"><span class="spinner"></span></div></div>
				<div class="cap-btns">
					<button class="btn primary" data-now>${ic("cam")} Capture now</button>
					<button class="btn ghost" data-later>${ic("play")} Capture in <span data-sec>5</span> s</button>
				</div>
				${canFloat ? `<button class="btn block pop-btn" data-float>${ic("external")} Pop out toolbox - stays on top while you work in MedX</button>` : ""}
				<div class="cap-count" hidden></div>
				<p class="muted small center">To share a different tab or window, use <b>Change source</b> or <b>Stop sharing</b> in Chrome's sharing bar.</p>
				</div></div>`);
			document.body.appendChild(m);
			const showTip = () => {
				const t = tipText();
				const el = $(".cap-box p.muted", m);
				el.textContent = t.text;
				el.classList.toggle("cap-warn", !!t.warn);
				$("[data-now]", m).classList.toggle("dim", !!t.warn);
			};
			showTip();
			try { track.addEventListener("capturehandlechange", showTip); } catch (e) { /* ignore */ }
			const poll = setInterval(() => { if (!document.body.contains(m)) clearInterval(poll); else showTip(); }, 1000);
			$(".cap-prev", m).appendChild(video);
			video.play().catch(() => {});
			let done = false, timer = null;
			const finish = (val) => {
				if (done) return;
				done = true;
				clearInterval(timer);
				stop();
				document.title = oldTitle;
				m.remove();
				resolve(val);
			};
			const grab = async () => {
				// wait until a real frame is available
				for (let i = 0; i < 40 && !(video.videoWidth > 0 && video.readyState >= 2); i++) await new Promise((r) => setTimeout(r, 100));
				if (!video.videoWidth) { toast("No picture from the shared screen. Try sharing again.", "err"); finish(null); return; }
				const c = document.createElement("canvas");
				c.width = video.videoWidth; c.height = video.videoHeight;
				c.getContext("2d").drawImage(video, 0, 0);
				const raw = c.toDataURL("image/png");
				stop(); // stop sharing as soon as the shot is taken
				document.title = "✓ Screenshot captured · " + oldTitle;
				m.remove();
				try { window.focus(); } catch (e) { /* ignore */ }
				const data = await annotate(raw);
				document.title = oldTitle;
				done = true;
				resolve(data ? { name: "screen-" + Date.now() + ".png", data } : null);
			};
			track.addEventListener("ended", () => { if (!done && !timer) finish(null); });
			$("[data-x]", m).onclick = () => finish(null);
			if ($("[data-float]", m)) $("[data-float]", m).onclick = () => {
				// hand the live stream over to the floating toolbox (this click allows the pop-up)
				done = true; clearInterval(timer); clearInterval(poll); document.title = oldTitle; m.remove();
				resolve({ float: floatingToolbox("snap", {}, stream) });
			};
			$("[data-now]", m).onclick = () => { clearInterval(timer); grab(); };
			$("[data-later]", m).onclick = () => {
				let left = 5;
				const box = $(".cap-count", m);
				box.hidden = false;
				m.querySelectorAll(".cap-btns .btn").forEach((b) => (b.disabled = true));
				const tick = () => {
					box.textContent = left > 0 ? `Switch to MedX now… capturing in ${left}` : "Capturing…";
					document.title = left > 0 ? `(${left}) Capturing… · ${oldTitle}` : oldTitle;
				};
				tick();
				timer = setInterval(() => {
					left -= 1;
					tick();
					if (left <= 0) { clearInterval(timer); grab(); }
				}, 1000);
			};
		});
	}
	// ---------------------------------------------------------------- webcam photo (desktop)
	// Desktop browsers ignore <input capture>, so open the webcam directly with a live preview.
	const canWebcam = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
	async function cameraPhoto() {
		if (!canWebcam) throw new Error("No camera access in this browser. Use File instead.");
		let devices = [], idx = 0, stream = null;
		const m = h(`<div class="modal sheet"><div class="sheet-box cap-box">
			<div class="sheet-head"><h3>Take a photo</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			<div class="cap-prev"><div class="cap-wait"><span class="spinner"></span></div><video autoplay muted playsinline></video></div>
			<div class="cap-btns"><button class="btn ghost" data-switch hidden>${ic("refresh")} Switch camera</button>
			<button class="btn primary" data-shot disabled>${ic("cam")} Take photo</button></div>
			<p class="muted small center" data-msg>Allow camera access when your browser asks.</p></div></div>`);
		document.body.appendChild(m);
		const video = $("video", m);
		const stop = () => { if (stream) stream.getTracks().forEach((t) => t.stop()); stream = null; };
		const start = async () => {
			stop();
			const dev = devices[idx];
			const constraints = { audio: false, video: dev && dev.deviceId ? { deviceId: { exact: dev.deviceId }, width: { ideal: 1920 }, height: { ideal: 1080 } }
				: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } } };
			stream = await navigator.mediaDevices.getUserMedia(constraints);
			video.srcObject = stream;
			await video.play().catch(() => {});
			$("[data-shot]", m).disabled = false;
			$("[data-msg]", m).textContent = dev && dev.label ? dev.label : "Point the camera at the screen or document.";
		};
		return new Promise((resolve) => {
			const done = (v) => { stop(); m.remove(); resolve(v); };
			$("[data-x]", m).onclick = () => done(null);
			$("[data-switch]", m).onclick = () => { idx = (idx + 1) % devices.length; start().catch((e) => toast(e.message, "err")); };
			$("[data-shot]", m).onclick = async () => {
				const c = document.createElement("canvas");
				c.width = video.videoWidth; c.height = video.videoHeight;
				c.getContext("2d").drawImage(video, 0, 0);
				const raw = c.toDataURL("image/jpeg", 0.9);
				stop(); m.remove();
				const data = await annotate(raw);
				resolve(data ? { name: "photo-" + Date.now() + ".png", data } : null);
			};
			start().then(async () => {
				devices = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
				const cur = stream && stream.getVideoTracks()[0] && stream.getVideoTracks()[0].getSettings().deviceId;
				idx = Math.max(0, devices.findIndex((d) => d.deviceId === cur));
				$("[data-switch]", m).hidden = devices.length < 2;
			}).catch((e) => {
				const msg = e && e.name === "NotAllowedError" ? "Camera access was blocked. Allow it from the camera icon in the address bar, or use File."
					: e && e.name === "NotFoundError" ? "No camera found on this computer. Use File, Capture or your phone instead." : (e.message || "Camera unavailable");
				$("[data-msg]", m).textContent = msg;
				$(".cap-wait", m).innerHTML = ic("cam", "big");
			});
		});
	}

	// ---------------------------------------------------------------- screen recorder
	const canRecordScreen = canCaptureScreen && typeof window.MediaRecorder !== "undefined";
	function pickMime() {
		const list = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4;codecs=avc1,mp4a", "video/mp4"];
		for (const m of list) { try { if (MediaRecorder.isTypeSupported(m)) return m; } catch (e) { /* ignore */ } }
		return "";
	}
	async function recordScreen() {
		if (!canRecordScreen) throw new Error("Screen recording isn't available in this browser. Use Win+Shift+R (Snipping Tool) and attach the file.");
		const max = (state.boot && state.boot.max_upload) || 10 * 1048576;
		const VBPS = 650000, ABPS = 48000;
		const maxSec = Math.max(30, Math.min(300, Math.floor(((max * 8) / (VBPS + ABPS)) * 0.85)));
		// 1. options
		const go = await new Promise((resolve) => {
			const m = h(`<div class="modal sheet"><div class="sheet-box">
				<div class="sheet-head"><h3>Record your screen</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
				<p class="muted small">Show the problem step by step. Choose the <b>MedX tab</b> (or a window / your screen) in the next dialog, then switch to it and do the steps. Come back here and press <b>Stop</b>, or use Chrome's <b>Stop sharing</b>.</p>
				<label class="ga-check"><input type="checkbox" id="rmic" checked> Include my voice (explain while you record)</label>
				<p class="muted small">Up to ${fmtDur(maxSec)} per recording (site upload limit ${fmtMB(max)}).</p>
				<button class="btn danger block" data-go>${ic("rec")} Start recording</button></div></div>`);
			document.body.appendChild(m);
			$("[data-x]", m).onclick = () => { m.remove(); resolve(null); };
			$("[data-go]", m).onclick = () => { const mic = $("#rmic", m).checked; m.remove(); resolve({ mic }); };
		});
		if (!go) return null;
		// 2. sources
		const display = await getShare(10);
		if (!display) return null;
		if (canFloat) {
			let tb = await floatingToolbox("record", { mic: go.mic }, display);
			if (tb.fallback) {
				// Chrome only allows the pop-up right after a click: ask for one more click
				const pop = await new Promise((resolve) => {
					const m = h(`<div class="modal sheet"><div class="sheet-box">
						<div class="sheet-head"><h3>Ready to record</h3></div>
						<p class="muted small">Screen sharing is on. Open the floating toolbox to control the recording from any screen.</p>
						<button class="btn danger block" data-pop>${ic("rec")} Start in floating toolbox</button>
						<button class="btn ghost block" data-here>Record with controls in this tab</button></div></div>`);
					document.body.appendChild(m);
					$("[data-pop]", m).onclick = () => { m.remove(); resolve(true); };
					$("[data-here]", m).onclick = () => { m.remove(); resolve(false); };
				});
				if (pop) tb = await floatingToolbox("record", { mic: go.mic }, display);
			}
			if (!tb.fallback) return { toolbox: tb };
		}
		let mic = null;
		if (go.mic) {
			try { mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
			catch (e) { toast("Microphone not available - recording without voice"); }
		}
		const vtrack = display.getVideoTracks()[0];
		const tracks = [vtrack].concat(mic ? mic.getAudioTracks() : []);
		const stream = new MediaStream(tracks);
		const mime = pickMime();
		let recorder;
		try { recorder = new MediaRecorder(stream, Object.assign({ videoBitsPerSecond: VBPS, audioBitsPerSecond: ABPS }, mime ? { mimeType: mime } : {})); }
		catch (e) { display.getTracks().forEach((t) => t.stop()); if (mic) mic.getTracks().forEach((t) => t.stop()); throw new Error("This browser can't record the screen."); }
		const chunks = [];
		recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
		const oldTitle = document.title;
		const started = Date.now();
		const isSelf = () => { try { const ch = vtrack.getCaptureHandle && vtrack.getCaptureHandle(); return !!(ch && ch.handle === SELF_HANDLE); } catch (e) { return false; } };
		const bar = h(`<div class="recbar"><span class="rec-dot"></span><b class="rec-time">0:00</b><span class="muted small rec-max">/ ${fmtDur(maxSec)}</span>
			<span class="rec-warn" hidden>You're recording this QA Tracker tab - use Chrome's "Share this tab instead" on the MedX tab</span>
			<button class="btn danger" data-stop>${ic("stop")} Stop</button></div>`);
		document.body.appendChild(bar);
		// 3. record
		const result = await new Promise((resolve) => {
			let stopped = false;
			const stopAll = () => {
				if (stopped) return;
				stopped = true;
				clearInterval(tick);
				try { if (recorder.state !== "inactive") recorder.stop(); } catch (e) { /* ignore */ }
			};
			recorder.onstop = () => {
				display.getTracks().forEach((t) => t.stop());
				if (mic) mic.getTracks().forEach((t) => t.stop());
				bar.remove();
				document.title = oldTitle;
				const secs = (Date.now() - started) / 1000;
				const type = (recorder.mimeType || mime || "video/webm").split(";")[0];
				resolve(chunks.length ? { blob: new Blob(chunks, { type }), duration: secs, ext: type.includes("mp4") ? "mp4" : "webm" } : null);
			};
			const tick = setInterval(() => {
				const secs = (Date.now() - started) / 1000;
				$(".rec-time", bar).textContent = fmtDur(secs);
				document.title = `● REC ${fmtDur(secs)} · ${oldTitle}`;
				$(".rec-warn", bar).hidden = !isSelf();
				if (secs >= maxSec) { toast("Maximum length reached - recording stopped"); stopAll(); }
			}, 500);
			$("[data-stop]", bar).onclick = stopAll;
			vtrack.addEventListener("ended", stopAll);
			recorder.start(1000);
		});
		if (!result) { toast("Nothing was recorded", "err"); return null; }
		try { window.focus(); } catch (e) { /* ignore */ }
		// 4. preview
		const url = URL.createObjectURL(result.blob);
		const keep = await new Promise((resolve) => {
			const m = h(`<div class="modal sheet"><div class="sheet-box cap-box">
				<div class="sheet-head"><h3>Your recording</h3><button class="iconbtn" data-x aria-label="Discard">${ic("x")}</button></div>
				<video class="rec-prev" src="${url}" controls playsinline></video>
				<p class="muted small">${fmtDur(result.duration)} · ${fmtMB(result.blob.size)}${result.blob.size > max ? ` - <b class="t-red">larger than the ${fmtMB(max)} limit, record a shorter clip</b>` : ""}</p>
				<div class="cap-btns"><button class="btn ghost" data-no>${ic("trash")} Discard</button>
				<button class="btn primary" data-yes ${result.blob.size > max ? "disabled" : ""}>${ic("check")} Attach recording</button></div></div></div>`);
			document.body.appendChild(m);
			const done = (v) => { m.remove(); resolve(v); };
			$("[data-x]", m).onclick = () => done(false);
			$("[data-no]", m).onclick = () => done(false);
			$("[data-yes]", m).onclick = () => done(true);
		});
		if (!keep) { URL.revokeObjectURL(url); return null; }
		return { blob: result.blob, duration: result.duration, name: `screen-recording-${Date.now()}.${result.ext}` };
	}

	// ---------------------------------------------------------------- floating toolbox
	// An always-on-top mini window (Chrome / Edge "Document Picture-in-Picture"), like the
	// Snipping Tool toolbar: it stays visible while you work in MedX, on any screen.
	const canFloat = canCaptureScreen && "documentPictureInPicture" in window && window.isSecureContext;
	const FLOAT_CSS = `
		*{box-sizing:border-box} html,body{margin:0;height:100%}
		body{font:13px/1.35 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;background:#161B22;color:#E6EAF0;
			display:flex;flex-direction:column;justify-content:center;gap:7px;padding:8px 10px;user-select:none;transition:background .15s}
		body.flash{background:#2b3a4a}
		.row{display:flex;align-items:center;gap:6px}
		button{font:inherit;display:inline-flex;align-items:center;gap:5px;border:1px solid #2A313C;background:#1D232C;color:#E6EAF0;
			border-radius:9px;padding:7px 10px;cursor:pointer;white-space:nowrap}
		button:hover{background:#26303b} button:disabled{opacity:.45;cursor:default}
		button.snap{background:#0F766E;border-color:#0F766E;color:#fff;font-weight:600} button.snap:hover{background:#11877e}
		button.rec.on{background:#D92D20;border-color:#D92D20;color:#fff}
		button.mic{padding:7px 8px} button.mic.off{opacity:.5;text-decoration:line-through}
		button.done{margin-left:auto;background:#E6EAF0;color:#14181F;border-color:#E6EAF0;font-weight:600}
		.ic{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;flex:none}
		.stat{display:flex;align-items:center;gap:8px;color:#98A2B3;font-size:12px;min-height:16px}
		.stat .msg{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
		.stat.warn .msg{color:#FDB022;white-space:normal}
		.cnt{color:#E6EAF0;font-weight:600}
		.thumb{height:26px;border-radius:4px;border:1px solid #2A313C;display:none} .thumb.show{display:block}
		.dot{width:8px;height:8px;border-radius:50%;background:#F97066;display:inline-block;animation:b 1s infinite}
		@keyframes b{50%{opacity:.25}}`;

	async function floatingToolbox(mode, opts, display) {
		opts = opts || {};
		let pip;
		try { pip = await documentPictureInPicture.requestWindow({ width: 470, height: 112 }); }
		catch (e) { return { fallback: true }; }
		const d = pip.document;
		d.title = "QA Tracker capture";
		const st = d.createElement("style"); st.textContent = FLOAT_CSS; d.head.appendChild(st);
		d.body.innerHTML = `<div class="row">
				<button class="snap" data-snap title="Take a screenshot now">${ic("cam")}Snap</button>
				<button data-delay title="Screenshot in 3 seconds (for menus and pop-ups)">${ic("timer")}3 s</button>
				<button class="rec" data-rec title="Start / stop a screen recording">${ic("rec")}<span>Record</span></button>
				<button class="mic ${opts.mic ? "" : "off"}" data-mic title="Include my voice in recordings">${ic("mic")}</button>
				<button class="done" data-done title="Finish and add everything to the report">${ic("check")}Done</button>
			</div>
			<div class="stat"><img class="thumb" alt=""><span class="msg"></span><span class="cnt"></span></div>`;
		const $p = (q) => d.querySelector(q);
		const msg = (t, warn) => { $p(".msg").innerHTML = t; $p(".stat").classList.toggle("warn", !!warn); };

		const vtrack = display.getVideoTracks()[0];
		const video = document.createElement("video");
		video.srcObject = display; video.muted = true; video.playsInline = true; video.play().catch(() => {});
		const shots = [], recs = [];
		const oldTitle = document.title;
		const max = (state.boot && state.boot.max_upload) || 10 * 1048576;
		const VBPS = 650000, ABPS = 48000;
		const maxSec = Math.max(30, Math.min(300, Math.floor(((max * 8) / (VBPS + ABPS)) * 0.85)));
		let micOn = !!opts.mic, recorder = null, mic = null, recStart = 0, tick = null, delayTimer = null, finished = false;

		const isSelf = () => { try { const ch = vtrack.getCaptureHandle && vtrack.getCaptureHandle(); return !!(ch && ch.handle === SELF_HANDLE); } catch (e) { return false; } };
		const surface = () => (vtrack.getSettings && vtrack.getSettings().displaySurface) || "";
		const count = () => {
			const parts = [];
			if (shots.length) parts.push(`${shots.length} shot${shots.length > 1 ? "s" : ""}`);
			if (recs.length) parts.push(`${recs.length} video${recs.length > 1 ? "s" : ""}`);
			$p(".cnt").textContent = parts.join(" · ");
		};
		const idle = () => {
			if (recorder) return;
			if (surface() === "browser" && isSelf()) msg("You're sharing the QA Tracker tab. Open MedX and click <b>Share this tab instead</b> in Chrome's sharing bar.", true);
			else if (surface() === "monitor") msg("Sharing your whole screen. This toolbox shows in shots; blur it in the editor, or share a window/tab instead.");
			else msg(surface() === "browser" ? "Sharing a tab. Work in MedX, then press Snap or Record." : "Sharing a window. Work in MedX, then press Snap or Record.");
		};
		idle();
		const poll = setInterval(idle, 1500);

		const grab = async () => {
			for (let i = 0; i < 30 && !(video.videoWidth > 0 && video.readyState >= 2); i++) await new Promise((r) => setTimeout(r, 100));
			let c = document.createElement("canvas");
			if (video.videoWidth) {
				c.width = video.videoWidth; c.height = video.videoHeight;
				c.getContext("2d").drawImage(video, 0, 0);
			} else if (window.ImageCapture) {
				const bmp = await new ImageCapture(vtrack).grabFrame();
				c.width = bmp.width; c.height = bmp.height; c.getContext("2d").drawImage(bmp, 0, 0);
			} else { msg("No picture from the shared screen yet - try again.", true); return; }
			const data = c.toDataURL("image/png");
			shots.push({ name: "screen-" + Date.now() + ".png", data });
			const t = $p(".thumb"); t.src = data; t.classList.add("show");
			d.body.classList.add("flash"); setTimeout(() => d.body.classList.remove("flash"), 160);
			count();
			msg("Screenshot taken. Snap again, or press Done.");
			document.title = `📷 ${shots.length} · ${oldTitle}`;
		};
		$p("[data-snap]").onclick = () => { if (delayTimer) return; grab(); };
		$p("[data-delay]").onclick = () => {
			if (delayTimer) return;
			let left = 3;
			const show = () => msg(`Open the menu / screen now… <b>${left}</b>`);
			show();
			delayTimer = setInterval(() => {
				left -= 1;
				if (left > 0) return show();
				clearInterval(delayTimer); delayTimer = null; grab();
			}, 1000);
		};
		$p("[data-mic]").onclick = () => { micOn = !micOn; $p("[data-mic]").classList.toggle("off", !micOn); };

		const stopRec = () => new Promise((resolve) => {
			if (!recorder) return resolve();
			const r = recorder;
			r.addEventListener("stop", () => resolve(), { once: true });
			try { if (r.state !== "inactive") r.stop(); else resolve(); } catch (e) { resolve(); }
		});
		const startRec = async () => {
			const tracks = [vtrack];
			if (micOn) {
				try { mic = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); tracks.push(...mic.getAudioTracks()); }
				catch (e) { msg("Microphone not available - recording without voice.", true); }
			}
			const mime = pickMime();
			const chunks = [];
			try { recorder = new MediaRecorder(new MediaStream(tracks), Object.assign({ videoBitsPerSecond: VBPS, audioBitsPerSecond: ABPS }, mime ? { mimeType: mime } : {})); }
			catch (e) { msg("This browser can't record the screen.", true); recorder = null; return; }
			recorder.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
			recorder.onstop = () => {
				clearInterval(tick);
				if (mic) { mic.getTracks().forEach((t) => t.stop()); mic = null; }
				const secs = (Date.now() - recStart) / 1000;
				const type = (recorder.mimeType || mime || "video/webm").split(";")[0];
				if (chunks.length) {
					const blob = new Blob(chunks, { type });
					if (blob.size > max) toast(`Recording is larger than the ${fmtMB(max)} upload limit - record a shorter clip`, "err");
					else recs.push({ blob, duration: secs, name: `screen-recording-${Date.now()}.${type.includes("mp4") ? "mp4" : "webm"}` });
				}
				recorder = null;
				const b = $p("[data-rec]"); b.classList.remove("on"); b.innerHTML = `${ic("rec")}<span>Record</span>`;
				$p("[data-snap]").disabled = $p("[data-delay]").disabled = $p("[data-mic]").disabled = false;
				count(); document.title = oldTitle;
				if (!finished) msg(`Recording saved (${fmtDur(secs)}). Record again, Snap, or press Done.`);
			};
			recStart = Date.now();
			recorder.start(1000);
			const b = $p("[data-rec]"); b.classList.add("on"); b.innerHTML = `${ic("stop")}<span>Stop</span>`;
			$p("[data-snap]").disabled = $p("[data-delay]").disabled = $p("[data-mic]").disabled = true;
			tick = setInterval(() => {
				const secs = (Date.now() - recStart) / 1000;
				msg(`<span class="dot"></span> Recording <b>${fmtDur(secs)}</b> / ${fmtDur(maxSec)}${micOn && mic ? " · with voice" : ""}${surface() === "browser" && isSelf() ? " - this is the QA Tracker tab!" : ""}`);
				document.title = `● REC ${fmtDur(secs)} · ${oldTitle}`;
				if (secs >= maxSec) { stopRec(); msg("Maximum length reached - recording stopped."); }
			}, 500);
		};
		$p("[data-rec]").onclick = () => { if (recorder) stopRec(); else startRec(); };

		return new Promise((resolve) => {
			const finish = async () => {
				if (finished) return;
				finished = true;
				clearInterval(poll); clearInterval(delayTimer);
				await stopRec();
				display.getTracks().forEach((t) => t.stop());
				document.title = oldTitle;
				try { pip.close(); } catch (e) { /* already closed */ }
				try { window.focus(); } catch (e) { /* ignore */ }
				resolve({ shots, recs });
			};
			$p("[data-done]").onclick = finish;
			pip.addEventListener("pagehide", finish);          // toolbox closed with its X
			vtrack.addEventListener("ended", finish);           // "Stop sharing" in Chrome's bar
			if (mode === "record") startRec();
		});
	}

	const isTouch = /Android|iPhone|iPad/i.test(navigator.userAgent);
	const sourceButtons = (small) => `<div class="src-btns ${small ? "small" : ""}">
		<button type="button" class="btn ghost" data-src="camera">${ic("cam")}${isTouch ? "Photo" : "Camera"}</button>
		${isTouch ? `<button type="button" class="btn ghost" data-src="camvideo">${ic("video")}Video</button>` : ""}
		${canCaptureScreen ? `<button type="button" class="btn ghost" data-src="screen">${ic("desk")}Capture</button>` : ""}
		${canRecordScreen ? `<button type="button" class="btn ghost rec-btn" data-src="record">${ic("rec")}Record</button>` : ""}
		<button type="button" class="btn ghost" data-src="file">${ic("clip")}File</button></div>
		${!window.isSecureContext && !small ? `<p class="muted small">Screen capture, recording and the webcam need the site to be opened over https://.</p>` : ""}`;
	const pasteHint = () => /Mac/i.test(navigator.platform) ? "Snip with Cmd+Ctrl+Shift+4, then paste with Cmd+V" : (/Android|iPhone|iPad/i.test(navigator.userAgent) ? "Take a screenshot, then choose it with Choose file" : "Snip with Win+Shift+S (Snipping Tool), then paste with Ctrl+V");

	// ------------------------------------------------------------------ annotator
	function annotate(src) {
		return new Promise((resolve) => {
			const m = h(`<div class="modal annot"><div class="annot-bar">
				<button data-t="pen" class="on" title="Draw">${ic("pen")}</button>
				<button data-t="arrow" title="Arrow">${ic("arrow")}</button>
				<button data-t="box" title="Box">${ic("box")}</button>
				<button data-t="blur" title="Hide private data">${ic("blur")}</button>
				<span class="sp"></span>
				<button data-c="#E11D48" class="c on" style="--c:#E11D48" title="Red"></button>
				<button data-c="#F59E0B" class="c" style="--c:#F59E0B" title="Yellow"></button>
				<button data-u title="Undo">${ic("undo")}</button>
				<span class="grow"></span>
				<button class="btn ghost" data-cancel>Cancel</button>
				<button class="btn primary" data-save>Done</button></div>
				<div class="annot-wrap"><canvas></canvas></div>
				<div class="annot-tip">Draw on the screenshot. Use ${ic("blur")} to hide patient names before sending.</div></div>`);
			document.body.appendChild(m);
			const cv = $("canvas", m), ctx = cv.getContext("2d");
			const img = new Image();
			let tool = "pen", color = "#E11D48", history = [], drawing = null;
			img.onload = () => {
				cv.width = img.naturalWidth; cv.height = img.naturalHeight;
				ctx.drawImage(img, 0, 0);
				history.push(ctx.getImageData(0, 0, cv.width, cv.height));
			};
			img.src = src;
			const pos = (e) => {
				const r = cv.getBoundingClientRect();
				const p = e.touches ? e.touches[0] : e;
				return { x: (p.clientX - r.left) * cv.width / r.width, y: (p.clientY - r.top) * cv.height / r.height };
			};
			const lw = () => Math.max(3, Math.round(cv.width / 300));
			const restore = () => ctx.putImageData(history[history.length - 1], 0, 0);
			const shape = (a, b, final) => {
				restore();
				ctx.strokeStyle = color; ctx.fillStyle = color; ctx.lineWidth = lw(); ctx.lineCap = "round";
				if (tool === "box") ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);
				if (tool === "arrow") {
					ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
					const ang = Math.atan2(b.y - a.y, b.x - a.x), L = lw() * 5;
					ctx.beginPath(); ctx.moveTo(b.x, b.y);
					ctx.lineTo(b.x - L * Math.cos(ang - 0.45), b.y - L * Math.sin(ang - 0.45));
					ctx.lineTo(b.x - L * Math.cos(ang + 0.45), b.y - L * Math.sin(ang + 0.45));
					ctx.closePath(); ctx.fill();
				}
				if (tool === "blur") {
					const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y), w = Math.abs(b.x - a.x), hh = Math.abs(b.y - a.y);
					if (w > 2 && hh > 2) {
						if (final) {
							const px = Math.max(6, Math.round(Math.max(w, hh) / 14));
							const tmp = document.createElement("canvas");
							tmp.width = Math.max(1, Math.round(w / px)); tmp.height = Math.max(1, Math.round(hh / px));
							tmp.getContext("2d").drawImage(cv, x, y, w, hh, 0, 0, tmp.width, tmp.height);
							ctx.imageSmoothingEnabled = false;
							ctx.drawImage(tmp, 0, 0, tmp.width, tmp.height, x, y, w, hh);
							ctx.imageSmoothingEnabled = true;
						} else {
							ctx.setLineDash([lw() * 2, lw() * 2]); ctx.strokeRect(x, y, w, hh); ctx.setLineDash([]);
						}
					}
				}
			};
			const down = (e) => {
				e.preventDefault();
				drawing = { a: pos(e), last: pos(e) };
				if (tool === "pen") { ctx.strokeStyle = color; ctx.lineWidth = lw(); ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.beginPath(); ctx.moveTo(drawing.a.x, drawing.a.y); }
			};
			const move = (e) => {
				if (!drawing) return;
				e.preventDefault();
				const p = pos(e);
				if (tool === "pen") { ctx.lineTo(p.x, p.y); ctx.stroke(); } else shape(drawing.a, p, false);
				drawing.last = p;
			};
			const up = () => {
				if (!drawing) return;
				if (tool !== "pen") shape(drawing.a, drawing.last, true);
				history.push(ctx.getImageData(0, 0, cv.width, cv.height));
				drawing = null;
			};
			cv.addEventListener("mousedown", down); cv.addEventListener("mousemove", move); window.addEventListener("mouseup", up);
			cv.addEventListener("touchstart", down, { passive: false }); cv.addEventListener("touchmove", move, { passive: false }); cv.addEventListener("touchend", up);
			m.querySelectorAll("[data-t]").forEach((b) => (b.onclick = () => { tool = b.dataset.t; m.querySelectorAll("[data-t]").forEach((x) => x.classList.toggle("on", x === b)); }));
			m.querySelectorAll("[data-c]").forEach((b) => (b.onclick = () => { color = b.dataset.c; m.querySelectorAll("[data-c]").forEach((x) => x.classList.toggle("on", x === b)); }));
			$("[data-u]", m).onclick = () => { if (history.length > 1) { history.pop(); restore(); } };
			const close = (val) => { window.removeEventListener("mouseup", up); m.remove(); resolve(val); };
			$("[data-cancel]", m).onclick = () => close(null);
			$("[data-save]", m).onclick = () => close(cv.toDataURL("image/png"));
		});
	}

	function lightbox(src, video) {
		video = video || /\.(webm|mp4|mov|m4v)(\?|$)/i.test(src);
		const m = h(`<div class="modal lb">${video ? `<video src="${esc(src)}" controls autoplay playsinline></video>` : `<img src="${esc(src)}" alt="">`}<button class="lb-x" aria-label="Close">${ic("x")}</button><a class="lb-open" href="${esc(src)}" target="_blank">Open original</a></div>`);
		m.onclick = (e) => { if (e.target === m || e.target.closest(".lb-x")) m.remove(); };
		document.body.appendChild(m);
	}

	// ------------------------------------------------------------------ state & router
	const lsGet = (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } };
	const lsSet = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } };
	const state = { boot: null, scope: "needs_you", search: "", picker: null, vendor: "", project: lsGet("qa_project") || "" };
	const app = $("#app");

	function shell(content, opts) {
		opts = opts || {};
		const b = state.boot;
		const initials = (b.full_name || b.user).split(/\s+/).map((x) => x[0]).slice(0, 2).join("").toUpperCase();
		return `<header class="top">
			${opts.back ? `<a class="iconbtn" href="${opts.back}" aria-label="Back">${ic("back")}</a>` :
				`<a class="brand" href="#/">${b.logo ? `<img src="${esc(b.logo)}" alt="">` : `<span class="logo">${ic("check")}</span>`}<span>${esc(b.title)}</span></a>`}
			${!opts.back && (b.projects || []).length ? `<button class="projbtn" id="proj" title="Switch project">${ic("grid")}<span>${esc(projLabel())}</span>${b.projects.length > 1 ? ic("down") : ""}</button>` : ""}
			<div class="grow">${opts.title ? `<div class="ttl">${opts.title}</div>` : ""}</div>
			<button class="avatar" id="me" aria-label="Account">${esc(initials)}</button>
		</header>
		<main>${content}</main>
		${opts.nav === false ? "" : `<nav class="bottom">
			${b.dashboard ? `<a href="#/dash" class="${opts.tab === "dash" ? "on" : ""}">${ic("chart")}<span>Dashboard</span></a>` : ""}
			<a href="#/tickets" class="${opts.tab === "home" ? "on" : ""}">${ic("list")}<span>Tickets</span>${b.counts.needs_you ? `<b>${b.counts.needs_you}</b>` : ""}</a>
			<a href="#/new" class="new">${ic("plus")}<span>Report</span></a>
			${b.gaps ? `<a href="#/gaps" class="${opts.tab === "gaps" ? "on" : ""}">${ic("grid")}<span>Gaps</span>${b.gap_needs ? `<b>${b.gap_needs}</b>` : ""}</a>` : ""}
			<a href="#/runs" class="${opts.tab === "runs" ? "on" : ""}">${ic("play")}<span>Test runs</span>${b.counts.runs ? `<b>${b.counts.runs}</b>` : ""}</a>
		</nav>`}`;
	}

	function projLabel() {
		const b = state.boot;
		if (b.project === "all") return "All projects";
		const p = (b.projects || []).find((x) => x.name === b.project);
		return p ? p.name : "Project";
	}

	async function switchProject(name) {
		state.project = name; state.vendor = "";
		lsSet("qa_project", name);
		state.boot = await api("boot", { project: name });
		if (window.QAP.onProjectChange) window.QAP.onProjectChange(name);
		route();
	}

	function bindShell() {
		const pb = $("#proj");
		if (pb && state.boot.projects.length > 1) pb.onclick = (e) => {
			e.stopPropagation();
			const b = state.boot;
			const menu = h(`<div class="menu projmenu"><div class="mhead"><b>Projects</b><span>You see only the projects you're a member of</span></div>
				${b.projects.map((p) => `<a href="#" data-p="${esc(p.name)}" class="${p.name === b.project ? "on" : ""}" style="padding-left:${10 + (p.depth || 0) * 18}px">${ic(p.name === b.project ? "check" : (p.depth ? "arrow" : "grid"))}<span><b>${esc(p.name)}</b><em>${esc([p.depth ? "sub-project" : p.client, p.status].filter(Boolean).join(" · "))}</em></span></a>`).join("")}
				<a href="#" data-p="all" class="${b.project === "all" ? "on" : ""}">${ic("list")}<span><b>All my projects</b><em>Combined list</em></span></a></div>`);
			menu.querySelectorAll("[data-p]").forEach((a) => (a.onclick = (ev) => { ev.preventDefault(); menu.remove(); switchProject(a.dataset.p); }));
			document.body.appendChild(menu);
			setTimeout(() => document.addEventListener("click", function off(ev) { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener("click", off); } }), 0);
		};
		const me = $("#me");
		if (!me) return;
		me.onclick = () => {
			const b = state.boot;
			const menu = h(`<div class="menu"><div class="mhead"><b>${esc(b.full_name)}</b><span>${esc(b.roles.join(", ") || b.party)}</span></div>
				${b.is_project_lead ? `<a href="#/team">${ic("users")} Team & coverage</a>` : ""}
				${b.desk ? `<a href="/app/qa-tracker">${ic("desk")} Open Desk</a>` : ""}
				<a href="/app/qa-issue" ${b.desk ? "" : 'hidden'}>${ic("list")} All issues (Desk)</a>
				<a href="/?cmd=web_logout" data-logout>${ic("out")} Log out</a></div>`);
			$("[data-logout]", menu).onclick = (e) => { e.preventDefault(); fetch("/api/method/logout", { method: "POST", headers: { "X-Frappe-CSRF-Token": window.QA_CSRF } }).finally(() => (location.href = "/login")); };
			document.body.appendChild(menu);
			setTimeout(() => document.addEventListener("click", function off(e) { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener("click", off); } }), 0);
		};
	}

	async function refreshBoot() {
		state.boot = await api("boot");
		if (state.boot.project && state.boot.project !== state.project) { state.project = state.boot.project; lsSet("qa_project", state.project); }
	}

	async function route() {
		if (state.picker) { state.picker.destroy(); state.picker = null; }
		const hash = location.hash.replace(/^#\/?/, "");
		const [view, arg] = hash.split("/");
		window.scrollTo(0, 0);
		try {
			if (!view && state.boot.persona === "management" && (window.QAP.routes || {}).dash) return window.QAP.routes.dash();
			if (view === "tickets") return viewHome();
			if (view === "new") return viewNew();
			if (view === "t" && arg) return viewTicket(decodeURIComponent(arg));
			if (view === "runs") return viewRuns();
			if (view === "team") return viewTeam();
			if (view === "r" && arg) return viewRun(decodeURIComponent(arg));
			const ext = (window.QAP.routes || {})[view];
			if (ext) return ext(arg ? decodeURIComponent(arg) : null, hash.split("/").slice(2).map(decodeURIComponent));
			return viewHome();
		} catch (e) {
			toast(e.message, "err");
		}
	}

	// ------------------------------------------------------------------ home
	async function viewHome() {
		const b = state.boot;
		const scopes = [["needs_you", `Needs you${b.counts.needs_you ? " · " + b.counts.needs_you : ""}`], ["open", "Open"], ["done", "Done"]];
		app.innerHTML = shell(`
			<section class="hello"><h1>Hi ${esc((b.full_name || "").split(" ")[0] || "there")}</h1>
			<p>${b.counts.needs_you ? `${b.counts.needs_you} ticket${b.counts.needs_you > 1 ? "s are" : " is"} waiting for you.` : "Nothing is waiting for you right now."}</p></section>
			${(b.scoreboard || []).length > 1 || ((b.scoreboard || []).length === 1 && b.scoreboard[0].vendor) ? `<div class="vboard">${b.scoreboard.map((v) => `<button class="vcard ${state.vendor === (v.vendor || "-") ? "on" : ""}" data-vendor="${esc(v.vendor || "-")}">
				<div class="vname">${esc(v.label)}${v.product ? `<span>${esc(v.product)}</span>` : ""}</div>
				<div class="vnums"><b>${v.open}</b><em>open</em>${v.blockers ? `<b class="red">${v.blockers}</b><em>blocker${v.blockers > 1 ? "s" : ""}</em>` : ""}${v.overdue ? `<b class="amber">${v.overdue}</b><em>overdue</em>` : ""}${v.retest ? `<b>${v.retest}</b><em>to retest</em>` : ""}</div>
				${v.open ? `<div class="muted small">avg age ${v.avg_age} day${v.avg_age === 1 ? "" : "s"}</div>` : ""}</button>`).join("")}</div>` : ""}
			${b.my_vendor ? `<p class="muted small vnote">You see ${esc(b.my_vendor)} tickets in this project.</p>` : ""}
			${b.limits && (b.limits.sites || b.limits.modules) ? `<p class="muted small vnote">Your allocation: ${esc([(b.limits.sites ? b.limits.sites.length + " site" + (b.limits.sites.length > 1 ? "s" : "") : "all sites"), (b.limits.modules ? b.limits.modules.join(", ") : "all areas")].join(" · "))}</p>` : ""}
			${b.is_project_lead ? `<a class="teamlink" href="#/team">${ic("users")} Team & coverage${(b.subprojects || []).length ? ` · ${b.subprojects.length} sub-project${b.subprojects.length > 1 ? "s" : ""}` : ""}</a>` : ""}
			<div class="search">${ic("search")}<input id="q" placeholder="Search tickets or ISS number" value="${esc(state.search)}"></div>
			<div class="chips" id="scopes">${scopes.map(([k, l]) => `<button class="chip ${state.scope === k ? "on" : ""}" data-s="${k}">${l}</button>`).join("")}</div>
			<div id="list" class="list"><div class="skel"></div><div class="skel"></div><div class="skel"></div></div>`, { tab: "home" });
		bindShell();
		app.querySelectorAll("[data-s]").forEach((el) => (el.onclick = () => { state.scope = el.dataset.s; viewHome(); }));
		app.querySelectorAll("[data-vendor]").forEach((el) => (el.onclick = () => {
			state.vendor = state.vendor === el.dataset.vendor ? "" : el.dataset.vendor;
			if (state.vendor && state.scope === "needs_you") state.scope = "open";
			viewHome();
		}));
		let timer;
		$("#q").oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { state.search = e.target.value; loadList(); }, 300); };
		loadList();
	}

	async function loadList() {
		const list = $("#list");
		if (!list) return;
		const rows = await api("tickets", { scope: state.scope, search: state.search, vendor: state.vendor || null });
		if (!rows.length) {
			list.innerHTML = state.scope === "needs_you" && !state.search
				? `<div class="empty"><div class="em-ic">${ic("check")}</div><h3>You're all caught up</h3><p>Tickets that need your retest, fix or approval show up here.</p><a class="btn primary" href="#/new">${ic("plus")} Report an issue</a></div>`
				: `<div class="empty"><h3>No tickets found</h3><p>Try another search or tab.</p></div>`;
			return;
		}
		list.innerHTML = rows.map((r) => `<a class="card tk ${r.needs_you ? "needs" : ""}" href="#/t/${encodeURIComponent(r.name)}">
			${r.thumb ? `<img class="tk-img" src="${esc(r.thumb)}" alt="" loading="lazy">` : `<div class="tk-img none">${ic("cam")}</div>`}
			<div class="tk-body"><div class="tk-top"><span class="muted">${sevDot(r.severity)}${esc(r.name)}${r.module ? " · " + esc(r.module) : ""}</span>${stagePill(r.status)}</div>
			<div class="tk-title">${esc(r.title)}</div>${stageBar(r.stage)}
			<div class="muted small">${r.needs_you ? `<b class="needs-tag">Needs you</b> · ` : ""}${r.vendor ? `<span class="vtag">${esc(r.vendor)}</span> · ` : ""}${state.boot.project === "all" && r.project ? esc(r.project) + " · " : ""}${esc(r.ago)}</div></div></a>`).join("");
	}

	// ------------------------------------------------------------------ new ticket
	function viewNew() {
		const b = state.boot;
		const leaves = b.sites.filter((x) => !x.group);
		const sites = leaves.length ? leaves : b.sites, mods = b.modules;
		const vendors = b.my_vendor ? [] : (b.vendors || []);
		const sel = { site: b.default_site || (sites.length === 1 ? sites[0].name : null), module: null, severity: "Medium", type: "Bug", moduleTouched: false,
			vendor: vendors.length === 1 ? vendors[0].name : null, vendorTouched: false };
		const siteLabel = (x) => { const parts = (x.path || x.name).split(" › "); return parts.length > 2 ? parts.slice(-2).join(" › ") : parts.join(" › "); };
		app.innerHTML = shell(`
			<section class="form">
			<h1>Report an issue</h1>
			${b.help ? `<p class="help">${esc(b.help)}</p>` : `<p class="help">Add a screenshot and say what went wrong. You can paste with Ctrl+V.</p>`}
			<div class="shots" id="shots"><div class="drop">${ic("cam", "big")}<b>Add screenshots</b><span>${esc(pasteHint())} · or drag and drop screenshots, recordings, PDF or Excel files</span></div>${sourceButtons()}<div class="thumbs"></div></div>
			<div class="seg" id="type"><button class="on" data-v="Bug">Something is wrong</button><button data-v="Query">I have a question</button></div>
			<label class="lbl" for="txt">What happened?</label>
			<textarea id="txt" rows="4" placeholder="Credit bills show in the cash counter after changing the payor to cash"></textarea>
			${b.project === "all" ? `<p class="help warn-note">You're viewing all projects. The ticket goes to your default project. Pick a project at the top to choose.</p>` : ""}
			<label class="lbl">Site</label><div class="chips wrap" id="site">${sites.map((s) => `<button class="chip ${sel.site === s.name ? "on" : ""}" data-v="${esc(s.name)}" title="${esc(s.path || s.name)}">${esc(siteLabel(s))}</button>`).join("")}</div>
			<label class="lbl">Area <span class="muted small" id="modhint"></span></label>
			<div class="chips wrap" id="mod">${mods.map((m) => `<button class="chip" data-v="${esc(m.name)}">${esc(m.name)}</button>`).join("")}</div>
			${vendors.length > 1 ? `<label class="lbl">Which system / vendor? <span class="muted small" id="vhint"></span></label>
			<div class="chips wrap" id="ven">${vendors.map((v) => `<button class="chip ${sel.vendor === v.name ? "on" : ""}" data-v="${esc(v.name)}">${esc(v.product || v.scope || v.name)}<span class="muted small"> · ${esc(v.name)}</span></button>`).join("")}</div>` : ""}
			<label class="lbl">How bad is it?</label>
			<div class="seg sevseg" id="sev">${["Low", "Medium", "High", "Blocker"].map((s) => `<button data-v="${s}" class="${s === "Medium" ? "on" : ""}">${s === "Blocker" ? "Blocker · can't work" : s}</button>`).join("")}</div>
			<button class="btn primary block" id="submit">${ic("send")} Send report</button>
			${b.channels.length ? `<div class="alt"><div class="muted small">Other ways to report</div>${b.channels.map((c) => `<${c.url ? `a href="${esc(c.url)}" target="_blank"` : "div"} class="alt-ch"><b>${esc(c.name)}</b><span>${esc(c.hint)}</span></${c.url ? "a" : "div"}>`).join("")}</div>` : ""}
			</section>`, { back: "#/", title: "New ticket", nav: false });
		bindShell();
		state.picker = shotPicker($("#shots"));
		const single = (id, key, after) => app.querySelectorAll(`#${id} [data-v]`).forEach((el) => (el.onclick = () => {
			sel[key] = el.dataset.v;
			app.querySelectorAll(`#${id} [data-v]`).forEach((x) => x.classList.toggle("on", x === el));
			if (after) after();
		}));
		single("site", "site"); single("sev", "severity"); single("type", "type");
		const vendorFromModule = () => {
			if (sel.vendorTouched || !$("#ven")) return;
			const m = mods.find((x) => x.name === sel.module);
			if (m && m.vendor && vendors.some((v) => v.name === m.vendor)) {
				sel.vendor = m.vendor;
				app.querySelectorAll("#ven [data-v]").forEach((x) => x.classList.toggle("on", x.dataset.v === m.vendor));
				$("#vhint").textContent = "(from area)";
			}
		};
		single("mod", "module", () => { sel.moduleTouched = true; $("#modhint").textContent = ""; vendorFromModule(); });
		if ($("#ven")) single("ven", "vendor", () => { sel.vendorTouched = true; $("#vhint").textContent = ""; });
		const guess = () => {
			if (sel.moduleTouched) return;
			const t = $("#txt").value.toLowerCase();
			let best = null, score = 0;
			mods.forEach((m) => {
				let s = 0;
				(m.keywords || "").split(",").forEach((k) => { k = k.trim().toLowerCase(); if (k && new RegExp("(^|[^a-z])" + k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "([^a-z]|$)").test(t)) s += 1 + k.split(" ").length; });
				if (s > score) { score = s; best = m.name; }
			});
			sel.module = best;
			app.querySelectorAll("#mod [data-v]").forEach((x) => x.classList.toggle("on", x.dataset.v === best));
			$("#modhint").textContent = best ? "(suggested)" : "";
			vendorFromModule();
		};
		$("#txt").oninput = guess;
		$("#submit").onclick = async (e) => {
			const btn = e.currentTarget;
			const text = $("#txt").value.trim();
			if (!text && !state.picker.shots.length && !state.picker.files.length && !state.picker.uploading) { toast("Add a screenshot or describe the problem", "err"); $("#txt").focus(); return; }
			btn.disabled = true; btn.innerHTML = '<span class="spinner sm"></span> Sending…';
			try {
				await state.picker.whenReady();
				const name = await api("create", { text, site: sel.site, module: sel.module, severity: sel.severity, issue_type: sel.type, images: state.picker.shots, files: state.picker.files,
					vendor: sel.vendor, project: b.project === "all" ? null : b.project });
				toast(`Ticket ${name} created`, "ok");
				await refreshBoot();
				location.hash = "#/t/" + encodeURIComponent(name);
			} catch (err) {
				toast(err.message, "err"); btn.disabled = false; btn.innerHTML = `${ic("send")} Send report`;
			}
		};
	}


	// ------------------------------------------------------------------ team & coverage (project leads)
	async function viewTeam() {
		const b = state.boot;
		if (!b.project || b.project === "all") { toast("Pick a project at the top first", "err"); location.hash = "#/"; return; }
		app.innerHTML = shell(`<div class="skel tall"></div><div class="skel"></div>`, { back: "#/", title: "Team & coverage", nav: false });
		bindShell();
		renderTeam(await api("team", { project: b.project }));
	}

	function teamSheet(title, body, onGo, goLabel) {
		const m = h(`<div class="modal sheet"><div class="sheet-box"><div class="sheet-head"><h3>${esc(title)}</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			${body}<button class="btn primary block" data-go>${esc(goLabel || "Save")}</button></div></div>`);
		document.body.appendChild(m);
		$("[data-x]", m).onclick = () => m.remove();
		m.onclick = (e) => { if (e.target === m) m.remove(); };
		$("[data-go]", m).onclick = async (e) => {
			e.currentTarget.disabled = true;
			try { const t = await onGo(m); m.remove(); if (t) renderTeam(t); } catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
		};
		return m;
	}

	function renderTeam(t) {
		const b = state.boot;
		const opt = (arr, blank) => `<option value="">${esc(blank)}</option>` + arr.map((x) => `<option value="${esc(x.name || x)}">${esc(x.path || x.name || x)}</option>`).join("");
		const people = t.people;
		const own = people.filter((p) => !p.inherited), inh = people.filter((p) => p.inherited);
		const personRow = (p) => `<div class="prow ${p.active ? "" : "off"}">
			<div class="pmain"><b>${esc(p.name)}</b><span class="muted small">${esc(p.user)}</span></div>
			<div class="ptags"><span class="pill gray">${esc(p.role)}</span>${p.vendor ? `<span class="vtag">${esc(p.vendor)}</span>` : ""}${p.inherited ? `<span class="muted small">from ${esc(p.project)}</span>` : ""}${p.active ? "" : `<span class="pill red">inactive</span>`}</div>
			<div class="plims">${p.limits.length ? p.limits.map((l) => `<span class="lim">${esc([l.site || "All sites", l.module || "All areas"].join(" · "))}${p.inherited ? "" : `<button data-unalloc="${esc(l.row)}" aria-label="Remove">${ic("x")}</button>`}</span>`).join("") : `<span class="muted small">Whole project</span>`}
				${p.inherited ? "" : `<button class="btn ghost sm" data-alloc="${esc(p.user)}">${ic("plus")} Limit</button><button class="btn ghost sm" data-active="${esc(p.row)}" data-on="${p.active ? 0 : 1}">${p.active ? "Deactivate" : "Activate"}</button>`}</div></div>`;
		const cols = t.modules;
		app.innerHTML = shell(`
			<section class="team">
				<div class="team-head"><div><h1>${esc(t.project)}</h1><p class="muted">${people.filter((p) => p.active).length} people · ${t.subprojects.length} sub-project${t.subprojects.length === 1 ? "" : "s"} · ${t.uncovered ? `<b class="red">${t.uncovered} site/area combinations with no tester</b>` : "every site/area has a tester"}</p></div></div>

				<h2>Sub-projects</h2>
				<div class="subgrid">${t.subprojects.map((sp) => `<div class="subcard"><b>${esc(sp.name)}</b><span class="muted small">${esc(sp.project_code)} · ${esc(sp.status)}</span>
					<div class="muted small">${sp.open} open · ${sp.members} own member${sp.members === 1 ? "" : "s"}</div>
					<button class="btn ghost sm" data-open="${esc(sp.name)}">Open ${ic("arrow")}</button></div>`).join("")}
					<button class="subcard add" id="newsub">${ic("plus")}<b>New sub-project</b><span class="muted small">Phase, branch or workstream</span></button></div>

				<div class="sec-head"><h2>People</h2><button class="btn ghost sm" id="addp">${ic("plus")} Add person</button></div>
				<p class="muted small">A <b>limit</b> narrows a person to a site (or a group of sites) and/or an area. No limits = the whole project. Members of a parent project also see every sub-project.</p>
				<div class="plist">${own.map(personRow).join("") || `<div class="empty"><p>No one in this project's own team yet.</p></div>`}</div>
				${inh.length ? `<details class="inh"><summary>${inh.length} from parent project${inh.length > 1 ? "s" : ""}</summary><div class="plist">${inh.map(personRow).join("")}</div></details>` : ""}

				<h2>Test coverage <span class="muted small">client testers, UAT users and QA leads per site and area</span></h2>
				<div class="covwrap"><table class="cov"><thead><tr><th>Site</th>${cols.map((c) => `<th><span>${esc(c)}</span></th>`).join("")}</tr></thead>
				<tbody>${t.grid.map((r) => `<tr><th title="${esc(r.path)}">${esc(r.site)}</th>${r.cells.map((c) => `<td class="${c.count ? (c.count === 1 ? "one" : "ok") : "none"}" title="${esc(c.module)}: ${esc(c.who.join(", ") || "nobody")}">${c.count || "–"}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
				<p class="muted small"><span class="key none"></span> nobody · <span class="key one"></span> one person · <span class="key ok"></span> two or more. Hover a cell to see who.</p>
			</section>`, { back: "#/", title: "Team & coverage", nav: false });
		bindShell();
		app.querySelectorAll("[data-open]").forEach((el) => (el.onclick = () => switchProject(el.dataset.open).then(() => { location.hash = "#/team"; })));
		app.querySelectorAll("[data-unalloc]").forEach((el) => (el.onclick = async () => {
			try { renderTeam(await api("unallocate", { project: t.project, row: el.dataset.unalloc })); toast("Limit removed", "ok"); } catch (e) { toast(e.message, "err"); }
		}));
		app.querySelectorAll("[data-active]").forEach((el) => (el.onclick = async () => {
			try { renderTeam(await api("set_member_active", { project: t.project, row: el.dataset.active, active: el.dataset.on })); } catch (e) { toast(e.message, "err"); }
		}));
		app.querySelectorAll("[data-alloc]").forEach((el) => (el.onclick = () => {
			const who = people.find((p) => p.user === el.dataset.alloc);
			teamSheet(`Limit ${who.name}`, `<p class="muted small">They will only see tickets and gaps for this site and area (plus any other limits they have).</p>
				<label class="lbl">Site or group</label><select id="lsite">${opt(t.sites, "All sites")}</select>
				<label class="lbl">Area</label><select id="lmod">${opt(t.modules, "All areas")}</select>
				<label class="lbl">Note (optional)</label><input id="lnote" placeholder="e.g. night shift">`,
				(m) => api("allocate", { project: t.project, user: who.user, site: $("#lsite", m).value || null, module: $("#lmod", m).value || null, note: $("#lnote", m).value || null }),
				"Add limit");
		}));
		$("#addp").onclick = () => teamSheet("Add person", `<label class="lbl">User (email)</label><input id="pu" type="email" placeholder="name@hospital.co.ke">
			<label class="lbl">Role</label><select id="pr">${t.roles.map((r) => `<option ${r === "Tester" ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>
			<label class="lbl">Vendor <span class="muted small">(only for vendor staff)</span></label><select id="pv">${opt(t.vendors, "Client staff (no vendor)")}</select>`,
			(m) => api("add_member", { project: t.project, user: $("#pu", m).value, role: $("#pr", m).value, vendor: $("#pv", m).value || null }), "Add to team");
		$("#newsub").onclick = () => teamSheet("New sub-project", `<label class="lbl">Name</label><input id="sn" placeholder="e.g. Phase 2 - Utawala">
			<label class="lbl">Short code</label><input id="sc" placeholder="e.g. UTW2" maxlength="8">
			<label class="lbl">Sites <span class="muted small">(optional: a group or site; blank = same as parent)</span></label><select id="ss">${opt(t.sites, "Same as parent")}</select>`,
			async (m) => {
				const r = await api("new_subproject", { project: t.project, name: $("#sn", m).value, code: $("#sc", m).value, root_site: $("#ss", m).value || null });
				state.boot = await api("boot", { project: state.project });
				return r;
			}, "Create");
	}


	// ------------------------------------------------------------------ merge duplicates (tickets & gaps)
	function mergeSheet(o) {
		const st = { mode: "into", picked: new Set(), rows: [], txt: "" };
		const m = h(`<div class="modal sheet"><div class="sheet-box merge-box">
			<div class="sheet-head"><h3>${ic("merge")} Merge duplicate ${o.kind}s</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			<div class="seg" id="mmode"><button class="on" data-v="into">Merge others into ${esc(o.name)}</button><button data-v="dup">${esc(o.name)} is a duplicate of…</button></div>
			<div class="search">${ic("search")}<input id="mq" placeholder="Search by number or words"></div>
			<div class="muted small" id="mlabel">Similar ${o.kind}s</div>
			<div class="mlist" id="mlist"><div class="skel"></div></div>
			<p class="muted small">Screenshots, recordings, files, links and the full history are copied into the ${o.kind} you keep. The duplicates are marked <b>Merged</b> and point to it. Their reporters are told, and their chat replies go to the kept ${o.kind}. The highest severity / priority is kept.</p>
			<button class="btn primary block" id="mgo" disabled>${ic("merge")} Merge</button></div></div>`);
		document.body.appendChild(m);
		const close = () => m.remove();
		$("[data-x]", m).onclick = close;
		m.onclick = (e) => { if (e.target === m) close(); };
		const btnText = () => {
			const n = st.picked.size, b = $("#mgo", m);
			b.disabled = !n;
			if (st.mode === "into") b.innerHTML = `${ic("merge")} ${n ? `Merge ${n} ${o.kind}${n > 1 ? "s" : ""} into ${esc(o.name)}` : "Pick the duplicates"}`;
			else b.innerHTML = `${ic("merge")} ${n ? `Merge ${esc(o.name)} into ${esc([...st.picked][0])}` : `Pick the ${o.kind} to keep`}`;
		};
		const draw = () => {
			const list = $("#mlist", m);
			if (!st.rows.length) { list.innerHTML = `<div class="empty"><p>${st.txt ? "Nothing found." : `No similar ${o.kind}s found. Search by number or words.`}</p></div>`; btnText(); return; }
			const type = st.mode === "into" ? "checkbox" : "radio";
			list.innerHTML = st.rows.map((r) => `<label class="mrow"><input type="${type}" name="mpick" value="${esc(r.name)}" ${st.picked.has(r.name) ? "checked" : ""}>
				<span class="mtxt"><b>${esc(r.name)}</b> ${esc(r.title)}<em>${esc([r.status, r.site, r.module].filter(Boolean).join(" · "))}</em></span>
				${r.score ? `<span class="mscore" title="similarity">${Math.round(r.score * 100)}%</span>` : ""}</label>`).join("");
			list.querySelectorAll("input").forEach((inp) => (inp.onchange = () => {
				if (type === "radio") st.picked = new Set([inp.value]);
				else if (inp.checked) st.picked.add(inp.value); else st.picked.delete(inp.value);
				btnText();
			}));
			btnText();
		};
		const load = async () => {
			try { st.rows = await o.candidates(st.txt); } catch (e) { st.rows = []; toast(e.message, "err"); }
			$("#mlabel", m).textContent = st.txt ? "Search results" : `Similar ${o.kind}s`;
			draw();
		};
		m.querySelectorAll("#mmode [data-v]").forEach((b) => (b.onclick = () => {
			st.mode = b.dataset.v; st.picked = new Set();
			m.querySelectorAll("#mmode [data-v]").forEach((x) => x.classList.toggle("on", x === b));
			draw();
		}));
		let timer;
		$("#mq", m).oninput = (e) => { clearTimeout(timer); timer = setTimeout(() => { st.txt = e.target.value.trim(); load(); }, 300); };
		$("#mgo", m).onclick = async (e) => {
			const btn = e.currentTarget;
			const picked = [...st.picked];
			const target = st.mode === "into" ? o.name : picked[0];
			const sources = st.mode === "into" ? picked : [o.name];
			btn.disabled = true; btn.innerHTML = '<span class="spinner sm"></span> Merging…';
			try {
				const r = await o.merge(target, sources);
				toast(`Merged ${r.merged.join(", ")} into ${r.target}`, "ok");
				close();
				o.open(r.target);
			} catch (err) { toast(err.message, "err"); btnText(); }
		};
		load();
	}


	function escalateSheet(t, e) {
		const m = h(`<div class="modal sheet"><div class="sheet-box"><div class="sheet-head"><h3>${esc(e.label)}</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			<p class="muted small">${e.up ? `Hand ${esc(t.name)} to ${esc(e.to)} support. Say what you already checked so they don't repeat it.` : `Return ${esc(t.name)} to ${esc(e.to)}, e.g. it's a training or data issue, not a system fault.`}</p>
			<label class="lbl">${e.up ? "What was checked, and what is needed?" : "Why is it going back?"}</label><textarea id="en" rows="3"></textarea>
			${(t.developers || []).length ? `<label class="lbl">Assign to <span class="muted small">(optional)</span></label><select id="ed"><option value="">Keep ${t.developer ? esc(t.developer) : "unassigned"}</option>${t.developers.map((d) => `<option value="${esc(d.value)}">${esc(d.label)}</option>`).join("")}</select>` : ""}
			<button class="btn primary block" data-go>${ic(e.up ? "up" : "down")} ${esc(e.label)}</button></div></div>`);
		document.body.appendChild(m);
		$("[data-x]", m).onclick = () => m.remove();
		m.onclick = (ev) => { if (ev.target === m) m.remove(); };
		$("[data-go]", m).onclick = async (ev) => {
			ev.currentTarget.disabled = true;
			try {
				await api("escalate", { name: t.name, level: e.to, note: $("#en", m).value, assigned_to: ($("#ed", m) || {}).value || null });
				m.remove(); toast(`${t.name} moved to ${e.to}`, "ok"); viewTicket(t.name);
			} catch (err) { toast(err.message, "err"); ev.currentTarget.disabled = false; }
		};
	}

	// ------------------------------------------------------------------ ticket
	async function viewTicket(name) {
		app.innerHTML = shell(`<div class="skel tall"></div><div class="skel"></div>`, { back: "#/", title: esc(name), nav: false });
		bindShell();
		const t = await api("ticket", { name });
		renderTicket(t);
	}

	function renderTicket(t) {
		const gal = (arr, label) => arr.length ? `<div class="gal-l">${label}</div><div class="gal">${arr.map((s) => `<img src="${esc(s)}" data-lb="${esc(s)}" alt="" loading="lazy">`).join("")}</div>` : "";
		const meta = [t.project, t.vendor, t.site, t.module, t.type === "Query" ? "Question" : null, t.support_level ? "Support " + t.support_level : null].filter(Boolean).map(esc).join(" · ");
		const tl = t.timeline.filter((u) => u.type !== "Status Change" || true);
		app.innerHTML = shell(`
			<section class="tkt">
				<div class="tkt-head"><span class="muted">${sevDot(t.severity)}${esc(t.name)}${t.code ? " · " + esc(t.code) : ""}</span>${stagePill(t.status)}</div>
				<h1>${esc(t.title)}</h1>
				${t.merged_into ? `<a class="mergedban" href="#/t/${encodeURIComponent(t.merged_into)}">${ic("merge")}<span>This ticket was a duplicate and was merged into <b>${esc(t.merged_into)}</b>. Follow that ticket.</span>${ic("arrow")}</a>` : ""}
				${(t.similar || []).length ? `<div class="dupban">${ic("merge")}<span>Possible duplicate${t.similar.length > 1 ? "s" : ""}: ${t.similar.map((x) => `<a href="#/t/${encodeURIComponent(x.name)}" title="${esc(x.title)}">${esc(x.name)}</a>`).join(", ")}</span><button class="btn ghost sm" data-merge>Review & merge</button></div>` : ""}
				<div class="muted small">${meta}${t.reporter ? ` · reported by ${esc(t.reporter)}` : ""} · ${esc(t.reported_ago)}${t.channel ? " via " + esc(t.channel) : ""}</div>
				${(t.merged_from || []).length ? `<div class="muted small">Includes merged ${t.merged_from.map((x) => `<a href="#/t/${encodeURIComponent(x.name)}" title="${esc(x.title)}">${esc(x.name)}</a>`).join(", ")}</div>` : ""}
				${t.target_date ? `<div class="due ${t.overdue ? "late" : ""}">${ic("timer")} Fix due ${esc(t.target_date)}${t.overdue ? " · overdue" : ""}</div>` : ""}
				<div class="stagebox">${stageBar(t.stage, true)}</div>
				${(t.escalate || []).length ? `<div class="esc-row"><span class="lvl lvl-${esc(t.support_level)}">${esc(t.support_level)}</span>${t.escalate.map((e, i) => `<button class="btn ghost sm" data-esc="${i}">${ic(e.up ? "up" : "down")}${esc(e.label)}</button>`).join("")}</div>` : ""}
				${t.actions.length ? `<div class="actions">${t.actions.map((a, i) => `<button class="btn ${a.style}" data-a="${i}" ${a.hint ? `title="${esc(a.hint)}"` : ""}>${a.style === "success" ? ic("check") : a.style === "danger" ? ic("x") : ""}${esc(a.label)}</button>`).join("")}</div>
				${t.actions.some((a) => a.hint) ? `<p class="muted small act-hints">${t.actions.filter((a) => a.hint).map((a) => `<b>${esc(a.label)}</b>: ${esc(a.hint)}`).join(" · ")}</p>` : ""}` : ""}
				${t.developer ? `<div class="kv"><span>Developer</span><b>${esc(t.developer)}</b></div>` : ""}
				${t.resolution ? `<div class="note"><div class="muted small">${t.status === "Answered" ? "Answer" : "Fix"}${t.fixed_in_build ? " · build " + esc(t.fixed_in_build) : ""}</div>${esc(t.resolution)}</div>` : ""}
				${t.description ? `<div class="desc">${t.description}</div>` : ""}
				${gal(t.shots.reported, "Screenshots")}${gal(t.shots.retest, "Retest screenshots")}${gal(t.shots.uat, "UAT screenshots")}
				${(t.files || []).length ? `<div class="gal-l">Files</div><div class="doc-list">${t.files.map((f) => `<a class="doc-chip" href="${esc(f.url)}" target="_blank" rel="noopener"><span class="doc-ic k-${docKind(f.name).toLowerCase()}">${esc(docKind(f.name))}</span><span class="doc-name">${esc(f.name)}<em>${esc(f.caption || "")}</em></span></a>`).join("")}</div>` : ""}
				${(t.recordings || []).length ? `<div class="gal-l">Screen recordings</div><div class="vids">${t.recordings.map((r) => `<figure><video src="${esc(r.url)}" controls preload="metadata" playsinline></video><figcaption>${esc(r.caption || "")}${r.duration ? " · " + esc(r.duration) : ""}</figcaption></figure>`).join("")}</div>` : ""}
			</section>
			<section class="timeline"><h3>Updates</h3>
				${tl.length ? tl.map((u) => u.type === "Status Change"
					? `<div class="sys">${esc(u.text)} · ${esc(u.ago)}</div>`
					: `<div class="bubble ${u.mine ? "mine" : ""} ${(u.party || "").toLowerCase()}"><div class="b-head"><b>${esc(u.by || u.party)}</b><span>${esc(u.party)}${u.channel && u.channel !== "Web" ? " · " + esc(u.channel) : ""} · ${esc(u.ago)}</span></div>
						${u.text ? `<div class="b-text">${esc(u.text)}</div>` : ""}${u.image ? `<img src="${esc(u.image)}" data-lb="${esc(u.image)}" alt="" loading="lazy">` : ""}${u.video ? `<video class="b-vid" src="${esc(u.video)}" controls preload="metadata" playsinline></video>` : ""}${u.file ? `<a class="doc-chip in-bubble" href="${esc(u.file.url)}" target="_blank" rel="noopener"><span class="doc-ic k-${docKind(u.file.name).toLowerCase()}">${esc(docKind(u.file.name))}</span><span class="doc-name">${esc(u.file.name)}</span></a>` : ""}</div>`).join("")
					: `<p class="muted">No updates yet.</p>`}
			</section>
			${t.can_update ? `<div class="composer" id="comp"><div class="thumbs"></div><div class="c-row">
				<button class="iconbtn" id="attach" aria-label="Attach screenshot">${ic("clip")}</button>
				<button class="iconbtn" id="cam" aria-label="Camera">${ic("cam")}</button>
				${canCaptureScreen ? `<button class="iconbtn" id="scr" aria-label="Capture screen" title="Capture screenshot">${ic("desk")}</button>` : ""}
				${canRecordScreen ? `<button class="iconbtn rec-ic" id="rcd" aria-label="Record screen" title="Record screen">${ic("rec")}</button>` : ""}
				<textarea id="msg" rows="1" placeholder="Add an update…"></textarea>
				<button class="iconbtn send" id="sendu" aria-label="Send">${ic("send")}</button></div></div>` : ""}
			${t.can_merge ? `<p class="center"><button class="btn ghost sm" data-merge>${ic("merge")} Merge duplicates…</button></p>` : ""}
			${state.boot.desk ? `<p class="center"><a class="muted small" href="${esc(t.desk_url)}">Open in Desk</a></p>` : ""}`,
			{ back: "#/", title: esc(t.name), nav: false });
		bindShell();
		app.querySelectorAll("[data-lb]").forEach((im) => (im.onclick = () => lightbox(im.dataset.lb)));
		app.querySelectorAll("[data-a]").forEach((b) => (b.onclick = () => actionDialog(t, t.actions[+b.dataset.a])));
		app.querySelectorAll("[data-esc]").forEach((b) => (b.onclick = () => escalateSheet(t, t.escalate[+b.dataset.esc])));
		app.querySelectorAll("[data-merge]").forEach((b) => (b.onclick = () => mergeSheet({
			kind: "ticket", name: t.name, title: t.title,
			candidates: (txt) => api("merge_candidates", { name: t.name, txt: txt || null }),
			merge: (target, sources) => api("merge", { target, sources }),
			open: (n) => { location.hash = "#/t/" + encodeURIComponent(n); viewTicket(n); },
		})));
		const comp = $("#comp");
		if (comp) {
			state.picker = shotPicker(comp);
			$("#attach").onclick = () => state.picker.pick();
			$("#cam").onclick = () => state.picker.camera();
			if ($("#scr")) $("#scr").onclick = () => state.picker.screen();
			if ($("#rcd")) $("#rcd").onclick = () => state.picker.record();
			const msg = $("#msg");
			msg.oninput = () => { msg.style.height = "auto"; msg.style.height = Math.min(140, msg.scrollHeight) + "px"; };
			$("#sendu").onclick = async (e) => {
				const text = msg.value.trim();
				if (!text && !state.picker.shots.length && !state.picker.files.length && !state.picker.uploading) { msg.focus(); return; }
				e.currentTarget.disabled = true;
				try {
					await state.picker.whenReady();
					const nt = await api("update", { name: t.name, text, images: state.picker.shots, files: state.picker.files });
					toast("Update posted", "ok");
					state.picker.destroy(); state.picker = null;
					renderTicket(nt);
					setTimeout(() => window.scrollTo(0, document.body.scrollHeight), 50);
				} catch (err) { toast(err.message, "err"); e.currentTarget.disabled = false; }
			};
		}
	}

	function actionDialog(t, a) {
		const needsForm = a.notes || a.build || a.shots || a.kind === "assign";
		const run = async (vals, btn) => {
			if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner sm"></span>'; }
			try {
				const nt = await api("act", Object.assign({ name: t.name, action: a.action }, vals || {}));
				toast(`${a.label}: done`, "ok");
				await refreshBoot();
				if (state.picker) { state.picker.destroy(); state.picker = null; }
				renderTicket(nt);
				return true;
			} catch (err) { toast(err.message, "err"); if (btn) { btn.disabled = false; btn.textContent = a.label; } return false; }
		};
		if (!needsForm) return run({});
		const m = h(`<div class="modal sheet"><div class="sheet-box">
			<div class="sheet-head"><h3>${esc(a.label)}</h3><button class="iconbtn" data-x aria-label="Close">${ic("x")}</button></div>
			${a.hint ? `<p class="muted small">${esc(a.hint)}</p>` : ""}
			${a.kind === "assign" && !t.developers.length ? `<p class="cap-warn small">No user has the Vendor Developer role yet. Add one in Desk → User.</p>` : ""}
			${a.kind === "assign" ? `<label class="lbl">Developer</label><select id="dev">${t.developers.map((d) => `<option value="${esc(d.value)}" ${d.value === t.assigned_to ? "selected" : ""}>${esc(d.label)}</option>`).join("")}</select>` : ""}
			${a.notes ? `<label class="lbl">${esc(a.notes)}</label><textarea id="an" rows="3"></textarea>` : ""}
			${a.build ? `<label class="lbl">Build / version</label><input id="ab" placeholder="1.4.3" value="${esc(t.fixed_in_build || "")}">` : ""}
			${a.shots ? `<div class="shots small" id="ashots"><div class="drop">${ic("cam")}<span>Add screenshots (optional) · paste or drop</span></div>${sourceButtons(true)}<div class="thumbs"></div></div>` : ""}
			<button class="btn ${a.style} block" data-go>${esc(a.label)}</button></div></div>`);
		document.body.appendChild(m);
		const prev = state.picker;
		const picker = a.shots ? shotPicker($("#ashots", m)) : null;
		const close = () => { if (picker) picker.destroy(); m.remove(); };
		$("[data-x]", m).onclick = close;
		m.onclick = (e) => { if (e.target === m) close(); };
		$("[data-go]", m).onclick = async (e) => {
			const notes = $("#an", m) ? $("#an", m).value.trim() : null;
			if (a.notes_required && !notes) { toast("Please add a note", "err"); $("#an", m).focus(); return; }
			if (picker) await picker.whenReady();
			const ok = await run({ notes, build: $("#ab", m) ? $("#ab", m).value.trim() : null, assigned_to: $("#dev", m) ? $("#dev", m).value : null, images: picker ? picker.shots : [], files: picker ? picker.files : [] }, e.currentTarget);
			if (ok) close(); else if (prev) state.picker = prev;
		};
	}

	// ------------------------------------------------------------------ test runs
	async function viewRuns() {
		app.innerHTML = shell(`<section class="hello"><h1>Your test runs</h1><p>Run each test and record the result.</p></section><div id="rl" class="list"><div class="skel"></div></div>`, { tab: "runs" });
		bindShell();
		const rows = await api("runs");
		const col = { "Pass": "green", "Fail": "red", "Blocked": "amber", "Skipped": "gray", "Not Run": "blue" };
		$("#rl").innerHTML = rows.length ? rows.map((r) => `<a class="card run" href="#/r/${encodeURIComponent(r.name)}">
			<div class="tk-top"><span class="muted">${esc(r.test_case)} · ${esc(r.module || "")}</span><span class="pill ${col[r.result] || "gray"}">${esc(r.result)}</span></div>
			<div class="tk-title">${esc(r.case_title || r.test_case)}</div><div class="muted small">${esc(r.test_cycle)} · ${esc(r.ago)}${r.issue ? " · " + esc(r.issue) : ""}</div></a>`).join("")
			: `<div class="empty"><h3>No test runs assigned</h3><p>Your QA lead assigns test runs from a test cycle.</p></div>`;
	}

	async function viewRun(name) {
		const r = await api("run", { name });
		app.innerHTML = shell(`<section class="tkt">
			<div class="tkt-head"><span class="muted">${esc(r.case)} · ${esc(r.cycle)}</span><span class="pill gray">${esc(r.result)}</span></div>
			<h1>${esc(r.title || r.case)}</h1>
			<div class="note"><div class="muted small">Steps</div><div class="desc">${r.steps || ""}</div></div>
			<div class="note"><div class="muted small">Expected result</div>${esc(r.expected || "")}</div>
			${r.issue ? `<p><a href="#/t/${encodeURIComponent(r.issue)}" class="btn ghost">View raised ticket ${esc(r.issue)}</a></p>` : ""}
			<label class="lbl" for="act">What actually happened? (needed if it fails)</label><textarea id="act" rows="3">${esc(r.actual || "")}</textarea>
			<div class="shots small" id="rshots"><div class="drop">${ic("cam")}<span>Add screenshots · paste or drop</span></div>${sourceButtons(true)}<div class="thumbs"></div></div>
			<div class="actions three"><button class="btn success" data-r="Pass">${ic("check")}Pass</button><button class="btn danger" data-r="Fail">${ic("x")}Fail</button><button class="btn secondary" data-r="Blocked">Blocked</button></div>
			</section>`, { back: "#/runs", title: "Test run", nav: false });
		bindShell();
		state.picker = shotPicker($("#rshots"));
		app.querySelectorAll("[data-r]").forEach((b) => (b.onclick = async () => {
			const actual = $("#act").value.trim();
			if (b.dataset.r !== "Pass" && !actual) { toast("Describe what actually happened", "err"); $("#act").focus(); return; }
			b.disabled = true;
			try {
				await state.picker.whenReady();
				const res = await api("run_result", { name, result: b.dataset.r, actual, images: state.picker.shots, files: state.picker.files });
				await refreshBoot();
				if (res.issue) { toast(`Saved. Ticket ${res.issue} raised`, "ok"); location.hash = "#/t/" + encodeURIComponent(res.issue); }
				else { toast("Saved", "ok"); location.hash = "#/runs"; }
			} catch (err) { toast(err.message, "err"); b.disabled = false; }
		}));
	}

	// ------------------------------------------------------------------ shared API for add-on screens (gaps.js)
	window.QAP = Object.assign(window.QAP || {}, {
		api, $, esc, h, ic, toast, shell, bindShell, shotPicker, annotate, lightbox, state, refreshBoot, sourceButtons, docKind,
		canCaptureScreen, canRecordScreen, canFloat, mergeSheet, sevDot, stagePill, stageBar, switchProject, project: () => state.project, boot: () => state.boot,
		get app() { return app; },
		setPicker(p) { if (state.picker) state.picker.destroy(); state.picker = p; },
		routes: (window.QAP && window.QAP.routes) || {},
	});

	// ------------------------------------------------------------------ start
	window.addEventListener("hashchange", route);
	refreshBoot().then(route).catch((e) => {
		app.innerHTML = `<div class="empty pad"><h3>Can't open QA Tracker</h3><p>${esc(e.message)}</p><a class="btn primary" href="/login?redirect-to=/qa">Log in</a></div>`;
	});
})();
