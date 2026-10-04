"use strict";
/* global I18N, t, setLang, currentLang, words */

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

async function copyText(text, doneKey) {
  try { await navigator.clipboard.writeText(text); toast(t(doneKey)); }
  catch { toast(t("copyBlocked")); }
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
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z"/>',
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
function hSeg(x, y, len, w) {
  return `${x},${y} ${x + w / 2},${y - w / 2} ${x + len - w / 2},${y - w / 2} ${x + len},${y} ${x + len - w / 2},${y + w / 2} ${x + w / 2},${y + w / 2}`;
}
function vSeg(x, y, len, w) {
  return `${x},${y} ${x + w / 2},${y + w / 2} ${x + w / 2},${y + len - w / 2} ${x},${y + len} ${x - w / 2},${y + len - w / 2} ${x - w / 2},${y + w / 2}`;
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

/* ---------- page elements and state ---------- */
const form = document.getElementById("ask-form");
const tiles = document.getElementById("tiles");
const queryBox = document.getElementById("query");
const goButton = document.getElementById("go");
const formError = document.getElementById("form-error");
const answer = document.getElementById("answer");
const examplesBox = document.getElementById("examples");
const lamp = document.getElementById("lamp");
const lampText = document.getElementById("lamp-text");
const hint = document.getElementById("query-hint");
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const SPEECH = { en: "en-IN", hi: "hi-IN", ta: "ta-IN" };

let machines = [];
let busy = false;
let lampKey = "starting";
let view = "translated";  // or "english": which copy of the answer is on screen
let lastAnswer = null;    // { response, codeShown } so a language or view change can re-render it

/* ---------- theme: automatic, light or dark ---------- */
const THEME_KEYS = { auto: "themeAuto", light: "themeLight", dark: "themeDark" };
const themeButton = document.getElementById("theme");
function applyTheme(mode) {
  if (mode === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = mode;
  themeButton.replaceChildren(icon(mode));
  themeButton.setAttribute("aria-label", t("colourTheme", { mode: t(THEME_KEYS[mode]) }));
  themeButton.title = t("themeTitle", { mode: t(THEME_KEYS[mode]) });
}
themeButton.addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const next = order[(order.indexOf(store.get("faultsense.theme", "auto")) + 1) % order.length];
  store.set("faultsense.theme", next);
  applyTheme(next);
  toast(t("colourTheme", { mode: t(THEME_KEYS[next]) }));
});

/* ---------- language ---------- */
function applyLanguage(lang) {
  setLang(lang);
  store.set("faultsense.lang", currentLang);
  document.documentElement.lang = currentLang;
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of document.querySelectorAll("[data-i18n-aria]")) node.setAttribute("aria-label", t(node.dataset.i18nAria));
  for (const button of document.querySelectorAll(".lang-switch button")) {
    button.setAttribute("aria-pressed", String(button.dataset.lang === currentLang));
  }
  if (!busy) goButton.textContent = t("diagnose");
  hint.textContent = t(Recognition ? "hintVoice" : "hint");
  lampText.textContent = t(lampKey);
  applyTheme(store.get("faultsense.theme", "auto"));
  buildTiles();
  showRecent();
  if (lastAnswer) showDiagnosis(lastAnswer.response, lastAnswer);
  else if (!busy) showEmpty();
}
for (const button of document.querySelectorAll(".lang-switch button")) {
  button.addEventListener("click", () => applyLanguage(button.dataset.lang));
}

/* ---------- machine tiles ---------- */
function machineIcon(text) {
  const lower = text.toLowerCase();
  return lower.includes("fan") ? "fan" : lower.includes("conveyor") ? "conveyor" : lower.includes("pump") ? "pump"
    : lower.includes("hoist") || lower.includes("crane") ? "hoist" : "drive";
}
function selectedMachineId() { const checked = tiles.querySelector("input:checked"); return checked ? checked.value : ""; }
function selectedMachine() { return machines.find((m) => m.id === selectedMachineId()) || null; }
function selectMachine(id) {
  const input = tiles.querySelector(`input[value="${CSS.escape(id)}"]`) || tiles.querySelector('input[value=""]');
  if (input) input.checked = true;
  showExamples();
}
function buildTiles() {
  const chosen = selectedMachineId() || store.get("faultsense.machine", "");
  const names = words("machines") || {};
  const entries = [{ id: "", name: t("anyDrive"), drive: t("noMachine"), icon: "drive", title: t("allManuals") }].concat(machines.map((m) => {
    const [name, drive] = (m.description || m.id).split(/\s+on an?\s+/i);
    return { id: m.id, name: names[name] || name || m.id, drive: drive || m.family, icon: machineIcon(m.description || ""), title: m.id };
  }));
  tiles.replaceChildren(...entries.map((entry, i) => {
    const inputId = `machine-${i}`;
    return el("div", { class: "tile" },
      el("input", { type: "radio", name: "machine", id: inputId, value: entry.id, onchange: () => {
        store.set("faultsense.machine", entry.id);
        showExamples();
      } }),
      el("label", { for: inputId, title: entry.title },
        icon(entry.icon), el("span", { class: "tile-name", text: entry.name }), el("span", { class: "tile-drive", lang: "en", text: entry.drive })));
  }));
  selectMachine(chosen);
}

function showExamples() {
  const machine = selectedMachine();
  const examples = words("examples");
  examplesBox.replaceChildren(...(examples[machine ? machine.manual : ""] || examples[""]).map((text) =>
    el("button", { type: "button", class: "example", text, onclick: () => { queryBox.value = text; queryBox.focus(); } })));
}

function showEmpty() { answer.replaceChildren(readout("", t("emptyTitle"), t("emptySub"))); }

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

function setLamp(state, key) { lampKey = key; lamp.dataset.state = state; lampText.textContent = t(key); }
async function checkHealth() {
  setLamp("checking", "starting");
  try {
    const response = await fetch("/health");
    const report = await response.json();
    if (response.ok) setLamp("ready", "ready");
    else if (report.status === "degraded") setLamp("degraded", "dbOffline");
    else setLamp("down", "notReady");
  } catch {
    setLamp("down", "serverDown");
  }
}

/* ---------- voice input (only where the browser offers speech recognition) ---------- */
const mic = document.getElementById("mic");
if (Recognition) {
  mic.hidden = false;
  mic.append(icon("mic"));
  let recognition = null;
  mic.addEventListener("click", () => {
    if (recognition) { recognition.stop(); return; }
    recognition = new Recognition();
    recognition.lang = SPEECH[currentLang];
    recognition.interimResults = true;
    const base = queryBox.value.trim();
    recognition.onresult = (event) => {
      const heard = [...event.results].map((r) => r[0].transcript).join(" ").trim();
      queryBox.value = base ? `${base} ${heard}` : heard;
    };
    recognition.onerror = (event) => { toast(t(event.error === "not-allowed" ? "micRefused" : "nothingHeard")); };
    recognition.onend = () => {
      recognition = null;
      mic.setAttribute("aria-pressed", "false");
      hint.textContent = t("hintVoice");
    };
    mic.setAttribute("aria-pressed", "true");
    hint.textContent = t("listening");
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

/* ---------- passage viewer (manual text stays English) ---------- */
const sheet = document.getElementById("sheet");
const passageCache = new Map();
document.getElementById("sheet-close").append(icon("close"));
document.getElementById("sheet-close").addEventListener("click", () => sheet.close());
sheet.addEventListener("click", (event) => { if (event.target === sheet) sheet.close(); });

async function openPassage(chunkId, manual, page, family) {
  const where = document.getElementById("sheet-where");
  const title = document.getElementById("sheet-title");
  const body = document.getElementById("sheet-body");
  const pdf = document.getElementById("sheet-pdf");
  where.textContent = t("passageWhere", { family, page });
  title.textContent = t("passageLoading");
  body.textContent = "";
  pdf.href = `/manuals/${encodeURIComponent(manual)}.pdf#page=${page}`;
  pdf.textContent = t("openPdf", { page });
  if (!sheet.open) sheet.showModal();
  try {
    if (!passageCache.has(chunkId)) {
      const response = await fetch(`/passages/${encodeURIComponent(chunkId)}`);
      if (!response.ok) throw new Error(String(response.status));
      passageCache.set(chunkId, await response.json());
    }
    const p = passageCache.get(chunkId);
    where.textContent = p.page_start === p.page_end
      ? t("passageWhere", { family: p.family, page: p.page_start })
      : t("passagePages", { family: p.family, from: p.page_start, to: p.page_end });
    title.textContent = p.heading.split(" > ").pop();
    body.textContent = p.text;
  } catch {
    title.textContent = t("passageFailed");
    body.textContent = t("passageFailedBody");
  }
}

/* ---------- which copy of the answer is shown ---------- */
function translationOf(response) {
  const tr = response.translation;
  return tr && tr.available ? tr : null;
}
function shown(response, kind, index, english) {
  const tr = view === "translated" ? translationOf(response) : null;
  const item = tr && tr[kind] && tr[kind][index];
  if (!item) return { text: english, fallback: false, translated: false, lang: "en" };
  return { text: item.text, fallback: item.fallback, translated: !item.fallback, lang: item.fallback ? "en" : tr.language };
}
function inEnglishTag(item) { return item.fallback ? el("span", { class: "tag-en", text: t("inEnglish") }) : null; }

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
    return el("a", { class: "cite", lang: "en", href: `/manuals/${encodeURIComponent(manual)}.pdf#page=${page}`, target: "_blank",
                     rel: "noopener", text: label, title: t("openManual") });
  }
  return el("button", { type: "button", class: "cite", lang: "en", text: label, title: t("readPassage"),
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
  const understood = response.meta.query_en && (view === "english" || currentLang === "en")
    ? el("span", { class: "understood", lang: "en", text: t("understoodAs", { q: response.meta.query_en }) }) : null;
  if (response.status === "escalate" && !response.sources.length && named.length) {
    return readout("", t("noManualFor", { models: named.join(", ") }), [t("noManualSub"), understood].filter(Boolean));
  }
  if (!matched.length) {
    return readout("", t(response.status === "escalate" ? "noCode" : "fromDescription"),
      [el("span", { text: t("searchedSymptoms") }), understood].filter(Boolean));
  }
  const first = matched[0];
  const sub = matched.map((m) => {
    const source = response.sources.find((s) => s.manual === m.manual && s.kind === "fault" && s.page_start === m.page);
    return citeButton(response, m.manual, m.page, source ? source.chunk_id : null);
  });
  if (first.fuzzy) sub.push(el("span", { text: t("lookalike", { code: first.code }) }));
  if (understood) sub.push(understood);
  const box = readout(first.code, first.name || first.code, sub, { reveal });
  box.querySelector(".readout-name").setAttribute("lang", "en");
  return box;
}

function dangerBlock(response) {
  if (!response.safety_warnings.length) return null;
  const sign = svg("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" });
  sign.append(svg("path", { d: "M12 2 1 21h22L12 2z", fill: "#fff" }), svg("path", { d: "M11 9h2v6h-2zM11 16.5h2v2h-2z", fill: "#c1121f" }));
  return el("section", { class: "danger", "aria-label": t("safetyLabel") },
    el("h2", { class: "danger-head" }, sign, t("danger")),
    el("ul", {}, response.safety_warnings.map((w, i) => {
      const item = shown(response, "safety_warnings", i, w.text);
      return el("li", {},
        el("p", { lang: item.lang, text: item.text }), inEnglishTag(item),
        item.translated ? el("p", { class: "orig", lang: "en", text: w.text }) : null,  // the original is always visible
        cites(response, w.citations));
    })));
}

function causesBlock(response) {
  if (!response.probable_causes.length) return null;
  return el("section", { class: "block causes" },
    el("div", { class: "block-head" }, el("h2", { text: t("likelyCauses") })),
    el("ol", {}, response.probable_causes.map((c, i) => {
      const item = shown(response, "causes", i, c.cause);
      const lit = Math.round(Math.max(0, Math.min(1, c.confidence)) * 10);
      const meter = el("div", { class: "meter", role: "img", "aria-label": t("support", { n: lit }) },
        Array.from({ length: 10 }, (_, k) => el("i", { class: k < lit ? "on" : "" })));
      return el("li", { class: "cause" },
        el("span", { class: "cause-rank", "aria-hidden": "true", text: c.rank }),
        el("div", {}, el("p", { class: "cause-text", lang: item.lang }, item.text, inEnglishTag(item)), meter, cites(response, c.citations)));
    })));
}

function stepsBlock(response, reportText) {
  const steps = response.corrective_actions;
  if (!steps.length) return null;
  const count = el("span", { text: t("stepsDone", { n: 0, total: steps.length }) });
  const fill = el("span", { class: "track-fill" });
  const track = el("div", { class: "track", "aria-live": "polite" }, el("span", { class: "track-bar", "aria-hidden": "true" }, fill), count);
  const block = el("section", { class: "block steps" });
  const doneNote = el("div", { class: "done-note" }, el("span", { text: t("allDone") }),
    el("button", { type: "button", class: "button-quiet", onclick: () => copyText(
      `${reportText()}\n\n${t("reportAllDone", { n: steps.length, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) })}`,
      "reportCopied") }, icon("copy"), t("copyReport")));
  const update = () => {
    const done = block.querySelectorAll(".step input:checked").length;
    count.textContent = t("stepsDone", { n: done, total: steps.length });
    fill.style.width = `${(done / steps.length) * 100}%`;
    track.classList.toggle("complete", done === steps.length);
    if (done === steps.length) block.append(doneNote); else doneNote.remove();
  };
  block.append(
    el("div", { class: "block-head" }, el("h2", { text: t("whatToDo") }), track),
    el("ol", {}, steps.map((s, i) => {
      const item = shown(response, "steps", i, s.action);
      return el("li", { class: `step${s.requires_isolation ? " isolate" : ""}` },
        el("label", {},
          el("input", { type: "checkbox", "aria-label": t("stepDone", { n: s.step }), onchange: update }),
          el("span", { class: "step-n", "aria-hidden": "true", text: s.step }),
          el("span", { class: "step-body" },
            s.requires_isolation ? el("p", { class: "isolate-note", text: t("isolateNote") }) : null,
            el("span", { class: "step-text", lang: item.lang, text: item.text }), inEnglishTag(item))),
        cites(response, s.citations));
    })));
  return block;
}

function sourcesBlock(response) {
  if (!response.sources.length) return null;
  return el("details", { class: "block sources" },
    el("summary", { text: t("pagesUsed", { n: response.sources.length }) }),
    el("ul", {}, response.sources.map((s) => el("li", {},
      citeButton(response, s.manual, s.page_start, s.chunk_id),
      el("span", { lang: "en" }, s.heading, s.kind === "safety" ? el("span", { class: "kind", text: t("safetyKind") }) : null)))));
}

const PLAIN = [["evidence threshold", "reasonEvidence"], ["do not cover", "reasonCover"],
               ["grounding checks", "reasonGrounding"], ["language model", "reasonModel"]];
function plainReason(reason) { const hit = PLAIN.find(([key]) => reason.includes(key)); return hit ? t(hit[1]) : null; }
function collectText(text) {
  const index = I18N.en.collect.indexOf(text);
  return index >= 0 ? words("collect")[index] : text;
}

function escalationBlock(response) {
  const e = response.escalation;
  const plain = plainReason(e.reason);
  return el("section", { class: "escalate" },
    el("h2", { text: t("callEngineer") }),
    el("p", { lang: plain ? currentLang : "en", text: plain || e.reason }),
    plain ? el("p", { class: "detail", lang: "en", text: t("details", { reason: e.reason }) }) : null,
    el("h3", { text: t("noteDown") }),
    el("ul", { class: "collect" }, e.collect.map((text) => el("li", {}, el("label", {}, el("input", { type: "checkbox" }), el("span", { text: collectText(text) }))))),
    // The engineer's summary stays English: it is written for maintenance staff.
    el("button", { type: "button", class: "copy", onclick: () => copyText(
      `${e.summary}\n\nPlease note:\n${e.collect.map((c) => `- ${c}`).join("\n")}`, "summaryCopied") },
      t("copyForEngineer")),
    e.sources_considered.length ? el("div", {}, el("h3", { text: t("pagesChecked") }),
      cites(response, e.sources_considered.map((s) => ({ manual: s.manual, page: s.page_start, chunk_id: s.chunk_id })))) : null);
}

function answerText(response) {
  const pages = (citations) => [...new Set(citations.map((c) => `${familyOf(response, c.manual)} p.${c.page}`))].join(", ");
  const lines = [`FaultSense: ${response.query}${response.machine_id ? ` (${response.machine_id})` : ""}`];
  for (const m of response.matched_fault_codes) lines.push(`${t("copyFaultCode")}: ${m.code} ${m.name} (${familyOf(response, m.manual)} p.${m.page})`);
  if (response.safety_warnings.length) {
    lines.push("", `${t("copySafety")}:`, ...response.safety_warnings.map((w, i) =>
      `- ${shown(response, "safety_warnings", i, w.text).text} (${pages(w.citations)})`));
  }
  lines.push("", `${t("likelyCauses")}:`, ...response.probable_causes.map((c, i) =>
    `${c.rank}. ${shown(response, "causes", i, c.cause).text} (${pages(c.citations)})`));
  lines.push("", `${t("copySteps")}:`, ...response.corrective_actions.map((s, i) =>
    `${s.step}. ${s.requires_isolation ? `${t("copyIsolate")} ` : ""}${shown(response, "steps", i, s.action).text} (${pages(s.citations)})`));
  return lines.join("\n");
}

function showDiagnosis(response, { codeShown }) {
  lastAnswer = { response, codeShown };
  const seconds = Math.max(1, Math.round(response.meta.latency_ms / 1000));
  const report = () => answerText(response);
  const translated = translationOf(response);
  const wantsTranslation = response.language === "hi" || response.language === "ta";
  const toggle = translated && response.status === "diagnosis"
    ? el("button", { type: "button", class: "button-quiet", onclick: () => {
        view = view === "translated" ? "english" : "translated";
        showDiagnosis(response, { codeShown: true });
      } }, view === "translated" ? t("showEnglish") : t("showTranslated"))
    : null;
  const toolbar = el("div", { class: "toolbar" },
    el("p", { class: "meta", text: t("answeredIn", { s: seconds }) }),
    toggle,
    response.status === "diagnosis"
      ? el("button", { type: "button", class: "button-quiet", onclick: () => copyText(report(), "answerCopied") }, icon("copy"), t("copyAnswer"))
      : null);
  const parts = [codeReadout(response, { reveal: !codeShown })];
  if (wantsTranslation && !translated && response.status === "diagnosis") parts.push(el("p", { class: "notice", text: t("translationUnavailable") }));
  if (response.status === "escalate") parts.push(escalationBlock(response));
  else parts.push(dangerBlock(response), causesBlock(response), stepsBlock(response, report));
  parts.push(sourcesBlock(response), toolbar);
  answer.replaceChildren(...parts.filter(Boolean));
}

function showProblem(titleKey, bodyKey, vars) {
  lastAnswer = null;
  answer.replaceChildren(el("section", { class: "problem", role: "alert" }, el("h2", { text: t(titleKey) }), el("p", { text: t(bodyKey, vars) })));
}

/* ---------- live progress ---------- */
function progressView(translating) {
  const keys = [["read", "stageRead"], ["search", "stageSearch"], ["write", "stageWrite"], ["check", "stageCheck"]];
  if (translating) keys.push(["translate", "stageTranslate"]);
  const stages = keys.map(([key, nameKey]) => {
    const detail = el("span", { class: "stage-detail" });
    const item = el("li", { class: "stage" }, el("span", { class: "stage-mark", "aria-hidden": "true" }), el("span", { class: "stage-name", text: t(nameKey) }), detail);
    return { key, item, detail };
  });
  const elapsed = el("p", { class: "elapsed" });
  const display = el("div", {}, readout("", t("checkingManuals"), t("working"), { testing: true }));
  const view_ = el("div", { class: "block", style: "padding: 0" }, el("ol", { class: "progress" }, stages.map((s) => s.item)), elapsed);
  const set = (key, state, text) => {
    const stage = stages.find((s) => s.key === key);
    if (!stage) return;
    stage.item.classList.remove("active", "done", "warn");
    if (state) stage.item.classList.add(state);
    if (text !== undefined) stage.detail.textContent = text;
  };
  return { display, view: view_, elapsed, set };
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

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (busy) return;
  const query = queryBox.value.trim();
  formError.hidden = true;
  if (!query) {
    formError.textContent = t("emptyQuery");
    formError.hidden = false;
    queryBox.focus();
    return;
  }
  busy = true;
  lastAnswer = null;
  view = "translated";
  goButton.disabled = true;
  goButton.textContent = t("diagnosing");
  answer.setAttribute("aria-busy", "true");
  const machineId = selectedMachineId();
  const language = currentLang;
  const started = performance.now();
  const progress = progressView(language !== "en");
  let codeShown = false;
  progress.set("read", "active");
  answer.replaceChildren(progress.display, progress.view);
  const tick = () => {
    const s = Math.round((performance.now() - started) / 1000);
    // Local models share the graphics card; a game or video editor can slow them to a crawl.
    progress.elapsed.textContent = t(s < 60 ? "elapsed" : "slow", { s });
  };
  tick();
  const timer = setInterval(tick, 1000);
  revealAnswer();

  const onEvent = (e) => {
    if (e.event === "stage" && e.stage === "translate_in") {
      progress.set("read", "active", t("translatingQuestion", { language: I18N[e.language] ? I18N[e.language].languageName : e.language }));
    } else if (e.event === "stage" && e.stage === "search") {
      progress.set("read", "done", e.models && e.models.length ? t("aboutModels", { models: e.models.join(", ") }) : "");
      progress.set("search", "active");
    } else if (e.event === "stage" && e.stage === "found") {
      const top = e.top ? `${e.top.family} p.${e.top.page}` : null;
      const more = Math.max(0, (e.pages || 0) - 1);
      const text = e.codes && e.codes.length
        ? t("foundCode", { code: e.codes[0], page: top }) + (more ? t("morePassages", { n: more }) : "")
        : top ? t("closest", { page: top, heading: e.top.heading.split(" > ").pop() }) : t("nothingClose");
      progress.set("search", "done", text);
      progress.set("write", "active");
      if (e.codes && e.codes.length) {
        codeShown = true;
        progress.display.replaceChildren(readout(e.codes[0], t("codeRecognised"), t("readingEntry"), { reveal: true }));
      }
    } else if (e.event === "stage" && e.stage === "retry") {
      progress.set("check", "warn", t("retry"));
    } else if (e.event === "stage" && e.stage === "translate_out") {
      progress.set("write", "done");
      progress.set("check", "done");
      progress.set("translate", "active");
    } else if (e.event === "result") {
      showDiagnosis(e.response, { codeShown });
      remember(query, machineId);
      if (lamp.dataset.state !== "ready") checkHealth();
    } else if (e.event === "error") {
      if (e.status === 404) showProblem("unknownMachineTitle", "unknownMachineBody");
      else { showProblem("failedTitle", "failedBody", { detail: e.detail }); checkHealth(); }
    }
  };

  try {
    const response = await fetch("/diagnose/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, machine_id: machineId || null, language }),
    });
    if (response.ok) await readStream(response, onEvent);
    else if (response.status === 422) showProblem("unreadableTitle", "unreadableBody");
    else { showProblem("failedTitle", "failedBody", { detail: response.status }); checkHealth(); }
  } catch {
    showProblem("unreachableTitle", "unreachableBody");
    setLamp("down", "serverDown");
  } finally {
    clearInterval(timer);
    busy = false;
    goButton.disabled = false;
    goButton.textContent = t("diagnose");
    answer.setAttribute("aria-busy", "false");
    revealAnswer();
  }
});

queryBox.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) form.requestSubmit();
});

applyLanguage(store.get("faultsense.lang", "en"));
loadInfo();
checkHealth();
