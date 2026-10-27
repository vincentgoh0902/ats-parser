// Everything from the PDF is inserted with textContent, never innerHTML.
const $ = (sel) => document.querySelector(sel);
const state = { report: null, engine: "modern", tab: "issues", previewUrl: null };

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

async function upload(file) {
  if (file.size > 5 * 1024 * 1024) return setStatus("That file is larger than 5 MB.", true);
  setStatus(`Parsing ${file.name}…`);
  const body = new FormData();
  body.append("file", file);
  body.append("check_links", $("#check-links").checked ? "true" : "false");
  let res;
  try {
    res = await fetch("/api/parse", { method: "POST", body });
  } catch {
    return setStatus("Couldn't reach the server.", true);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return setStatus(data.detail || `Error ${res.status}`, true);

  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  $("#preview").src = state.previewUrl;
  $("#filename").textContent = file.name;
  state.report = data;
  setStatus("");
  drop.classList.add("compact");
  $("#result").hidden = false;
  render();
}

// ---- tabs and engine switch ----
document.querySelectorAll(".tabs button").forEach((b) =>
  b.addEventListener("click", () => { state.tab = b.dataset.tab; render(); }));
document.querySelectorAll("#engine button").forEach((b) =>
  b.addEventListener("click", () => { if (!b.disabled) { state.engine = b.dataset.engine; render(); } }));

function render() {
  const r = state.report;
  if (!r) return;
  // Field parsing only runs on the two layout-aware readings.
  if (state.tab !== "text" && state.engine === "stream") state.engine = "modern";

  document.querySelectorAll(".tabs button").forEach((b) => {
    b.setAttribute("aria-selected", String(b.dataset.tab === state.tab));
    $(`#tab-${b.dataset.tab}`).hidden = b.dataset.tab !== state.tab;
  });
  document.querySelectorAll("#engine button").forEach((b) => {
    b.classList.toggle("on", b.dataset.engine === state.engine);
    b.disabled = b.hasAttribute("data-text-only") && state.tab !== "text";
  });
  $(".engine-bar").hidden = state.tab === "issues" || state.tab === "links";

  const score = $("#score");
  score.textContent = `Parse health ${r.score}/100`;
  score.className = "score " + (r.score >= 85 ? "good" : r.score >= 60 ? "fair" : "poor");

  const counts = { issues: r.issues.length, links: r.links.length };
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.querySelector(".count")?.remove();
    if (counts[b.dataset.tab]) b.append(h("span", { class: "count" }, counts[b.dataset.tab]));
  });

  const views = { issues: renderIssues, fields: renderFields, text: renderText, links: renderLinks };
  const target = $(`#tab-${state.tab}`);
  target.replaceChildren(...[views[state.tab](r)].flat());
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
