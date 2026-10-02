"use strict";

/* ---------- helpers: every server string goes through textContent ---------- */
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const SVG_NS = "http://www.w3.org/2000/svg";
function svg(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs || {})) node.setAttribute(key, value);
  return node;
}

const store = {
  get(key, fallback) {
    try { const raw = localStorage.getItem(key); return raw === null ? fallback : JSON.parse(raw); }
    catch { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ } },
};

let toastTimer;
function toast(text) {
  const box = document.getElementById("toast");
  box.textContent = text;
  box.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove("show"), 2200);
}

async function copyText(text, done) {
  try { await navigator.clipboard.writeText(text); toast(done); }
  catch { toast("Copying is blocked here: select the text and copy it instead."); }
}

/* ---------- line icons (24 x 24, stroked in currentColor) ---------- */
const ICONS = {
  drive: '<rect x="5" y="2.5" width="14" height="19" rx="2"/><rect x="8" y="5.5" width="8" height="4.5" rx="1"/><path d="M8.5 14h7M8.5 17.5h4.5"/>',
  fan: '<circle cx="12" cy="12" r="9.5"/><circle cx="12" cy="12" r="1.6"/><path d="M12 10.4c-.6-3.3.3-5.6 2.6-5.4 2 .2 1.6 3.2-1.2 5.3M13.4 12.8c3.1 1.2 4.6 3.2 3.2 5-1.2 1.6-3.6-.3-4.2-3.6M10.6 12.8c-2.6 2.1-5 2.4-5.8.3-.8-1.9 2-3 5.2-1.9"/>',
  conveyor: '<rect x="2.5" y="13" width="19" height="6" rx="3"/><circle cx="6" cy="16" r="1.2"/><circle cx="18" cy="16" r="1.2"/><rect x="8.5" y="6.5" width="7" height="6.5" rx="1"/>',
  pump: '<circle cx="10" cy="14.5" r="6.5"/><circle cx="10" cy="14.5" r="2"/><path d="M14.5 9.5V4h6.5M3.5 14.5H1.5"/>',
  hoist: '<path d="M2.5 4h19M12 7v6"/><rect x="9" y="4" width="6" height="3" rx="0.5"/><path d="M12 13a3.2 3.2 0 1 1-3.2 3.2"/>',
  mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5.5A1.5 1.5 0 0 0 14.5 4h-9A1.5 1.5 0 0 0 4 5.5v9A1.5 1.5 0 0 0 5.5 16H8"/>',
  auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor" stroke="none"/>',
  light: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>',
  dark: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
};
function icon(name) {
  const box = svg("svg", { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": "1.7",
                           "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
  box.innerHTML = ICONS[name];  // static markup from this file, never server text
  return box;
}

/* ---------- 7-segment readout, drawn like the drive's own LED display ---------- */
const SEGMENTS = {
  "0": "abcdef", "1": "bc", "2": "abdeg", "3": "abcdg", "4": "bcfg", "5": "acdfg", "6": "acdefg",
  "7": "abc", "8": "abcdefg", "9": "abcdfg",
  A: "abcefg", B: "cdefg", C: "adef", D: "bcdeg", E: "adefg", F: "aefg", G: "acdef", H: "bcefg",
  I: "ef", J: "bcde", L: "def", N: "ceg", O: "abcdef", P: "abefg", Q: "abcfg", R: "eg", S: "acdfg",
  T: "defg", U: "bcdef", Y: "bcdfg",
  b: "cdefg", c: "deg", d: "bcdeg", h: "cefg", n: "ceg", o: "cdeg", r: "eg", t: "defg", u: "cde",
  "-": "g", " ": "",
};
const CELL = 60;
function hSeg(x, y, len, t) {
  return `${x},${y} ${x + t / 2},${y - t / 2} ${x + len - t / 2},${y - t / 2} ${x + len},${y} ${x + len - t / 2},${y + t / 2} ${x + t / 2},${y + t / 2}`;
}
function vSeg(x, y, len, t) {
  return `${x},${y} ${x + t / 2},${y + t / 2} ${x + t / 2},${y + len - t / 2} ${x},${y + len} ${x - t / 2},${y + len - t / 2} ${x - t / 2},${y + t / 2}`;
}
const SHAPES = {
  a: hSeg(9, 7, 36, 8), g: hSeg(9, 50, 36, 8), d: hSeg(9, 93, 36, 8),
  f: vSeg(7, 9, 39, 8), b: vSeg(47, 9, 39, 8), e: vSeg(7, 52, 39, 8), c: vSeg(47, 52, 39, 8),
};
function segmentable(text) { return [...text].every((ch) => ch in SEGMENTS || ch.toUpperCase() in SEGMENTS); }

function sevenSegment(text, { minCells = 4, dots = false } = {}) {
  const chars = [...text].slice(0, 6);
  while (chars.length < minCells) chars.unshift(" ");
  const box = svg("svg", { class: "seg", viewBox: `-4 -2 ${chars.length * CELL + 8} 104`, "aria-hidden": "true" });
  const group = svg("g", { transform: "skewX(-7) translate(10 0)" });
  chars.forEach((ch, i) => {
    const lit = SEGMENTS[ch] ?? SEGMENTS[ch.toUpperCase()] ?? "";
    const off = svg("g", { class: "off" });
    const on = svg("g", { class: "on lit" });
    for (const [name, points] of Object.entries(SHAPES)) {
      (lit.includes(name) ? on : off).append(svg("polygon", { points, transform: `translate(${i * CELL} 0)` }));
    }
    (dots ? on : off).append(svg("circle", { cx: i * CELL + 56, cy: 93, r: 4 }));
    group.append(off, on);
  });
  box.append(group);
  return box;
}

function readout(code, nameText, sub, { testing = false, reveal = false } = {}) {
  let shown;
  if (testing) shown = sevenSegment("8888", { dots: true });
  else if (code && segmentable(code)) shown = sevenSegment(code);
  else if (code) shown = el("span", { class: "seg-text", "aria-hidden": "true", text: code });
  else shown = sevenSegment("----");
  const classes = ["readout", testing && "testing", reveal && code && "reveal"].filter(Boolean).join(" ");
  return el("div", { class: classes },
    shown,
    el("div", { class: "readout-meta" },
      el("p", { class: "readout-name", text: nameText }),
      sub ? el("div", { class: "readout-sub" }, sub) : null));
}

/* ---------- page elements ---------- */
const form = document.getElementById("ask-form");
const tiles = document.getElementById("tiles");
const queryBox = document.getElementById("query");
const goButton = document.getElementById("go");
const formError = document.getElementById("form-error");
const answer = document.getElementById("answer");
const examplesBox = document.getElementById("examples");
const lamp = document.getElementById("lamp");
const lampText = document.getElementById("lamp-text");

const EXAMPLES = {
  "": ["OHF on the pump drive", "InF1 on the fan drive", "ATV61 trips on OHF"],
  atv12: ["OHF", "SCF3 after we changed the motor cable", "Display stays blank at power up"],
  atv320: ["OCF when the conveyor starts", "Display flashes and the motor never reaches speed", "tnF at power up"],
  atv600: ["OHF", "Pump trips on hot afternoons", "Borewell pump runs dry and the drive trips"],
  atv900: ["BLF when the hoist lifts", "OBF when lowering a heavy load fast", "brF brake feedback fault"],
};
let machines = [];

/* ---------- theme: automatic, light or dark ---------- */
const THEMES = { auto: "automatic", light: "light", dark: "dark" };
const themeButton = document.getElementById("theme");
function applyTheme(mode) {
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  themeButton.replaceChildren(icon(mode));
  themeButton.setAttribute("aria-label", `Colour theme: ${THEMES[mode]}`);
  themeButton.title = `Colour theme: ${THEMES[mode]} (click to change)`;
}
themeButton.addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const next = order[(order.indexOf(store.get("faultsense.theme", "auto")) + 1) % order.length];
  store.set("faultsense.theme", next);
  applyTheme(next);
  toast(`Colour theme: ${THEMES[next]}`);
});
applyTheme(store.get("faultsense.theme", "auto"));

/* ---------- machine tiles ---------- */
function machineIcon(text) {
  const t = text.toLowerCase();
  return t.includes("fan") ? "fan" : t.includes("conveyor") ? "conveyor" : t.includes("pump") ? "pump"
    : t.includes("hoist") || t.includes("crane") ? "hoist" : "drive";
}
function selectedMachineId() { const checked = tiles.querySelector("input:checked"); return checked ? checked.value : ""; }
function selectedMachine() { return machines.find((m) => m.id === selectedMachineId()) || null; }
function selectMachine(id) {
  const input = tiles.querySelector(`input[value="${CSS.escape(id)}"]`) || tiles.querySelector('input[value=""]');
  if (input) input.checked = true;
  showExamples();
}
function buildTiles() {
  const entries = [{ id: "", name: "Any drive", drive: "No machine chosen", icon: "drive" }].concat(machines.map((m) => {
    const [name, drive] = (m.description || m.id).split(/\s+on an?\s+/i);
    return { id: m.id, name: name || m.id, drive: drive || m.family, icon: machineIcon(m.description || "") };
  }));
  tiles.replaceChildren(...entries.map((entry, i) => {
    const inputId = `machine-${i}`;
    return el("div", { class: "tile" },
      el("input", { type: "radio", name: "machine", id: inputId, value: entry.id, onchange: () => {
        store.set("faultsense.machine", entry.id);
        showExamples();
      } }),
      el("label", { for: inputId, title: entry.id || "Search all four manuals" },
        icon(entry.icon), el("span", { class: "tile-name", text: entry.name }), el("span", { class: "tile-drive", text: entry.drive })));
  }));
  selectMachine(store.get("faultsense.machine", ""));
}

function showExamples() {
  const machine = selectedMachine();
  examplesBox.replaceChildren(...(EXAMPLES[machine ? machine.manual : ""] || EXAMPLES[""]).map((text) =>
    el("button", { type: "button", class: "example", text, onclick: () => { queryBox.value = text; queryBox.focus(); } })));
}

function showEmpty() {
  answer.replaceChildren(readout("", "Waiting for a code or a problem",
    "Answers appear here, with the manual page behind every cause and step."));
}

/* ---------- start-up: machines, models and the system lamp ---------- */
async function loadInfo() {
  try {
    const info = await (await fetch("/info")).json();
    machines = info.machines || [];
    const engine = info.engine || {};
    const where = (name) => name && (name.startsWith("ollama ") ? `${name.slice(7)} on this computer` : `${name.replace(/^anthropic /, "")} (Claude API)`);
    const parts = [];
    if (engine.diagnosis) parts.push(`Diagnosis: ${where(engine.diagnosis)}.`);
    if (engine.rewrite) parts.push(`Search wording: ${where(engine.rewrite)}.`);
    document.getElementById("engine").textContent = parts.join(" ");
  } catch { /* the lamp reports a server that is not running */ }
  buildTiles();
}

function setLamp(state, text) { lamp.dataset.state = state; lampText.textContent = text; }
async function checkHealth() {
  setLamp("checking", "Starting up");
  try {
    const response = await fetch("/health");
    const report = await response.json();
    if (response.ok) setLamp("ready", "Ready");
    else if (report.status === "degraded") setLamp("degraded", "Database offline");
    else setLamp("down", "Not ready");
  } catch {
    setLamp("down", "Server not running");
  }
}

/* ---------- voice input (only where the browser offers speech recognition) ---------- */
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const mic = document.getElementById("mic");
const hint = document.getElementById("query-hint");
if (Recognition) {
  mic.hidden = false;
  mic.append(icon("mic"));
  let recognition = null;
  mic.addEventListener("click", () => {
    if (recognition) { recognition.stop(); return; }
    recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.interimResults = true;
    const base = queryBox.value.trim();
    recognition.onresult = (event) => {
      const heard = [...event.results].map((r) => r[0].transcript).join(" ").trim();
      queryBox.value = base ? `${base} ${heard}` : heard;
    };
    recognition.onerror = (event) => {
      toast(event.error === "not-allowed" ? "Microphone access was refused." : "Nothing was heard. Try again.");
    };
    recognition.onend = () => {
      recognition = null;
      mic.setAttribute("aria-pressed", "false");
      hint.textContent = "Press Ctrl+Enter to diagnose.";
    };
    mic.setAttribute("aria-pressed", "true");
    hint.textContent = "Listening. Say the code or describe the problem.";
    recognition.start();
  });
}

/* ---------- recent questions (this browser only) ---------- */
function remember(query, machineId) {
  const recent = store.get("faultsense.recent", []).filter((r) => r.query !== query);
  recent.unshift({ query, machineId });
  store.set("faultsense.recent", recent.slice(0, 5));
  showRecent();
}
function showRecent() {
  const recent = store.get("faultsense.recent", []);
  document.getElementById("recent").hidden = recent.length === 0;
  document.getElementById("recent-list").replaceChildren(...recent.map((r) => el("li", {},
    el("button", { type: "button", text: r.query, onclick: () => {
      queryBox.value = r.query;
      selectMachine(r.machineId || "");
      queryBox.focus();
    } }))));
}

/* ---------- passage viewer ---------- */
const sheet = document.getElementById("sheet");
const passageCache = new Map();
document.getElementById("sheet-close").append(icon("close"));
document.getElementById("sheet-close").addEventListener("click", () => sheet.close());
sheet.addEventListener("click", (event) => { if (event.target === sheet) sheet.close(); });  // click on the backdrop

async function openPassage(chunkId, manual, page, family) {
  const where = document.getElementById("sheet-where");
  const title = document.getElementById("sheet-title");
  const body = document.getElementById("sheet-body");
  const pdf = document.getElementById("sheet-pdf");
  where.textContent = `${family} manual, page ${page}`;
  title.textContent = "Loading the manual passage";
  body.textContent = "";
  pdf.href = `/manuals/${encodeURIComponent(manual)}.pdf#page=${page}`;
  pdf.textContent = `Open the PDF at page ${page}`;
  if (!sheet.open) sheet.showModal();
  try {
    if (!passageCache.has(chunkId)) {
      const response = await fetch(`/passages/${encodeURIComponent(chunkId)}`);
      if (!response.ok) throw new Error(String(response.status));
      passageCache.set(chunkId, await response.json());
    }
    const p = passageCache.get(chunkId);
    const pages = p.page_start === p.page_end ? `page ${p.page_start}` : `pages ${p.page_start} to ${p.page_end}`;
    where.textContent = `${p.family} manual, ${pages}`;
    title.textContent = p.heading.split(" > ").pop();
    body.textContent = p.text;
  } catch {
    title.textContent = "This passage could not be loaded";
    body.textContent = "The PDF link below still opens the manual at the cited page.";
  }
}

/* ---------- rendering an answer ---------- */
function sourceFor(response, sourceId) { return response.sources.find((s) => s.id === sourceId); }
function familyOf(response, manualId) {
  const source = response.sources.find((s) => s.manual === manualId);
  return source ? source.family : manualId.toUpperCase();
}
function citeButton(response, manual, page, chunkId) {
  const family = familyOf(response, manual);
  const label = `${family} p.${page}`;
  if (!chunkId) {
    return el("a", { class: "cite", href: `/manuals/${encodeURIComponent(manual)}.pdf#page=${page}`, target: "_blank",
                     rel: "noopener", text: label, title: "Open the manual at this page" });
  }
  return el("button", { type: "button", class: "cite", text: label, title: "Read this passage of the manual",
                        onclick: () => openPassage(chunkId, manual, page, family) });
}
function cites(response, citations) {
  const seen = new Set();
  const buttons = [];
  for (const c of citations) {
    const key = `${c.manual}:${c.page}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const source = c.source_id ? sourceFor(response, c.source_id) : null;
    buttons.push(citeButton(response, c.manual, c.page, source ? source.chunk_id : c.chunk_id));
  }
  return buttons.length ? el("div", { class: "cites" }, buttons) : null;
}

function codeReadout(response, { reveal }) {
  const matched = response.matched_fault_codes;
  const named = response.meta.named_models || [];
  if (response.status === "escalate" && !response.sources.length && named.length) {
    return readout("", `No manual for the ${named.join(", ")}`, "FaultSense only answers from the manuals it has.");
  }
  if (!matched.length) {
    return readout("", response.status === "escalate" ? "No fault code recognised" : "Answered from your description",
      "No code on the display was mentioned, so FaultSense searched the manuals for the symptoms.");
  }
  const first = matched[0];
  const sub = matched.map((m) => {
    const source = response.sources.find((s) => s.manual === m.manual && s.kind === "fault" && s.page_start === m.page);
    return citeButton(response, m.manual, m.page, source ? source.chunk_id : null);
  });
  if (first.fuzzy) sub.push(el("span", { text: `You typed a look-alike: the drive shows this code as ${first.code}.` }));
  return readout(first.code, first.name || first.code, sub, { reveal });
}

function dangerBlock(response) {
  if (!response.safety_warnings.length) return null;
  const sign = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
  sign.append(svg("path", { d: "M12 2 1 21h22L12 2z", fill: "#fff" }), svg("path", { d: "M11 9h2v6h-2zM11 16.5h2v2h-2z", fill: "#c1121f" }));
  return el("section", { class: "danger", "aria-label": "Safety warnings" },
    el("h2", { class: "danger-head" }, sign, "DANGER"),
    el("ul", {}, response.safety_warnings.map((w) => el("li", {}, el("p", { text: w.text }), cites(response, w.citations)))));
}

function causesBlock(response) {
  if (!response.probable_causes.length) return null;
  return el("section", { class: "block causes" },
    el("div", { class: "block-head" }, el("h2", { text: "Likely causes" })),
    el("ol", {}, response.probable_causes.map((c) => {
      const lit = Math.round(Math.max(0, Math.min(1, c.confidence)) * 10);
      const meter = el("div", { class: "meter", role: "img", "aria-label": `Support in the manual: ${lit} of 10` },
        Array.from({ length: 10 }, (_, i) => el("i", { class: i < lit ? "on" : "" })));
      return el("li", { class: "cause" },
        el("span", { class: "cause-rank", "aria-hidden": "true", text: c.rank }),
        el("div", {}, el("p", { class: "cause-text", text: c.cause }), meter, cites(response, c.citations)));
    })));
}

function stepsBlock(response, reportText) {
  const steps = response.corrective_actions;
  if (!steps.length) return null;
  const count = el("span", { text: `0 of ${steps.length} done` });
  const fill = el("span", { class: "track-fill" });
  const track = el("div", { class: "track", "aria-live": "polite" }, el("span", { class: "track-bar", "aria-hidden": "true" }, fill), count);
  const block = el("section", { class: "block steps" });
  const doneNote = el("div", { class: "done-note" }, el("span", { text: "All steps done." }),
    el("button", { type: "button", class: "button-quiet", onclick: () => copyText(
      `${reportText()}\n\nAll ${steps.length} steps done at ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}.`,
      "Report copied") }, icon("copy"), "Copy report"));
  const update = () => {
    const done = block.querySelectorAll(".step input:checked").length;
    count.textContent = `${done} of ${steps.length} done`;
    fill.style.width = `${(done / steps.length) * 100}%`;
    track.classList.toggle("complete", done === steps.length);
    if (done === steps.length) block.append(doneNote); else doneNote.remove();
  };
  block.append(
    el("div", { class: "block-head" }, el("h2", { text: "What to do" }), track),
    el("ol", {}, steps.map((s) => el("li", { class: `step${s.requires_isolation ? " isolate" : ""}` },
      el("label", {},
        el("input", { type: "checkbox", "aria-label": `Done: step ${s.step}`, onchange: update }),
        el("span", { class: "step-n", "aria-hidden": "true", text: s.step }),
        el("span", { class: "step-body" },
          s.requires_isolation ? el("p", { class: "isolate-note", text: "Isolate and lock out the power before this step." }) : null,
          el("span", { class: "step-text", text: s.action }))),
      cites(response, s.citations)))));
  return block;
}

function sourcesBlock(response) {
  if (!response.sources.length) return null;
  return el("details", { class: "block sources" },
    el("summary", { text: `Manual pages used (${response.sources.length})` }),
    el("ul", {}, response.sources.map((s) => el("li", {},
      citeButton(response, s.manual, s.page_start, s.chunk_id),
      el("span", {}, s.heading, s.kind === "safety" ? el("span", { class: "kind", text: " (safety)" }) : null)))));
}

const PLAIN = [
  ["evidence threshold", "This does not match anything in the drive manuals."],
  ["do not cover", "The manual pages found do not explain this problem well enough to name a cause."],
  ["grounding checks", "The drafted answer could not be fully backed by the manuals, so it is not shown."],
  ["language model", "The answering model is not available right now."],
];
function plainReason(reason) { const hit = PLAIN.find(([key]) => reason.includes(key)); return hit ? hit[1] : reason; }

function escalationBlock(response) {
  const e = response.escalation;
  const plain = plainReason(e.reason);
  return el("section", { class: "escalate" },
    el("h2", { text: "Call a maintenance engineer" }),
    el("p", { text: plain }),
    plain !== e.reason ? el("p", { class: "detail", text: `Details: ${e.reason}` }) : null,
    el("h3", { text: "Before they arrive, note down" }),
    el("ul", { class: "collect" }, e.collect.map((text) => el("li", {}, el("label", {}, el("input", { type: "checkbox" }), el("span", { text }))))),
    el("button", { type: "button", class: "copy", onclick: () => copyText(
      `${e.summary}\n\nPlease note:\n${e.collect.map((c) => `- ${c}`).join("\n")}`, "Summary copied for the engineer") },
      "Copy for the engineer"),
    e.sources_considered.length ? el("div", {}, el("h3", { text: "Manual pages checked" }),
      cites(response, e.sources_considered.map((s) => ({ manual: s.manual, page: s.page_start, chunk_id: s.chunk_id })))) : null);
}

function answerText(response) {
  const pages = (citations) => [...new Set(citations.map((c) => `${familyOf(response, c.manual)} p.${c.page}`))].join(", ");
  const lines = [`FaultSense: ${response.query}${response.machine_id ? ` (${response.machine_id})` : ""}`];
  for (const m of response.matched_fault_codes) lines.push(`Fault code: ${m.code} ${m.name} (${familyOf(response, m.manual)} p.${m.page})`);
  if (response.safety_warnings.length) {
    lines.push("", "Safety:", ...response.safety_warnings.map((w) => `- ${w.text} (${pages(w.citations)})`));
  }
  lines.push("", "Likely causes:", ...response.probable_causes.map((c) => `${c.rank}. ${c.cause} (${pages(c.citations)})`));
  lines.push("", "Steps:", ...response.corrective_actions.map((s) =>
    `${s.step}. ${s.requires_isolation ? "[Isolate and lock out first] " : ""}${s.action} (${pages(s.citations)})`));
  return lines.join("\n");
}

function showDiagnosis(response, { codeShown }) {
  const seconds = Math.max(1, Math.round(response.meta.latency_ms / 1000));
  const report = () => answerText(response);
  const toolbar = el("div", { class: "toolbar" },
    el("p", { class: "meta", text: `Answered in ${seconds} s.` }),
    response.status === "diagnosis"
      ? el("button", { type: "button", class: "button-quiet", onclick: () => copyText(report(), "Answer copied") }, icon("copy"), "Copy answer")
      : null);
  const parts = [codeReadout(response, { reveal: !codeShown })];
  if (response.status === "escalate") parts.push(escalationBlock(response));
  else parts.push(dangerBlock(response), causesBlock(response), stepsBlock(response, report));
  parts.push(sourcesBlock(response), toolbar);
  answer.replaceChildren(...parts.filter(Boolean));
}

function showProblem(title, text) {
  answer.replaceChildren(el("section", { class: "problem", role: "alert" }, el("h2", { text: title }), el("p", { text })));
}

/* ---------- live progress ---------- */
function progressView() {
  const stages = [
    ["read", "Reading the question"],
    ["search", "Searching the manuals"],
    ["write", "Writing the answer"],
    ["check", "Checking every citation"],
  ].map(([key, name]) => {
    const detail = el("span", { class: "stage-detail" });
    const item = el("li", { class: "stage" }, el("span", { class: "stage-mark", "aria-hidden": "true" }), el("span", { class: "stage-name", text: name }), detail);
    return { key, item, detail };
  });
  const elapsed = el("p", { class: "elapsed" });
  const display = el("div", {}, readout("", "Checking the manuals", "Working on it", { testing: true }));
  const view = el("div", { class: "block", style: "padding: 0" }, el("ol", { class: "progress" }, stages.map((s) => s.item)), elapsed);
  const set = (key, state, text) => {
    const stage = stages.find((s) => s.key === key);
    stage.item.classList.remove("active", "done", "warn");
    if (state) stage.item.classList.add(state);
    if (text !== undefined) stage.detail.textContent = text;
  };
  return { display, view, elapsed, set };
}

/* ---------- asking ---------- */
// One column: the answer sits below the form, so jump to it while waiting and again when it lands.
function revealAnswer() {
  if (window.matchMedia("(max-width: 959px)").matches) answer.scrollIntoView({ block: "start" });
}

async function readStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buffer.trim()) onEvent(JSON.parse(buffer));
}

let busy = false;
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const query = queryBox.value.trim();
  formError.hidden = true;
  if (!query) {
    formError.textContent = "Type the code on the display or a short description first.";
    formError.hidden = false;
    queryBox.focus();
    return;
  }
  busy = true;
  goButton.disabled = true;
  goButton.textContent = "Diagnosing";
  answer.setAttribute("aria-busy", "true");
  const machineId = selectedMachineId();
  const started = performance.now();
  const progress = progressView();
  let codeShown = false;
  progress.set("read", "active");
  answer.replaceChildren(progress.display, progress.view);
  const tick = () => {
    const seconds = Math.round((performance.now() - started) / 1000);
    // Local models share the graphics card; a game or video editor can slow them to a crawl.
    progress.elapsed.textContent = seconds < 60
      ? `${seconds} s. Usually 15 to 40 s on this computer.`
      : `${seconds} s. This is taking longer than usual. If a game or another graphics-heavy program is open, closing it frees the graphics card FaultSense uses.`;
  };
  tick();
  const timer = setInterval(tick, 1000);
  revealAnswer();

  const onEvent = (e) => {
    if (e.event === "stage" && e.stage === "search") {
      progress.set("read", "done", e.models && e.models.length ? `About the ${e.models.join(", ")}` : "");
      progress.set("search", "active");
    } else if (e.event === "stage" && e.stage === "found") {
      const top = e.top ? `${e.top.family} p.${e.top.page}` : null;
      const more = Math.max(0, (e.pages || 0) - 1);
      const text = e.codes && e.codes.length
        ? `Found ${e.codes[0]} in ${top}${more ? ` and ${more} more passages` : ""}`
        : top ? `Closest match: ${top}, ${e.top.heading.split(" > ").pop()}` : "Nothing close in the manuals";
      progress.set("search", "done", text);
      progress.set("write", "active");
      if (e.codes && e.codes.length) {
        codeShown = true;
        progress.display.replaceChildren(readout(e.codes[0], "Code recognised", "Reading its manual entry", { reveal: true }));
      }
    } else if (e.event === "stage" && e.stage === "retry") {
      progress.set("check", "warn", "A draft cited something the manual does not say, so it is being rewritten");
    } else if (e.event === "result") {
      showDiagnosis(e.response, { codeShown });
      remember(query, machineId);
      if (lamp.dataset.state !== "ready") checkHealth();
    } else if (e.event === "error") {
      if (e.status === 404) showProblem("Unknown machine", "That machine is not set up in FaultSense. Choose another machine or Any drive.");
      else { showProblem("FaultSense could not answer", `The server reported an error (${e.detail}). Try again; if it repeats, check the terminal running faultsense serve.`); checkHealth(); }
    }
  };

  try {
    const response = await fetch("/diagnose/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, machine_id: machineId || null }),
    });
    if (response.ok) await readStream(response, onEvent);
    else if (response.status === 422) showProblem("That question could not be read", "Type a fault code or a short description in plain text, up to 2,000 characters.");
    else { showProblem("FaultSense could not answer", `The server reported an error (${response.status}).`); checkHealth(); }
  } catch {
    showProblem("FaultSense is not reachable", "Check that faultsense serve is still running on this computer, then try again.");
    setLamp("down", "Server not running");
  } finally {
    clearInterval(timer);
    busy = false;
    goButton.disabled = false;
    goButton.textContent = "Diagnose";
    answer.setAttribute("aria-busy", "false");
    revealAnswer();
  }
});

queryBox.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) form.requestSubmit();
});

showEmpty();
showRecent();
loadInfo();
checkHealth();
