// Everything from the PDF is inserted with textContent, never innerHTML.
const $ = (sel) => document.querySelector(sel);
const state = {
  report: null, engine: "modern", tab: "issues", previewUrl: null,
  file: null, matchedJd: "", left: "pdf", active: null,
};

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

// ---- upload ----
const drop = $("#drop"), input = $("#file"), statusEl = $("#status");

$("#pick").addEventListener("click", (e) => { e.stopPropagation(); input.click(); });
drop.addEventListener("click", () => input.click());
drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); } });
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]);
});
input.addEventListener("change", () => { if (input.files[0]) upload(input.files[0]); input.value = ""; });

function setStatus(msg, isError = false) {
  statusEl.textContent = msg;
  statusEl.classList.toggle("error", isError);
}

const jdInput = $("#jd"), rerun = $("#rerun");
function updateJdUi() {
  const n = jdInput.value.trim().length;
  $("#jd-count").textContent = n ? `${n.toLocaleString()} characters` : "";
  rerun.hidden = !(state.file && jdInput.value.trim() !== state.matchedJd);
  rerun.textContent = state.matchedJd ? "Match again" : "Match this job";
}
jdInput.addEventListener("input", updateJdUi);
rerun.addEventListener("click", () => state.file && upload(state.file));

async function upload(file) {
  if (file.size > 5 * 1024 * 1024) return setStatus("That file is larger than 5 MB.", true);
  const jdText = jdInput.value.trim();
  setStatus(jdText ? `Parsing ${file.name} and matching it to the job…` : `Parsing ${file.name}…`);
  const body = new FormData();
  body.append("file", file);
  body.append("check_links", $("#check-links").checked ? "true" : "false");
  if (jdText) body.append("job_description", jdText);
  let res;
  try {
    res = await fetch("/api/parse", { method: "POST", body });
  } catch {
    return setStatus("Couldn't reach the server.", true);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return setStatus(data.detail || `Error ${res.status}`, true);

  if (state.file !== file) {
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);
    $("#preview").src = state.previewUrl;
    $("#filename").textContent = file.name;
  }
  state.file = file;
  state.matchedJd = jdText;
  state.report = data;
  state.active = null;
  if (data.match) { state.tab = "match"; state.left = "marks"; }
  else { if (state.tab === "match") state.tab = "issues"; state.left = "pdf"; }
  updateJdUi();
  setStatus("");
  drop.classList.add("compact");
  $("#result").hidden = false;
  render();
}

// ---- tabs and engine switch ----
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => {
    state.tab = b.dataset.tab;
    if (state.tab === "match") state.left = "marks";
    render();
  }));
document.querySelectorAll("#left-view button").forEach((b) =>
  b.addEventListener("click", () => { state.left = b.dataset.left; renderLeft(); }));
document.querySelectorAll("#engine button").forEach((b) =>
  b.addEventListener("click", () => { if (!b.disabled) { state.engine = b.dataset.engine; render(); } }));

function render() {
  const r = state.report;
  if (!r) return;
  // Field parsing only runs on the two layout-aware readings.
  if (state.tab !== "text" && state.engine === "stream") state.engine = "modern";

  document.querySelector('.tabs [data-tab="match"]').hidden = !r.match;
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.tab === state.tab));
    $(`#tab-${b.dataset.tab}`).hidden = b.dataset.tab !== state.tab;
  });
  document.querySelectorAll("#engine button").forEach((b) => {
    b.classList.toggle("on", b.dataset.engine === state.engine);
    b.disabled = b.hasAttribute("data-text-only") && state.tab !== "text";
  });
  $(".engine-bar").hidden = ["issues", "links", "match"].includes(state.tab);

  const score = $("#score");
  score.textContent = `Parse health ${r.score}/100`;
  score.className = "score " + (r.score >= 85 ? "good" : r.score >= 60 ? "fair" : "poor");

  const counts = { issues: r.issues.length, links: r.links.length };
  if (r.match) counts.match = `${r.match.score}`;
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.querySelector(".count")?.remove();
    if (counts[b.dataset.tab]) b.append(h("span", { class: "count" }, counts[b.dataset.tab]));
  });

  const views = { match: renderMatch, issues: renderIssues, fields: renderFields, text: renderText, links: renderLinks };
  const target = $(`#tab-${state.tab}`);
  target.replaceChildren(...[views[state.tab](r)].flat());
  renderLeft();
}

// ---- left pane: PDF or highlighted resume text ----
function renderLeft() {
  const m = state.report?.match;
  const marks = Boolean(m) && state.left === "marks";
  $("#left-view").hidden = !m;
  document.querySelectorAll("#left-view button").forEach((b) =>
    b.classList.toggle("on", b.dataset.left === (marks ? "marks" : "pdf")));
  $("#left-title").textContent = marks ? "Your resume" : "Your PDF";
  $("#preview").hidden = marks;
  $("#resume-doc-wrap").hidden = !marks;
  if (marks) {
    const spans = m.terms.flatMap((t) => t.resume_spans.map(([s, e]) => ({ s, e, t })));
    $("#resume-doc").replaceChildren(...highlight(m.resume_text, spans, "resume"));
    applyActive();
  }
}

// ---- views ----
function renderIssues(r) {
  if (!r.issues.length) {
    return h("div", { class: "all-clear" }, "No problems found. Both parsers read this resume cleanly.");
  }
  return r.issues.map((i) =>
    h("div", { class: `issue ${i.severity}` },
      h("span", { class: "code" }, `${i.severity.toUpperCase()} · ${i.code}`),
      h("p", {}, i.message),
      h("p", { class: "fix" }, "Fix: ", i.fix)));
}

const show = (v) => (v ? v : h("span", { class: "missing" }, "not found"));

function renderFields(r) {
  const f = state.engine === "modern" ? r.fields : r.legacy_fields;
  const c = f.contact;
  const out = [
    h("h3", {}, "Contact"),
    h("dl", { class: "kv" },
      h("dt", {}, "Name"), h("dd", {}, show(c.name)),
      h("dt", {}, "Email"), h("dd", {}, show(c.email)),
      h("dt", {}, "Phone"), h("dd", {}, show(c.phone)),
      h("dt", {}, "Location"), h("dd", {}, show(c.location)),
      h("dt", {}, "URLs"), h("dd", {}, c.urls.length ? c.urls.join(", ") : show(null))),
  ];
  if (f.summary) out.push(h("h3", {}, "Summary"), h("p", {}, f.summary));

  out.push(h("h3", {}, `Experience (${f.experience.length})`));
  if (!f.experience.length) out.push(h("p", { class: "missing" }, "No jobs extracted."));
  for (const e of f.experience) {
    out.push(h("div", { class: "entry" },
      h("dl", { class: "kv" },
        h("dt", {}, "Title"), h("dd", {}, show(e.title)),
        h("dt", {}, "Company"), h("dd", {}, show(e.company)),
        h("dt", {}, "Dates"), h("dd", {}, `${e.start ?? "?"} → ${e.end ?? "?"}`),
        e.location && [h("dt", {}, "Location"), h("dd", {}, e.location)]),
      e.bullets.length ? h("ul", {}, e.bullets.map((b) => h("li", {}, b))) : null));
  }

  out.push(h("h3", {}, `Education (${f.education.length})`));
  if (!f.education.length) out.push(h("p", { class: "missing" }, "No education extracted."));
  for (const e of f.education) {
    out.push(h("div", { class: "entry" },
      h("dl", { class: "kv" },
        h("dt", {}, "School"), h("dd", {}, show(e.school)),
        h("dt", {}, "Degree"), h("dd", {}, show(e.degree)),
        h("dt", {}, "Dates"), h("dd", {}, `${e.start ?? "?"} → ${e.end ?? "?"}`),
        e.gpa && [h("dt", {}, "GPA"), h("dd", {}, e.gpa)])));
  }

  out.push(h("h3", {}, "Skills section"),
    f.skills.length ? h("div", { class: "chips" }, f.skills.map((s) => h("span", { class: "chip" }, s)))
      : h("p", { class: "missing" }, "No Skills section found."));
  out.push(h("h3", {}, "Keywords a recruiter search would match"),
    h("div", { class: "chips" }, f.skills_detected.map((s) => h("span", { class: "chip" }, s))));

  out.push(h("h3", {}, "Sections found"),
    h("div", { class: "chips" }, f.sections.map((s) =>
      h("span", { class: "chip", title: s.heading || "" }, `${s.key} · ${s.lines} lines`))));
  return out;
}

function renderText(r) {
  const text = r.engines[state.engine];
  const desc = {
    modern: "Column-aware reading, like good commercial parsers.",
    legacy: "Straight across the page, like simpler ATSs. Highlighted lines differ from the Smart reading.",
    stream: "The order the text is stored in the PDF, which is what Tika-based ATSs see. Highlighted lines differ from the Smart reading.",
  }[state.engine];
  const pre = h("pre", { class: "raw" });
  if (state.engine === "modern") {
    pre.textContent = text || "(no text)";
  } else {
    const smart = new Set(r.engines.modern.split("\n").map((l) => l.trim()));
    for (const line of text.split("\n")) {
      const differs = line.trim() && !smart.has(line.trim());
      pre.append(differs ? h("mark", {}, line) : line, "\n");
    }
  }
  return [h("p", { class: "legend muted" }, desc), pre];
}

function linkStatus(l) {
  if (l.issue === "LINK_HIDDEN") return h("span", { class: "tag bad" }, "hidden from ATS");
  if (l.issue === "LINK_MISMATCH") return h("span", { class: "tag bad" }, "text ≠ target");
  if (!l.clickable) return h("span", { class: "tag warn" }, "text only, not clickable");
  return h("span", { class: "tag ok" }, "visible");
}

function liveness(l) {
  if (!l.check) return h("span", { class: "muted" }, "–");
  const { ok, status, note } = l.check;
  if (ok === true) return h("span", { class: "tag ok" }, status);
  if (ok === false) return h("span", { class: "tag bad" }, status || note);
  return h("span", { class: "tag neutral", title: note }, note);
}

function renderLinks(r) {
  if (!r.links.length) return h("p", { class: "muted" }, "No links found.");
  const anyChecked = r.links.some((l) => l.check);
  return [
    h("table", { class: "links" },
      h("thead", {}, h("tr", {}, h("th", {}, "Link"), h("th", {}, "Shown as"), h("th", {}, "ATS"),
        anyChecked && h("th", {}, "Loads"))),
      h("tbody", {}, r.links.map((l) => h("tr", {},
        h("td", {}, l.url),
        h("td", {}, l.anchor_text || h("span", { class: "muted" }, "(no text)")),
        h("td", {}, linkStatus(l)),
        anyChecked && h("td", {}, liveness(l)))))),
    !anyChecked && h("p", { class: "muted legend" }, "Tick “Check that links load” and upload again to test each link."),
  ];
}

// ---- job match ----
const STATUS_LABEL = { matched: "found", partial: "partly", missing: "missing" };
const WHERE_LABEL = {
  experience: "Experience", projects: "Projects", activities: "Activities", summary: "Summary",
  skills: "Skills list", education: "Education", top: "Header", certifications: "Certifications",
  awards: "Awards", links: "Links", contact: "Contact", languages: "Languages", interests: "Interests",
  publications: "Publications", references: "References",
};
const IMPORTANCE_LABEL = { required: "Required", responsibility: "From the responsibilities", preferred: "Nice to have" };

function termById(id) { return state.report.match.terms.find((t) => t.id === id); }

// Text with <mark>s for the given spans. Overlaps go to the longer span, then
// to a direct match over an implied one ("GitHub Actions" over "CI/CD").
const STATUS_RANK = { matched: 0, partial: 1, missing: 2 };
function highlight(text, spans, side) {
  const sorted = [...spans].sort((a, b) =>
    a.s - b.s || (b.e - b.s) - (a.e - a.s) || STATUS_RANK[a.t.status] - STATUS_RANK[b.t.status]);
  const out = [];
  let pos = 0;
  for (const { s, e, t } of sorted) {
    if (s < pos) continue;
    if (s > pos) out.push(text.slice(pos, s));
    out.push(h("mark", {
      class: `m ${t.status} ${t.importance}`, "data-term": t.id, "data-side": side, tabindex: "0",
      title: `${t.label} · ${IMPORTANCE_LABEL[t.importance]} · ${STATUS_LABEL[t.status]}`,
    }, text.slice(s, e)));
    pos = e;
  }
  out.push(text.slice(pos));
  return out;
}

function chip(t) {
  const where = t.where.length ? t.where.map((w) => WHERE_LABEL[w] || w).join(", ") : "";
  return h("button", { type: "button", class: `chip term ${t.status}`, "data-term": t.id, title: where },
    t.label, t.kind === "soft" ? h("span", { class: "chip-note" }, "soft skill") : null);
}

function renderMatch(r) {
  const m = r.match;
  const out = [];

  // Score and breakdown.
  out.push(h("div", { class: `match-head ${m.band}` },
    h("div", { class: "match-score" }, h("span", { class: "num" }, m.score), h("span", { class: "of" }, "/100")),
    h("div", {},
      h("p", { class: "band" }, m.band_label),
      m.title?.job_title && h("p", { class: "muted small" }, "Job: ", m.title.job_title))));
  out.push(h("div", { class: "breakdown" }, m.breakdown.map((b) =>
    h("div", { class: "brow" },
      h("span", { class: "blabel" }, b.label, h("span", { class: "bweight" }, ` ${b.weight}%`)),
      h("span", { class: "bar" }, h("span", { class: "fill", style: `width:${Math.round(b.score * 100)}%` })),
      h("span", { class: "bdetail muted" }, b.detail)))));

  out.push(h("div", { id: "focus", class: "focus muted" }, "Click any keyword to see where it appears in both texts."));

  // What's missing.
  const missing = m.terms.filter((t) => t.status === "missing");
  const partial = m.terms.filter((t) => t.status === "partial");
  out.push(h("h3", {}, "What's missing"));
  const groups = [
    ["Required", missing.filter((t) => t.importance !== "preferred")],
    ["Nice to have", missing.filter((t) => t.importance === "preferred")],
    ["Partly there", partial],
  ].filter(([, ts]) => ts.length);
  if (!groups.length) out.push(h("p", { class: "all-clear" }, "Every keyword from the job appears on your resume."));
  for (const [label, ts] of groups) {
    out.push(h("p", { class: "group-label" }, label), h("div", { class: "chips" }, ts.map(chip)));
  }

  if (m.suggestions.length) {
    out.push(h("h3", {}, "How to improve the match"));
    out.push(h("ul", { class: "suggestions" }, m.suggestions.map((sg) =>
      h("li", { class: `sg-${sg.kind}`, "data-term": sg.term || null }, sg.text))));
  }

  // What matches.
  const found = m.terms.filter((t) => t.status === "matched");
  out.push(h("h3", {}, `What matches (${found.length} of ${m.terms.length})`));
  if (!found.length) out.push(h("p", { class: "missing" }, "No keywords from the job were found."));
  for (const imp of ["required", "responsibility", "preferred"]) {
    const ts = found.filter((t) => t.importance === imp);
    if (ts.length) out.push(h("p", { class: "group-label" }, IMPORTANCE_LABEL[imp]), h("div", { class: "chips" }, ts.map(chip)));
  }

  // The job description, highlighted line by line.
  out.push(h("h3", {}, "Job description"),
    h("p", { class: "legend muted" },
      h("mark", { class: "m matched key" }, "found"), " ",
      h("mark", { class: "m partial key" }, "partly"), " ",
      h("mark", { class: "m missing key" }, "missing"),
      " · greyed-out parts (about the company, benefits) aren't scored."));
  const spans = m.terms.flatMap((t) => t.jd_spans.map(([s, e]) => ({ s, e, t })));
  const doc = h("div", { id: "jd-doc", class: "doc" });
  for (const [s, e, kind] of m.jd_sections) {
    const inLine = spans.filter((sp) => sp.s >= s && sp.e <= e).map((sp) => ({ ...sp, s: sp.s - s, e: sp.e - s }));
    doc.append(h("div", { class: `line ${kind}` }, highlight(m.jd_text.slice(s, e), inLine, "jd"), "\n"));
  }
  out.push(doc);
  queueMicrotask(applyActive);
  return out;
}

// Clicking a keyword anywhere focuses it on both sides.
document.addEventListener("click", (e) => {
  const el = e.target.closest("[data-term]");
  if (!el || !state.report?.match) return;
  setActive(el.dataset.term, el.dataset.side);
});
document.addEventListener("keydown", (e) => {
  const el = e.target.closest?.("mark[data-term]");
  if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setActive(el.dataset.term, el.dataset.side); }
});

function setActive(id, fromSide) {
  state.active = state.active === id && !fromSide ? null : id;
  if (state.active && state.left !== "marks") { state.left = "marks"; renderLeft(); }
  applyActive(fromSide);
}

function scrollWithin(container, el) {
  if (!container || !el) return;
  const c = container.getBoundingClientRect(), r = el.getBoundingClientRect();
  container.scrollTop += r.top - c.top - c.height / 3;
}

function applyActive(fromSide) {
  document.querySelectorAll(".is-active").forEach((el) => el.classList.remove("is-active"));
  const focus = $("#focus");
  const id = state.active;
  if (!id || !state.report?.match) return;
  document.querySelectorAll(`[data-term="${id}"]`).forEach((el) => el.classList.add("is-active"));
  const t = termById(id);
  if (!t) return;
  if (fromSide !== "jd") scrollWithin($("#jd-doc"), document.querySelector(`#jd-doc [data-term="${id}"]`));
  if (fromSide !== "resume") scrollWithin($("#resume-doc"), document.querySelector(`#resume-doc [data-term="${id}"]`));
  if (focus) {
    const where = t.where.map((w) => WHERE_LABEL[w] || w).join(", ");
    const parts = [h("strong", {}, t.label), ` · ${IMPORTANCE_LABEL[t.importance]} · `];
    if (t.status === "missing") parts.push(h("span", { class: "bad" }, "not on your resume"));
    else if (t.implied_by?.length) parts.push(h("span", { class: "warn" }, `implied by ${t.implied_by.join(", ")}`), ` (in ${where})`);
    else parts.push(`found in ${where}`);
    if (t.wording_differs) parts.push(` · you wrote “${t.resume_wording[0]}”, the job says “${t.jd_wording[0]}”`);
    focus.replaceChildren(...parts);
    focus.classList.remove("muted");
  }
}
