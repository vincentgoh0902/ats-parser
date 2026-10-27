// Resume editor: edit what the parser read, check it, download a clean PDF.
// Uses $, h, state, render and jdInput from app.js. Text goes in with
// textContent / .value only, never innerHTML.

const ed = {
  resume: null,      // the form's data (same shape as /api/render takes)
  check: null,       // last /api/check result
  checking: false,
  stale: false,      // edited since the last check
  dirty: false,      // edited since the parse; warn before leaving
  confirmed: new Set(),  // missing keywords the user says they have used
  dismissed: new Set(),
  pdfUrl: null,
  firstScore: null,  // match score of the first check, to show the change
  timer: null,
};

// ---- paths like "sections.1.entries.0.bullets.2" ----
function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? o : o[/^\d+$/.test(k) ? Number(k) : k]), obj);
}
function setPath(obj, path, value) {
  const keys = path.split(".");
  const last = keys.pop();
  const parent = getPath(obj, keys.join("."));
  parent[/^\d+$/.test(last) ? Number(last) : last] = value;
}
const field = (path) => document.querySelector(`#tab-edit [data-path="${path}"]`);

function editorStart(resume) {
  ed.resume = structuredClone(resume);
  ed.check = null;
  ed.stale = true;
  ed.dirty = false;
  ed.confirmed.clear();
  ed.dismissed.clear();
  ed.firstScore = null;
}

window.addEventListener("beforeunload", (e) => { if (ed.dirty) e.preventDefault(); });

// ---- server calls ----
async function postJson(url, body) {
  const res = await fetch(url, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `Error ${res.status}`);
  }
  return res;
}

async function runCheck() {
  clearTimeout(ed.timer);
  if (ed.checking) { ed.timer = setTimeout(runCheck, 400); return; }
  ed.checking = true;
  editorStatus("Checking…");
  try {
    const jd = jdInput.value.trim();
    const [checkRes, pdfRes] = await Promise.all([
      postJson("/api/check", { resume: ed.resume, job_description: jd }),
      postJson("/api/render", ed.resume),
    ]);
    ed.check = await checkRes.json();
    if (ed.firstScore === null && ed.check.match) ed.firstScore = ed.check.match.score;
    if (ed.pdfUrl) URL.revokeObjectURL(ed.pdfUrl);
    ed.pdfUrl = URL.createObjectURL(await pdfRes.blob());
    ed.stale = false;
    editorStatus("");
  } catch (err) {
    editorStatus(err.message, true);
  } finally {
    ed.checking = false;
  }
  if (state.tab === "edit") { renderCheck(); renderLeft(); }
}

function scheduleCheck() {
  ed.stale = true;
  ed.dirty = true;
  clearTimeout(ed.timer);
  ed.timer = setTimeout(runCheck, 1200);
}

async function download() {
  try {
    const res = await postJson("/api/render", ed.resume);
    const url = URL.createObjectURL(await res.blob());
    const base = (ed.resume.contact.name || "resume").trim().replace(/[^\w.-]+/g, "_");
    const a = h("a", { href: url, download: `${base}.pdf` });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    ed.dirty = false;
  } catch (err) {
    editorStatus(err.message, true);
  }
}

function editorStatus(msg, isError = false) {
  const el = $("#ed-status");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", isError);
}

// ---- the tab ----
function renderEditor() {
  if (!ed.resume) return h("p", { class: "muted" }, "Upload a resume first.");
  if (ed.stale && !ed.checking) queueMicrotask(runCheck);
  else queueMicrotask(renderCheck);
  const r = ed.resume;
  return [
    h("p", { class: "legend muted" },
      "Edit your resume here and download it as a clean, single-column PDF that ATSs read well. ",
      "It's rebuilt from the text, so your original design isn't kept. Nothing is saved on the server."),
    h("div", { class: "ed-bar" },
      h("button", { type: "button", class: "btn", id: "ed-download" }, "Download PDF"),
      h("button", { type: "button", class: "btn ghost", id: "ed-check" }, "Check again"),
      h("div", { class: "seg", id: "ed-size" },
        h("button", { type: "button", "data-size": "letter", class: r.page_size !== "a4" ? "on" : null }, "Letter"),
        h("button", { type: "button", "data-size": "a4", class: r.page_size === "a4" ? "on" : null }, "A4")),
      h("span", { id: "ed-status", class: "muted small" })),
    h("div", { id: "ed-check-out" }),
    h("h3", {}, "Your resume"),
    h("div", { id: "ed-form" }, formView(r)),
  ];
}

// ---- check results: score, read-back problems, suggestions ----
function renderCheck() {
  const out = $("#ed-check-out");
  if (!out) return;
  const c = ed.check;
  if (!c) return out.replaceChildren();
  const parts = [];

  const stats = [h("span", {}, `${c.pages} page${c.pages > 1 ? "s" : ""}`)];
  if (c.match) {
    const delta = ed.firstScore !== null ? c.match.score - ed.firstScore : 0;
    stats.push(h("span", { class: `match-pill ${c.match.band}` }, `Job match ${c.match.score}/100`,
      delta ? h("span", { class: delta > 0 ? "up" : "down" }, ` ${delta > 0 ? "+" : ""}${delta}`) : null));
  }
  stats.push(c.mismatches.length
    ? h("span", { class: "tag warn" }, `${c.mismatches.length} field${c.mismatches.length > 1 ? "s" : ""} read differently`)
    : h("span", { class: "tag ok" }, "reads back exactly as written"));
  parts.push(h("div", { class: "ed-stats" }, stats));

  if (c.mismatches.length) {
    parts.push(h("h3", {}, "Fix these first"),
      h("p", { class: "legend muted" }, "These fields don't come back the way you wrote them when the PDF is parsed."),
      h("ul", { class: "ed-list" }, c.mismatches.map((m) => h("li", {},
        h("button", { type: "button", class: "linkish", "data-goto": m.path }, labelFor(m.path)),
        `: ${m.hint}`,
        m.read ? h("span", { class: "muted" }, ` (read as “${m.read}”)`) : null))));
  }

  const sgs = c.suggestions.filter((s) => !ed.dismissed.has(key(s)));
  const quick = sgs.filter((s) => s.kind === "wording" || s.kind === "implied");
  const evidence = sgs.filter((s) => s.kind === "evidence");
  const missing = sgs.filter((s) => s.kind === "missing");

  if (quick.length) {
    parts.push(h("h3", {}, "Quick fixes"),
      h("p", { class: "legend muted" }, "Same facts, in the job's words. Check each one reads right."),
      ...quick.map((s) => h("div", { class: "sg-card" },
        h("p", {}, s.text),
        diffView(s.before, s.after),
        h("div", { class: "sg-actions" },
          h("button", { type: "button", class: "btn small", "data-apply": key(s) }, "Apply"),
          h("button", { type: "button", class: "linkish", "data-goto": s.path }, "Show"),
          h("button", { type: "button", class: "linkish", "data-dismiss": key(s) }, "Dismiss")))));
  }
  if (evidence.length) {
    parts.push(h("h3", {}, "Show it in use"),
      ...evidence.map((s) => h("div", { class: "sg-card" },
        h("p", {}, s.text),
        s.why && h("p", { class: "muted small" }, `Suggested because this bullet ${s.why}.`),
        h("div", { class: "sg-actions" },
          h("button", { type: "button", class: "linkish", "data-goto": s.path }, "Go to bullet"),
          h("button", { type: "button", class: "linkish", "data-dismiss": key(s) }, "Dismiss")))));
  }
  if (missing.length) {
    parts.push(h("h3", {}, "Missing keywords"),
      h("p", { class: "legend muted" },
        "Only add a keyword you have really used. Recruiters ask about everything on your resume."),
      ...missing.map((s) => {
        const ok = ed.confirmed.has(s.term);
        return h("div", { class: `sg-card missing-card ${ok ? "open" : ""}` },
          h("label", { class: "confirm" },
            h("input", { type: "checkbox", "data-confirm": s.term, checked: ok ? "" : null }),
            h("strong", {}, s.label), h("span", { class: "muted small" }, ` · ${s.importance === "preferred" ? "nice to have" : "required"}`),
            h("span", { class: "muted small" }, " · I have used this")),
          ok && h("div", { class: "sg-more" },
            s.fits.length
              ? [h("p", { class: "small" }, "Where it could go. Say how you used it, in your own words:"),
                h("ul", { class: "ed-list" }, s.fits.map((f) => h("li", {},
                  h("button", { type: "button", class: "linkish", "data-goto": f.path }, labelFor(f.path)),
                  f.why ? h("span", { class: "muted small" }, ` (${f.why})`) : null)))]
              : h("p", { class: "small muted" }, "No bullet is an obvious fit. Add it to the bullet where you used it."),
            s.add_to && h("button", { type: "button", class: "btn small ghost", "data-add": key(s) }, `Add “${s.add}” to Skills`)));
      }));
  }
  if (c.match && !sgs.length) parts.push(h("p", { class: "all-clear" }, "No more keyword suggestions for this job."));
  if (!c.match) parts.push(h("p", { class: "muted small" }, "Paste a job description above to get keyword suggestions."));
  out.replaceChildren(...parts);
  markFields();
}

const key = (s) => `${s.kind}:${s.term}:${s.path || ""}`;

function diffView(before, after) {
  // Show only the changed middle, with a little context either side.
  let i = 0;
  while (i < before.length && before[i] === after[i]) i++;
  let j = 0;
  while (j < before.length - i && before[before.length - 1 - j] === after[after.length - 1 - j]) j++;
  const ctx = (s) => (s.length > 40 ? "…" + s.slice(-40) : s);
  const tail = (s) => (s.length > 40 ? s.slice(0, 40) + "…" : s);
  return h("p", { class: "diff" },
    ctx(before.slice(0, i)),
    before.slice(i, before.length - j) && h("del", {}, before.slice(i, before.length - j)),
    h("ins", {}, after.slice(i, after.length - j)),
    tail(before.slice(before.length - j)));
}

function labelFor(path) {
  const p = path.split(".");
  if (p[0] === "contact") return { name: "Name", email: "Email", phone: "Phone", location: "Location", links: "Link" }[p[1]] || p[1];
  const s = ed.resume.sections[Number(p[1])];
  if (!s) return path;
  if (p[2] === "entries") {
    const e = s.entries[Number(p[3])];
    const what = e ? (e.title || e.org || "entry") : "entry";
    if (p[4] === "bullets") return `${what}, bullet ${Number(p[5]) + 1}`;
    return `${what}, ${{ title: "title", org: "company", location: "location", dates: "dates" }[p[4]] || p[4]}`;
  }
  if (p[2] === "schools") {
    const e = s.schools[Number(p[3])];
    return `${e?.school || "school"}, ${p[4] === "details" ? `line ${Number(p[5]) + 1}` : p[4]}`;
  }
  if (p[2] === "items" && p.length > 3) return `${s.heading}, line ${Number(p[3]) + 1}`;
  return s.heading;
}

// Flag fields an ATS reads differently, in place.
function markFields() {
  document.querySelectorAll("#tab-edit .flagged").forEach((el) => {
    el.classList.remove("flagged");
    el.removeAttribute("title");
  });
  for (const m of ed.check?.mismatches || []) {
    const el = field(m.path) || field(m.path.split(".").slice(0, -1).join("."));
    if (el) { el.classList.add("flagged"); el.title = m.hint; }
  }
}

function goTo(path) {
  const el = field(path) || field(path.split(".").slice(0, -1).join("."));
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  el.focus({ preventScroll: true });
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}

// ---- the form ----
function textField(path, label, { area = false, placeholder = "" } = {}) {
  const value = getPath(ed.resume, path) ?? "";
  const attrs = { "data-path": path, placeholder, "aria-label": label };
  const el = area ? h("textarea", { ...attrs, rows: "2" }) : h("input", { ...attrs, type: "text" });
  el.value = value;
  return el;
}

function csvInput(path, label) {
  const el = h("textarea", { "data-path": path, "data-csv": "", rows: "3", "aria-label": label });
  el.value = (getPath(ed.resume, path) || []).join(", ");
  return el;
}

const rm = (path, label) => h("button", { type: "button", class: "icon-btn", "data-remove": path, title: `Remove ${label}`, "aria-label": `Remove ${label}` }, "×");

function listEditor(path, label, addLabel) {
  const items = getPath(ed.resume, path) || [];
  return h("div", { class: "ed-bullets" },
    items.map((_, k) => h("div", { class: "ed-bullet" },
      h("span", { class: "dot" }, "•"),
      textField(`${path}.${k}`, `${label} ${k + 1}`, { area: true }),
      rm(`${path}.${k}`, `${label} ${k + 1}`))),
    h("button", { type: "button", class: "linkish small", "data-push": path }, `+ ${addLabel}`));
}

function formView(r) {
  const out = [
    h("fieldset", { class: "ed-card" },
      h("legend", {}, "Contact"),
      h("div", { class: "grid2" },
        textField("contact.name", "Name", { placeholder: "Full name" }),
        textField("contact.email", "Email", { placeholder: "Email" }),
        textField("contact.phone", "Phone", { placeholder: "+65 9123 4567" }),
        textField("contact.location", "Location", { placeholder: "City, Region" })),
      h("p", { class: "group-label" }, "Links"),
      listEditor("contact.links", "Link", "Add link")),
  ];
  r.sections.forEach((s, i) => {
    const base = `sections.${i}`;
    const body = [];
    if (s.kind === "text") body.push(textField(`${base}.text`, s.heading, { area: true }));
    if (s.kind === "entries") {
      s.entries.forEach((e, j) => {
        const p = `${base}.entries.${j}`;
        body.push(h("div", { class: "ed-entry" },
          h("div", { class: "ed-entry-head" },
            h("div", { class: "grid2" },
              textField(`${p}.title`, "Title", { placeholder: "Title" }),
              textField(`${p}.org`, "Company", { placeholder: s.key === "experience" ? "Company" : "Organisation" }),
              textField(`${p}.dates`, "Dates", { placeholder: "Jan 2023 – Present" }),
              textField(`${p}.location`, "Location", { placeholder: "City, Region (optional)" })),
            rm(p, "entry")),
          listEditor(`${p}.bullets`, "Bullet", "Add bullet")));
      });
      body.push(h("button", { type: "button", class: "linkish small", "data-push-entry": base }, "+ Add entry"));
    }
    if (s.kind === "education") {
      s.schools.forEach((e, j) => {
        const p = `${base}.schools.${j}`;
        body.push(h("div", { class: "ed-entry" },
          h("div", { class: "ed-entry-head" },
            h("div", { class: "grid2" },
              textField(`${p}.school`, "School", { placeholder: "School" }),
              textField(`${p}.degree`, "Degree", { placeholder: "Bachelor of Science in …" }),
              textField(`${p}.dates`, "Dates", { placeholder: "Aug 2020 – May 2024" }),
              textField(`${p}.gpa`, "GPA", { placeholder: "GPA: 3.8/4.0 (optional)" }),
              textField(`${p}.location`, "Location", { placeholder: "City, Region (optional)" })),
            rm(p, "school")),
          listEditor(`${p}.details`, "Detail", "Add detail")));
      });
      body.push(h("button", { type: "button", class: "linkish small", "data-push-school": base }, "+ Add school"));
    }
    if (s.kind === "skills") body.push(csvInput(`${base}.items`, "Skills, comma separated"));
    if (s.kind === "list") body.push(listEditor(`${base}.items`, "Item", "Add line"));
    out.push(h("fieldset", { class: "ed-card" },
      h("legend", {}, s.heading,
        i > 0 && h("button", { type: "button", class: "icon-btn", "data-up": String(i), title: "Move section up", "aria-label": `Move ${s.heading} up` }, "↑")),
      body));
  });
  return out;
}

function redrawForm() {
  const y = window.scrollY;
  $("#ed-form").replaceChildren(...formView(ed.resume));
  markFields();
  window.scrollTo(0, y);
}

// ---- events ----
document.addEventListener("input", (e) => {
  const el = e.target.closest("#tab-edit [data-path]");
  if (!el) return;
  const value = el.hasAttribute("data-csv")
    ? el.value.split(",").map((x) => x.trim()).filter(Boolean)
    : el.value;
  setPath(ed.resume, el.dataset.path, value);
  scheduleCheck();
});

document.addEventListener("click", (e) => {
  if (!e.target.closest("#tab-edit")) return;
  const b = e.target.closest("button, input[type=checkbox]");
  if (!b) return;
  const d = b.dataset;
  const find = (k) => ed.check?.suggestions.find((s) => key(s) === k);

  if (b.id === "ed-download") return download();
  if (b.id === "ed-check") return runCheck();
  if (d.size) {
    ed.resume.page_size = d.size;
    document.querySelectorAll("#ed-size button").forEach((x) => x.classList.toggle("on", x === b));
    return runCheck();
  }
  if (d.goto) return goTo(d.goto);
  if (d.dismiss) { ed.dismissed.add(d.dismiss); return renderCheck(); }
  if (d.confirm !== undefined) {
    b.checked ? ed.confirmed.add(d.confirm) : ed.confirmed.delete(d.confirm);
    return renderCheck();
  }
  if (d.apply) {
    const s = find(d.apply);
    if (!s) return;
    if (getPath(ed.resume, s.path) !== s.before) return editorStatus("That text has changed since the check. Check again first.", true);
    setPath(ed.resume, s.path, s.after);
    const el = field(s.path);
    if (el) el.value = s.after;
    ed.dismissed.add(d.apply);
    renderCheck();
    return scheduleCheck();
  }
  if (d.add) {
    const s = find(d.add);
    const items = s && getPath(ed.resume, s.add_to);
    if (!items) return;
    if (!items.some((x) => x.toLowerCase() === s.add.toLowerCase())) items.push(s.add);
    const el = field(s.add_to);
    if (el) el.value = items.join(", ");
    ed.dismissed.add(d.add);
    renderCheck();
    return scheduleCheck();
  }
  // Structural edits redraw the form; suggestions point at old paths until the re-check.
  if (d.remove) {
    const parts = d.remove.split(".");
    const idx = Number(parts.pop());
    getPath(ed.resume, parts.join(".")).splice(idx, 1);
  } else if (d.push) {
    getPath(ed.resume, d.push).push("");
  } else if (d.pushEntry) {
    getPath(ed.resume, d.pushEntry).entries.push({ title: "", org: "", location: "", dates: "", bullets: [""] });
  } else if (d.pushSchool) {
    getPath(ed.resume, d.pushSchool).schools.push({ school: "", degree: "", location: "", dates: "", gpa: "", details: [] });
  } else if (d.up) {
    const i = Number(d.up);
    const s = ed.resume.sections;
    [s[i - 1], s[i]] = [s[i], s[i - 1]];
  } else {
    return;
  }
  ed.check = null;
  renderCheck();
  redrawForm();
  scheduleCheck();
});
