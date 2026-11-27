"use strict";

const state = {
  patches: [],
  tags: [],
  libTags: new Set(),
  selectedRef: null,
  selectedProject: null,
  roots: [],
  browse: { root: "card", path: "Samples", entries: [] },
  buildType: "oneshot",
  pads: {},
  selectedPad: null,
  zones: [],
  buildTags: new Set(),
  pendingBody: null,
  selectedCommit: null,
  mode: "new",
  baseRef: null,
  playing: null,
};

// ---------- helpers ----------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Number fields: press and drag up or down to change the value; a vertical slider shows where it is.
// A plain click still places the cursor for typing. Shift while dragging changes in finer steps.
(function setupNumberScrub() {
  document.addEventListener("pointerdown", (down) => {
    const input = down.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "number" || input.disabled || input.readOnly || down.button !== 0) return;
    const min = input.min !== "" ? Number(input.min) : null;
    const max = input.max !== "" ? Number(input.max) : null;
    const step = input.step && input.step !== "any" ? Number(input.step) : 1;
    const decimals = (String(step).split(".")[1] || "").length;
    const start = Number(input.value) || 0;
    const ranged = min != null && max != null && max > min;
    let dragging = false;
    let pop = null;
    let fill = null;
    let label = null;
    const show = () => {
      const box = input.getBoundingClientRect();
      fill = el("div", { class: "scrub-fill" });
      label = el("div", { class: "scrub-value" });
      pop = el("div", { class: "scrub-pop" + (ranged ? "" : " open-range") }, el("div", { class: "scrub-track" }, fill), label);
      document.body.append(pop);
      const height = 160;
      pop.style.left = `${Math.max(4, box.left - 46)}px`;
      pop.style.top = `${Math.min(window.innerHeight - height - 30, Math.max(4, box.top + box.height / 2 - height / 2))}px`;
    };
    const render = (value) => {
      label.textContent = value.toFixed(decimals);
      if (ranged) fill.style.height = `${((value - min) / (max - min)) * 100}%`;
    };
    const move = (ev) => {
      const dy = down.clientY - ev.clientY;
      if (!dragging) {
        if (Math.abs(dy) < 4) return;
        dragging = true;
        input.blur();
        document.body.classList.add("scrubbing");
        show();
      }
      // The whole range takes 16 pixels per value step, at least 120 and at most 400 pixels,
      // so a field with few values does not jump and one with many values stays reachable
      const count = ranged ? (max - min) / step : Infinity;
      const pxPerStep = Number.isFinite(count) ? Math.min(400, Math.max(120, count * 16)) / count : 6;
      const fine = ev.shiftKey ? 5 : 1;
      let value = start + Math.trunc(dy / (pxPerStep * fine)) * step;
      if (min != null) value = Math.max(min, value);
      if (max != null) value = Math.min(max, value);
      value = Number(value.toFixed(decimals));
      if (String(value) !== input.value) {
        input.value = String(value);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
      render(value);
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      if (!dragging) return;
      document.body.classList.remove("scrubbing");
      if (pop) pop.remove();
      if (Number(input.value) !== start) input.dispatchEvent(new Event("change", { bubbles: true }));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  });
})();

// Double click on a field with data-default sets the default; double click again brings back the value
// it had before. data-reset-key keeps that value across redraws of the field.
const resetMemory = new Map();
document.addEventListener("dblclick", (ev) => {
  const node = ev.target;
  if (!(node instanceof HTMLInputElement || node instanceof HTMLSelectElement) || node.disabled || node.dataset.default == null) return;
  ev.preventDefault();
  const key = node.dataset.resetKey || node;
  const current = node.value;
  const fallback = node.dataset.default;
  let next;
  if (Number(current) !== Number(fallback) || (Number.isNaN(Number(current)) && current !== fallback)) {
    resetMemory.set(key, current);
    next = fallback;
  } else if (resetMemory.has(key)) {
    next = resetMemory.get(key);
    resetMemory.delete(key);
  } else {
    return;
  }
  node.value = next;
  node.dispatchEvent(new Event("input", { bubbles: true }));
  node.dispatchEvent(new Event("change", { bubbles: true }));
  toast(next === fallback ? "Default value, double click again for the previous one" : "Previous value");
});

// replaceChildren that skips null children, as el() does
function fill(node, ...children) {
  node.replaceChildren(...children.flat().filter((c) => c != null));
}

async function api(method, url, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json();
}

function toast(message, isError = false) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.style.color = isError ? "var(--err)" : "";
  node.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("show"), 3500);
}

// In-page message dialog. buttons: [{ label, value, primary }]; resolves with the value of the clicked
// button, or null when the dialog is closed with Esc
function showMessage(title, text, buttons = [{ label: "OK", value: true, primary: true }]) {
  const dialog = document.getElementById("message-dialog");
  return new Promise((resolve) => {
    const done = (value) => { dialog.onclose = null; dialog.close(); resolve(value); };
    fill(document.getElementById("message-content"), el("h2", {}, title), el("p", {}, text));
    fill(document.getElementById("message-actions"), buttons.map((b) =>
      el("button", { class: b.primary ? "primary" : "", onclick: () => done(b.value) }, b.label)));
    // The close event of a previous dialog arrives late; only a close while this one is shut counts
    dialog.onclose = () => { if (!dialog.open) resolve(null); };
    dialog.showModal();
    dialog.querySelector(".dialog-actions button.primary")?.focus();
  });
}

function confirmDialog(title, text, okLabel) {
  return showMessage(title, text, [{ label: "Cancel", value: false }, { label: okLabel, value: true, primary: true }]);
}

const player = document.getElementById("player");

function setPlaying(source) {
  state.playing = source;
  markPlaying();
}

// Elements with data-src show a stop state while their source plays
function markPlaying() {
  const active = state.playing && !player.paused ? state.playing : null;
  document.querySelectorAll("[data-src]").forEach((node) => node.classList.toggle("playing", node.dataset.src === active));
}

function stopAll() {
  stop();
  wavePlayer.stop();
  padPreview.stop();
  if (seqPlayer.playing) { seqPlayer.stop(); renderSequencer(); }
  markPlaying();
}

function loadPrefs() {
  try {
    const prefs = JSON.parse(localStorage.getItem("blackbook-audio") || "{}");
    return { volume: prefs.volume ?? 1, loop: !!prefs.loop, preview: prefs.preview ?? true };
  } catch (_) { return { volume: 1, loop: false, preview: true }; }
}

function savePrefs() {
  try {
    localStorage.setItem("blackbook-audio", JSON.stringify({ volume: audioOut.volume, loop: audioOut.loop, preview: state.autoPreview }));
  } catch (_) { /* storage unavailable */ }
}

function setupAudioControls() {
  const prefs = loadPrefs();
  const volume = document.getElementById("volume");
  const loop = document.getElementById("loop-btn");
  const preview = document.getElementById("br-preview");
  const applyVolume = (v) => { audioOut.setVolume(v); player.volume = v; volume.title = `Volume ${Math.round(v * 100)} %`; };
  volume.value = prefs.volume;
  applyVolume(prefs.volume);
  audioOut.loop = prefs.loop;
  player.loop = prefs.loop;
  loop.classList.toggle("on", prefs.loop);
  state.autoPreview = prefs.preview;
  preview.checked = prefs.preview;
  volume.addEventListener("input", () => { applyVolume(Number(volume.value)); savePrefs(); });
  volume.addEventListener("dblclick", () => { volume.value = 1; applyVolume(1); savePrefs(); });
  loop.addEventListener("click", () => {
    audioOut.loop = !audioOut.loop;
    player.loop = audioOut.loop;
    loop.classList.toggle("on", audioOut.loop);
    // Running Web Audio playback follows the switch
    if (padPreview.node) padPreview.node.loop = audioOut.loop;
    if (wavePlayer.node) wavePlayer.node.loop = audioOut.loop;
    savePrefs();
  });
  preview.addEventListener("change", () => { state.autoPreview = preview.checked; savePrefs(); });
}

function stop() {
  player.pause();
  player.currentTime = 0;
  setPlaying(null);
}

// Clicking the same sample again stops it
function play(source) {
  if (!source) return;
  if (state.playing === source && !player.paused) {
    stop();
    return;
  }
  player.src = "/api/audio?src=" + encodeURIComponent(source);
  setPlaying(source);
  player.play().catch((err) => {
    setPlaying(null);
    toast("Playback failed: " + err.message, true);
  });
}

player.addEventListener("ended", () => setPlaying(null));
player.addEventListener("pause", markPlaying);
player.addEventListener("play", markPlaying);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "F1") { ev.preventDefault(); openHelp(); return; }
  if (ev.key === "Escape" && !document.getElementById("help").hidden) { closeHelp(); return; }
  if (ev.key === "Escape") stopAll();
});

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function noteName(n) { return NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1); }
// Pad 1 is bottom left (celldisppos 8) and counts to the right and upwards; the top row holds pads 9-16
function padNumber(slot) { return slot >= 8 ? slot - 7 : slot + 9; }
const PAD_SLOTS_BY_NUMBER = [8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7];
function baseName(source) { return source.split("/").pop(); }
// Readable location of a source id: card files as card paths, inbox and libraries with their root name
function sourcePath(source) {
  const [root, rel] = [source.slice(0, source.indexOf(":")), source.slice(source.indexOf(":") + 1)];
  const known = (state.roots || []).find((r) => r.id === root);
  const base = known ? known.path.replace(/[\\/]+$/, "") : root;
  return `${base}/${rel}`;
}
function fmtSeconds(s) { return s ? s.toFixed(2) + " s" : ""; }

function tagChips(container, selected, onChange) {
  container.replaceChildren(
    ...state.tags.map((tag) =>
      el("span", {
        class: "chip" + (selected.has(tag) ? " on" : ""),
        onclick: () => {
          selected.has(tag) ? selected.delete(tag) : selected.add(tag);
          tagChips(container, selected, onChange);
          onChange && onChange();
        },
      }, tag)
    )
  );
}

// ---------- theme ----------

// 'auto' follows the OS, 'dark' and 'light' are stored and set as data-theme on <html>
function applyTheme(theme) {
  if (theme !== "auto" && theme !== "light") theme = "dark";
  document.documentElement.dataset.theme = theme;
  document.querySelectorAll("#theme-switch button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeSet === theme)));
  return theme;
}

function storedTheme() {
  try { return localStorage.getItem("blackbook.theme") || "dark"; } catch (_) { return "dark"; }
}

applyTheme(storedTheme());
document.getElementById("theme-switch").addEventListener("click", (ev) => {
  const button = ev.target.closest("button[data-theme-set]");
  if (!button) return;
  const theme = applyTheme(button.dataset.themeSet);
  try {
    localStorage.setItem("blackbook.theme", theme);
  } catch (_) { /* storage unavailable */ }
});

// ---------- help ----------

function openHelp(sectionId) {
  const sections = window.BlackbookHelp.sections;
  const nav = document.getElementById("help-nav");
  const body = document.getElementById("help-body");
  if (!body.childElementCount) {
    sections.forEach((sec) => {
      nav.append(el("a", { href: "#help-" + sec.id, "data-id": sec.id, onclick: (ev) => {
        ev.preventDefault();
        document.getElementById("help-" + sec.id).scrollIntoView({ behavior: "smooth" });
      } }, sec.title));
      const node = el("section", { class: "helpsec", id: "help-" + sec.id }, el("h2", {}, sec.title));
      node.insertAdjacentHTML("beforeend", sec.html);
      body.append(node);
    });
    body.addEventListener("scroll", () => {
      let current = sections[0].id;
      for (const sec of sections) {
        if (document.getElementById("help-" + sec.id).offsetTop - body.offsetTop <= body.scrollTop + 40) current = sec.id;
      }
      nav.querySelectorAll("a").forEach((a) => a.classList.toggle("active", a.dataset.id === current));
    });
  }
  document.getElementById("help").hidden = false;
  if (sectionId) document.getElementById("help-" + sectionId)?.scrollIntoView();
  body.dispatchEvent(new Event("scroll"));
}

function closeHelp() {
  document.getElementById("help").hidden = true;
}

document.getElementById("help-btn").addEventListener("click", () => openHelp());
document.getElementById("help-close").addEventListener("click", closeHelp);
document.getElementById("help").addEventListener("click", (ev) => { if (ev.target.id === "help") closeHelp(); });

// ---------- navigation ----------

function showView(view) {
  document.querySelector(`.topbar nav button[data-view="${view}"]`).click();
}

document.querySelectorAll("nav button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b === button));
    document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + button.dataset.view));
    if (button.dataset.view === "projects") loadProjects();
    if (button.dataset.view === "backup") loadBackup();
  });
});

// ---------- library ----------

async function loadLibrary() {
  [state.patches, state.tags] = await Promise.all([api("GET", "/api/patches"), api("GET", "/api/tags")]);
  tagChips(document.getElementById("lib-tags"), state.libTags, renderLibrary);
  renderLibrary();
}

// Patch folder names on the card and their names in the UI
const TYPE_LABELS = { OneShots: "One-shot", SampInst: "Multisample", Loops: "Loop", Slicer: "Slicer", Shredder: "Shredder" };
const TRACK_LABELS = { samtrack: "One-shot", multisamtrack: "Multisample", looptrack: "Loop", slicertrack: "Slicer", granslicertrack: "Shredder" };

function typeLabel(type) { return TYPE_LABELS[type] || type; }

function renderLibrary() {
  const search = document.getElementById("lib-search").value.toLowerCase();
  const source = document.getElementById("lib-source").value;
  const type = document.getElementById("lib-type").value;
  const list = document.getElementById("lib-list");

  const items = state.patches.filter((p) =>
    (!search || p.name.toLowerCase().includes(search) || p.tags.some((t) => t.toLowerCase().includes(search))) &&
    (!source || p.root === source) &&
    (!type || p.type === type) &&
    [...state.libTags].every((t) => p.tags.includes(t))
  ).sort((a, b) => (b.is_user - a.is_user) || a.name.localeCompare(b.name) || typeLabel(a.type).localeCompare(typeLabel(b.type)));

  list.replaceChildren(
    ...items.map((p) =>
      el("div", {
        class: "row" + (p.ref === state.selectedRef ? " selected" : ""),
        onclick: () => showPatch(p.ref),
      },
      p.is_user ? el("span", { class: "badge user" }, "user") : el("span", { class: "badge factory" }, "factory"),
      el("span", { class: "name", title: p.tags.length ? "Tags: " + p.tags.join(", ") : "untagged" }, p.name),
      el("span", { class: "meta" }, typeLabel(p.type)))
    )
  );
  if (!items.length) list.append(el("p", { class: "muted", style: "padding:12px" }, "No patches match."));
}

["lib-search", "lib-source", "lib-type"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderLibrary)
);

async function showPatch(ref) {
  state.selectedRef = ref;
  renderLibrary();
  const detail = document.getElementById("lib-detail");
  detail.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  let data;
  try {
    data = await api("GET", "/api/patch?ref=" + encodeURIComponent(ref));
  } catch (err) {
    detail.replaceChildren(el("p", { class: "err" }, err.message));
    return;
  }
  const summary = state.patches.find((p) => p.ref === ref);
  const isUser = summary && summary.is_user;
  const tags = new Set(data.tags);
  const tagBox = el("div", { class: "chips" });

  const saveButton = el("button", {
    class: "primary small",
    disabled: true,
    onclick: async () => {
      try {
        const result = await api("PUT", "/api/patch/tags", { ref, tags: [...tags] });
        summary.tags = result.tags;
        saveButton.disabled = true;
        renderLibrary();
        toast("Tags saved");
      } catch (err) {
        toast(err.message, true);
      }
    },
  }, "Save tags");

  if (isUser) {
    tagChips(tagBox, tags, () => { saveButton.disabled = false; });
  } else {
    tagBox.replaceChildren(...data.tags.map((t) => el("span", { class: "chip static on" }, t)));
    if (!data.tags.length) tagBox.append(el("span", { class: "muted" }, "untagged"));
  }

  const isMulti = data.track_type === "multisamtrack";
  const rows = data.samples.filter((s) => s.filename).map((s) =>
    el("tr", {},
      el("td", {}, el("button", { class: "small playbtn", disabled: !s.source, "data-src": s.source || "", onclick: () => play(s.source) })),
      el("td", {}, s.filename, s.source ? null : el("span", { class: "err" }, " (missing)")),
      el("td", { class: "muted" }, isMulti
        ? `${s.root_name}  keys ${noteName(s.key_low)}-${noteName(s.key_high)}  vel ${s.vel_low}-${s.vel_high}`
        : s.slot != null ? "pad " + padNumber(s.slot) : ""),
      el("td", { class: "sample-actions" }, s.source && s.source.startsWith("card:")
        ? [
          el("button", { class: "small", title: isUser ? "Edit the sample, save as new file or overwrite the original" : "Edit the sample and save it as a new file, factory samples stay unchanged",
            onclick: () => openAudioEditor(s.source, { card: true, onWritten: () => showPatch(ref) }) }, "Edit wave"),
          isUser ? el("button", { class: "small", title: "Rename the file on the card and in every patch and project that uses it",
            onclick: async () => { if (await renameSample(s.source)) showPatch(ref); } }, "Rename") : null,
        ]
        : null)
    )
  );

  const editable = summary && (summary.type === "OneShots" || summary.type === "SampInst");
  const editButtons = editable
    ? el("div", { style: "margin-top:10px;display:flex;gap:8px" },
        isUser ? el("button", { class: "primary", onclick: () => loadIntoBuilder(ref, "edit") }, "Edit in builder") : null,
        el("button", { onclick: () => loadIntoBuilder(ref, "copy") }, "Use as template"))
    : el("div", { class: "muted", style: "margin-top:10px" }, "Editing of this patch type is not supported yet.");

  fill(detail,
    el("h2", {}, summary ? summary.name : ref),
    el("div", { class: "muted" }, ref.replaceAll("\\", " / "), "  ·  ", TRACK_LABELS[data.track_type] || data.track_type),
    editButtons,
    el("div", { class: "label" }, "Preview"),
    data.preview
      ? el("button", { class: "playbtn wide", "data-src": data.preview, onclick: () => play(data.preview) }, "Preview")
      : el("span", { class: "muted" }, "no preview.wav"),
    el("div", { class: "label" }, "Tags" + (isUser ? "" : " (factory, read only)")),
    tagBox,
    isUser ? el("div", { style: "margin-top:8px" }, saveButton) : null,
    el("div", { class: "label" }, `Samples (${rows.length})`),
    el("table", { class: "samples-table" }, el("tbody", {}, rows))
  );
  markPlaying();
}

// ---------- browser ----------

async function loadBrowser() {
  const select = document.getElementById("br-root");
  const label = (r) => (r.id === "card" ? "Card" : r.id === "inbox" ? "Inbox" : r.path);
  select.replaceChildren(...state.roots.map((r) => el("option", { value: r.id }, label(r))));
  setupBrowserDrop();
  select.value = state.browse.root;
  select.addEventListener("change", () => openFolder(select.value, ""));
  try {
    await openFolder("card", "Samples");
  } catch (_) {
    await openFolder("card", "");
  }
}

async function openFolder(root, path) {
  const data = await api("GET", `/api/browse?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}`);
  state.browse = { root, path: data.path, entries: data.entries };
  document.getElementById("br-root").value = root;
  document.getElementById("br-filter").value = "";
  renderBrowser();
}

function renderBrowser() {
  const { root, path, entries } = state.browse;
  const filter = document.getElementById("br-filter").value.toLowerCase();

  const crumbs = document.getElementById("br-crumbs");
  const parts = path ? path.split("/") : [];
  crumbs.replaceChildren(
    el("span", { onclick: () => openFolder(root, "") }, root === "card" ? "Card" : root === "inbox" ? "Inbox" : root),
    ...parts.flatMap((part, i) => [" / ", el("span", { onclick: () => openFolder(root, parts.slice(0, i + 1).join("/")) }, part)])
  );

  const list = document.getElementById("br-list");
  const visible = entries.filter((e) => !filter || e.name.toLowerCase().includes(filter));
  list.replaceChildren(
    ...visible.map((e) => {
      if (e.kind === "dir") {
        return el("div", { class: "row dir", onclick: () => openFolder(root, e.path) }, el("span", { class: "name" }, e.name));
      }
      const source = `${root}:${e.path}`;
      return el("div", {
        class: "row",
        draggable: "true",
        title: e.info,
        "data-src": source,
        onclick: () => { if (state.autoPreview) play(source); },
        ondragstart: (ev) => {
          ev.dataTransfer.setData("application/x-blackbook", JSON.stringify([source]));
          ev.dataTransfer.effectAllowed = "copy";
        },
      }, el("span", { class: "name" }, e.name), el("span", { class: "meta" }, fmtSeconds(e.duration)),
      el("button", { class: "small playbtn", title: "Play or stop", onclick: (ev) => { ev.stopPropagation(); play(source); } }));
    })
  );
  markPlaying();
}

document.getElementById("br-filter").addEventListener("input", renderBrowser);

function droppedSources(ev) {
  const raw = ev.dataTransfer.getData("application/x-blackbook");
  return raw ? JSON.parse(raw) : [];
}

// ---------- files dropped from outside the browser ----------

function readEntries(reader) {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

async function filesFromEntry(entry) {
  if (entry.isFile) {
    return new Promise((resolve) => entry.file((f) => resolve([f]), () => resolve([])));
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const files = [];
  // readEntries returns the directory content in batches
  for (let batch = await readEntries(reader); batch.length; batch = await readEntries(reader)) {
    for (const child of batch) files.push(...(await filesFromEntry(child)));
  }
  return files;
}

// Entries must be taken synchronously inside the drop event, reading happens afterwards
function externalEntries(ev) {
  const items = [...(ev.dataTransfer.items || [])].filter((i) => i.kind === "file");
  const entries = items.map((i) => (i.webkitGetAsEntry ? i.webkitGetAsEntry() : null)).filter(Boolean);
  return { entries, files: [...ev.dataTransfer.files] };
}

async function externalWavs({ entries, files }) {
  const all = entries.length ? (await Promise.all(entries.map(filesFromEntry))).flat() : files;
  return all.filter((f) => f.name.toLowerCase().endsWith(".wav")).sort((a, b) => a.name.localeCompare(b.name));
}

async function uploadFiles(files, root, path) {
  if (!files.length) {
    toast("No WAV files in the drop", true);
    return [];
  }
  await api("POST", "/api/import/prepare", { root, path });
  const sources = [];
  for (const [i, file] of files.entries()) {
    toast(`Importing ${i + 1} / ${files.length}: ${file.name}`);
    const url = `/api/import?root=${encodeURIComponent(root)}&path=${encodeURIComponent(path)}&name=${encodeURIComponent(file.name)}`;
    const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file });
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch (_) { /* ignore */ }
      toast(detail, true);
      continue;
    }
    sources.push((await response.json()).source);
  }
  toast(`Imported ${sources.length} of ${files.length} files`);
  return sources;
}

function makeDropTarget(node, onDrop) {
  node.addEventListener("dragover", (ev) => { ev.preventDefault(); node.classList.add("over"); });
  node.addEventListener("dragleave", () => node.classList.remove("over"));
  node.addEventListener("drop", async (ev) => {
    ev.preventDefault();
    node.classList.remove("over");
    const sources = droppedSources(ev);
    if (sources.length) {
      onDrop(sources);
      return;
    }
    // Files from the file manager go to the local inbox first and are copied into the patch on save
    const external = externalEntries(ev);
    if (!external.files.length) return;
    try {
      const uploaded = await uploadFiles(await externalWavs(external), "inbox", "");
      if (uploaded.length) onDrop(uploaded);
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// Dropping files onto the sample browser imports them into the folder shown there
function setupBrowserDrop() {
  const list = document.getElementById("br-list");
  list.addEventListener("dragover", (ev) => {
    if (ev.dataTransfer.types.includes("Files")) { ev.preventDefault(); list.classList.add("over"); }
  });
  list.addEventListener("dragleave", () => list.classList.remove("over"));
  list.addEventListener("drop", async (ev) => {
    if (!ev.dataTransfer.types.includes("Files")) return;
    ev.preventDefault();
    list.classList.remove("over");
    const external = externalEntries(ev);
    const { root, path } = state.browse;
    try {
      await uploadFiles(await externalWavs(external), root, path);
      await openFolder(root, path);
    } catch (err) {
      toast(err.message, true);
    }
  });
}

// ---------- builder: common ----------

document.querySelectorAll(".seg button").forEach((button) => {
  button.addEventListener("click", () => selectBuildType(button.dataset.type));
});

function buildBody() {
  const body = {
    type: state.buildType,
    name: document.getElementById("b-name").value,
    tags: [...state.buildTags],
    base_ref: state.baseRef,
    mode: state.mode,
  };
  if (state.buildType === "oneshot") {
    body.pads = Object.entries(state.pads).map(([slot, pad]) => ({
      slot: Number(slot), source: pad.source, loop_mode: pad.loop_mode || 0,
      params: pad.params || {}, start: pad.start ?? null, length: pad.length ?? null,
    }));
  } else {
    body.zones = state.zones.map((z) => ({
      source: z.source, root: z.root, key_low: z.key_low, key_high: z.key_high,
      vel_low: z.vel_low, vel_high: z.vel_high, vel_root: z.vel_root,
    }));
  }
  return body;
}

document.getElementById("b-plan").addEventListener("click", async () => {
  const body = buildBody();
  let plan;
  try {
    plan = await api("POST", "/api/build/plan", body);
  } catch (err) {
    toast(err.message, true);
    return;
  }
  state.pendingBody = body;
  const content = document.getElementById("plan-content");
  fill(content,
    el("p", {}, "Target: ", el("strong", {}, plan.target || "(invalid)")),
    plan.errors.length ? el("div", {}, el("div", { class: "label err" }, "Errors"), el("ul", { class: "msgs err" }, plan.errors.map((e) => el("li", {}, e)))) : null,
    plan.warnings.length ? el("div", {}, el("div", { class: "label warn" }, "Warnings"), el("ul", { class: "msgs warn" }, plan.warnings.map((w) => el("li", {}, w)))) : null,
    el("div", { class: "label" }, `Files (${plan.files.length} samples, patch.xml, preview.wav ${plan.preview_seconds} s)`),
    el("table", {}, el("tbody", {}, plan.files.map((f) => el("tr", {}, el("td", {}, f.name), el("td", { class: "muted" }, f.info), el("td", { class: "muted" }, f.source))))),
    el("div", { class: "label" }, "Tags"),
    el("div", {}, plan.tags.length ? plan.tags.join(", ") : el("span", { class: "muted" }, "none, the patch gets no index entry")),
    el("details", {}, el("summary", { class: "label" }, "patch.xml"), el("pre", {}, plan.xml))
  );
  document.getElementById("plan-apply").disabled = !plan.ok;
  document.getElementById("plan-dialog").showModal();
});

document.getElementById("plan-cancel").addEventListener("click", () => document.getElementById("plan-dialog").close());

document.getElementById("plan-apply").addEventListener("click", async () => {
  try {
    const result = await api("POST", "/api/build/apply", state.pendingBody);
    document.getElementById("plan-dialog").close();
    toast(`Written ${result.ref.replaceAll("\\", "/")} (${result.written.length} files). Use Eject before you unplug the card.`);
    await loadLibrary();
    // Continue with the saved patch in edit mode without asking again
    await loadIntoBuilder(result.ref, "edit", false, true);
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- builder: one-shot ----------

function renderPads() {
  const grid = document.getElementById("pads");
  grid.replaceChildren(
    ...Array.from({ length: 16 }, (_, slot) => {
      const pad = state.pads[slot];
      const node = el("div", {
        class: "pad" + (pad ? " filled" : "") + (pad && !pad.source ? " missing" : "") + (state.selectedPad === slot ? " selected" : ""),
        onclick: () => {
          state.selectedPad = slot;
          if (pad) previewPad(pad);
          renderPads();
        },
      }, el("span", { class: "num" }, padNumber(slot)), el("span", { class: "sample" }, pad ? (pad.source ? baseName(pad.source) : pad.filename + " (missing)") : ""));
      if (pad) {
        node.draggable = true;
        node.title = "Drag onto another pad to move it there; a filled pad swaps places";
        node.addEventListener("dragstart", (ev) => {
          ev.dataTransfer.setData("application/x-blackbook-pad", String(slot));
          ev.dataTransfer.effectAllowed = "move";
        });
      }
      node.addEventListener("drop", (ev) => {
        const from = ev.dataTransfer.getData("application/x-blackbook-pad");
        if (from === "") return;
        ev.preventDefault();
        ev.stopImmediatePropagation();
        node.classList.remove("over");
        const source = Number(from);
        if (source === slot) return;
        const moving = state.pads[source];
        const target = state.pads[slot];
        if (target) state.pads[source] = target; else delete state.pads[source];
        state.pads[slot] = moving;
        state.selectedPad = slot;
        renderPads();
      });
      makeDropTarget(node, (sources) => {
        // Several dropped files fill the following pads in pad number order
        const start = PAD_SLOTS_BY_NUMBER.indexOf(slot);
        sources.forEach((source, i) => {
          const target = PAD_SLOTS_BY_NUMBER[start + i];
          if (target === undefined) return;
          const old = state.pads[target];
          // Replacing the sample keeps the pad settings, the playback window starts over
          state.pads[target] = old
            ? { ...old, source, filename: null, start: null, length: null, frames: null }
            : { source, loop_mode: 0, params: defaultPadParams(), start: null, length: null, frames: null };
        });
        state.selectedPad = slot;
        renderPads();
      });
      return node;
    })
  );
  renderPadEditor();
}

function defaultPadParams() {
  return Object.fromEntries((state.padParams || []).map((p) => [p.key, p.default]));
}

const PAD_TABS = ["Sound", "Setup", "Env/LFO", "WAV"];

function paramControl(pad, param) {
  const params = pad.params;
  const value = params[param.key] ?? param.default;
  const label = el("span", { class: "plabel" }, param.label);
  const rerender = () => renderPadEditor();
  if (param.kind === "toggle") {
    return el("label", { class: "check" },
      el("input", { type: "checkbox", checked: value !== 0, onchange: (ev) => { params[param.key] = ev.target.checked ? 1 : 0; rerender(); } }), label);
  }
  if (param.kind === "choice") {
    return el("label", {}, label,
      el("select", { onchange: (ev) => { params[param.key] = Number(ev.target.value); refreshPadGraphics(pad); } },
        param.options.map((name, i) => el("option", { value: i, selected: i === value }, name))));
  }
  const shown = value / param.scale;
  const digits = String(param.step).split(".")[1]?.length || 0;
  const number = el("input", { type: "number", min: param.min, max: param.max, step: param.step, value: shown.toFixed(digits) });
  const slider = el("input", { type: "range", min: param.min, max: param.max, step: param.step, value: shown });
  const set = (v, from) => {
    const clamped = Math.min(param.max, Math.max(param.min, Number(v)));
    params[param.key] = Math.round(clamped * param.scale);
    if (from !== number) number.value = clamped.toFixed(digits);
    if (from !== slider) slider.value = clamped;
    refreshPadGraphics(pad);
  };
  number.addEventListener("change", () => set(number.value, number));
  slider.addEventListener("input", () => set(slider.value, slider));
  // Double click resets to the default of a new pad, a second one brings the value back
  for (const node of [number, slider]) {
    node.dataset.default = (param.default / param.scale).toFixed(digits);
    node.dataset.resetKey = `pad:${pad.source || ""}:${param.key}`;
  }
  return el("label", { class: "pnum" }, el("span", { class: "plabel" }, param.label, el("span", { class: "unit" }, param.unit)), el("span", { class: "prow" }, slider, number));
}

// ---------- waveform and audio editor ----------

state.snapZero = true;
const pcmCache = new Map();

async function loadPcm(source) {
  if (pcmCache.has(source)) return pcmCache.get(source);
  const response = await fetch("/api/pcm?src=" + encodeURIComponent(source));
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
  const rate = Number(response.headers.get("X-Sample-Rate"));
  const channels = deinterleave(await response.arrayBuffer(), Number(response.headers.get("X-Channels")));
  const entry = { rate, channels };
  pcmCache.set(source, entry);
  // Keep the cache small, samples can be long
  while (pcmCache.size > 6) pcmCache.delete(pcmCache.keys().next().value);
  return entry;
}

function snapToggle(onchange) {
  return el("label", { class: "check", title: "Every edge lands on the nearest zero crossing, so the sample starts and ends without a click" },
    el("input", { type: "checkbox", checked: state.snapZero, onchange: (ev) => { state.snapZero = ev.target.checked; if (onchange) onchange(); } }), "Snap to zero");
}

function fmtTime(frames, rate) {
  return `${(frames / rate).toFixed(3)} s`;
}

function wavTab(pad, slot) {
  const canvas = el("canvas", { class: "pad-wave" });
  const startInput = el("input", { type: "number", min: 0, step: 1 });
  const lengthInput = el("input", { type: "number", min: 0, step: 1 });
  const info = el("span", { class: "muted" }, "Reading the file ...");
  const view = new WaveView(canvas, {
    mode: "region",
    snap: () => state.snapZero,
    onChange: () => {
      pad.start = view.region.start;
      pad.length = view.region.end - view.region.start;
      syncInputs();
    },
  });
  const syncInputs = () => {
    const r = view.region;
    if (!r) return;
    startInput.value = r.start;
    lengthInput.value = r.end - r.start;
    info.textContent = `${view.frames} frames, plays ${fmtTime(r.end - r.start, view.rate)}`;
  };
  const setWindow = (start, length) => {
    const frames = pad.frames;
    pad.start = Math.min(Math.max(0, Math.round(start)), frames - 1);
    pad.length = Math.min(Math.max(1, Math.round(length)), frames - pad.start);
    view.region = { start: pad.start, end: pad.start + pad.length };
    view.draw();
    syncInputs();
  };
  startInput.addEventListener("change", () => {
    const start = view.snapFrame(Number(startInput.value));
    setWindow(start, view.region.end - start);
  });
  lengthInput.addEventListener("change", () => {
    const start = view.region.start;
    setWindow(start, view.snapFrame(start + Number(lengthInput.value)) - start);
  });

  loadPcm(pad.source).then(({ rate, channels }) => {
    if (state.pads[slot] !== pad) return;
    view.setAudio(channels, rate);
    pad.frames = view.frames;
    const start = Math.min(pad.start ?? 0, view.frames - 1);
    const length = pad.length == null || pad.length <= 0 ? view.frames - start : Math.min(pad.length, view.frames - start);
    view.region = { start, end: start + length };
    if (pad.start != null || pad.length != null) { pad.start = start; pad.length = length; }
    view.draw();
    syncInputs();
  }).catch((err) => { info.textContent = err.message; info.className = "err"; });

  return [
    el("div", { class: "wav-tools" },
      el("button", { class: "small", onclick: () => {
        if (wavePlayer.playing) return wavePlayer.stop();
        const r = view.region; if (r) wavePlayer.play(view, r.start, r.end);
      } }, "▶ Play region"),
      snapToggle(),
      el("button", { class: "small", onclick: () => setWindow(0, pad.frames) }, "Whole file"),
      el("button", { class: "small", onclick: () => openAudioEditor(pad.source, { slot }) }, "Edit audio ..."),
      info),
    canvas,
    el("div", { class: "pad-form" },
      el("label", {}, "Start (frames)", startInput),
      el("label", {}, "Length (frames)", lengthInput)),
    el("p", { class: "muted hint-small" }, "Drag the white lines to set where the pad starts and stops. The file itself is not changed; Edit audio cuts, fades and normalizes the sample."),
  ];
}

// ---------- renaming a sample on the card ----------

function askName(title, text, value) {
  const dialog = document.getElementById("message-dialog");
  return new Promise((resolve) => {
    const input = el("input", { type: "text", value, class: "rename-input", spellcheck: "false" });
    const done = (result) => { dialog.onclose = null; dialog.close(); resolve(result); };
    fill(document.getElementById("message-content"), el("h2", {}, title), el("p", {}, text), input);
    fill(document.getElementById("message-actions"),
      el("button", { onclick: () => done(null) }, "Cancel"),
      el("button", { class: "primary", onclick: () => done(input.value.trim()) }, "Next"));
    input.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); done(input.value.trim()); } });
    dialog.onclose = () => { if (!dialog.open) resolve(null); };
    dialog.showModal();
    const dot = value.toLowerCase().lastIndexOf(".wav");
    input.focus();
    input.setSelectionRange(0, dot > 0 ? dot : value.length);
  });
}

// Every place in the open page that still points to the old file follows the new name
function replaceSource(oldSource, newSource, newName) {
  const fix = (pad) => {
    if (!pad || pad.source !== oldSource) return;
    pad.source = newSource;
    if (pad.filename) pad.filename = pad.filename.replace(/[^\\/]*$/, newName);
  };
  Object.values(state.pads || {}).forEach(fix);
  if (typeof proj !== "undefined" && proj.data) {
    for (const t of proj.data.tracks) {
      t.pads.forEach(fix);
      Object.values(t.padState || {}).forEach(fix);
    }
  }
  if (typeof proj !== "undefined" && proj.padsOpen) Object.values(proj.padsOpen.pads || {}).forEach(fix);
  if (pcmCache.has(oldSource)) { pcmCache.set(newSource, pcmCache.get(oldSource)); pcmCache.delete(oldSource); }
}

// Asks for the new name, shows every patch and project that changes, then renames. Returns the result or null.
async function renameSample(source) {
  const current = source.split("/").pop();
  const name = await askName("Rename sample", "New file name on the card. Every patch and project that uses the file is updated.", current);
  if (!name) return null;
  let plan;
  try {
    plan = await api("POST", "/api/sample/rename", { source, name });
  } catch (err) { toast(err.message, true); return null; }
  const lines = [`${plan.path}`, `becomes ${plan.new_path}`, ""];
  if (plan.references.length) {
    lines.push(`Updated in ${plan.references.length} file${plan.references.length > 1 ? "s" : ""}:`);
    plan.references.forEach((r) => lines.push(`  ${r.kind === "project" ? "Project" : "Patch"} ${r.xml}`));
  } else {
    lines.push("No patch or project uses this file.");
  }
  if (plan.cache) lines.push("", "The cache file (.wav.pk) is deleted, the blackbox rebuilds it.");
  plan.warnings.forEach((w) => lines.push("", "Note: " + w));
  lines.push("", "A snapshot is taken before and after, if the backup is set up.");
  if (!(await confirmDialog("Rename sample?", lines.join("\n"), "Rename"))) return null;
  try {
    const result = await api("POST", "/api/sample/rename", { source, name, apply: true });
    replaceSource(source, result.source, result.name);
    toast(`Renamed to ${result.name}${result.references.length ? `, ${result.references.length} file(s) updated` : ""}`);
    return result;
  } catch (err) { toast(err.message, true); return null; }
}

// target.slot: the result goes onto that pad of the builder (inbox copy, original untouched).
// target.card: the result is written to the card, as a new file or over the original; target.onWritten runs after
async function openAudioEditor(source, target) {
  if (!source) return;
  const onCard = !!target.card;
  const dialog = document.getElementById("audio-editor");
  const canvas = document.getElementById("ae-wave");
  let session;
  try {
    session = await api("POST", "/api/audio-edit/open", { source });
  } catch (err) {
    toast(err.message, true);
    return;
  }
  // A fresh canvas per session drops the handlers of the previous editor view
  const fresh = canvas.cloneNode(false);
  canvas.replaceWith(fresh);
  const v = new WaveView(fresh, { mode: "select", snap: () => state.snapZero, onChange: () => status() });

  const reload = async () => {
    const response = await fetch(`/api/audio-edit/${session.id}/pcm`);
    v.setAudio(deinterleave(await response.arrayBuffer(), session.channels), session.sample_rate);
    status();
  };
  const sel = () => v.selection || { start: 0, end: v.frames };
  const status = () => {
    const s = v.selection;
    const rate = session.sample_rate;
    document.getElementById("ae-status").textContent = s
      ? `Selection ${s.start} to ${s.end} (${s.end - s.start} frames, ${fmtTime(s.end - s.start, rate)})  ·  file ${v.frames} frames, ${fmtTime(v.frames, rate)}`
      : `No selection, operations apply to the whole sample  ·  file ${v.frames} frames, ${fmtTime(v.frames, rate)}`;
    undoBtn.disabled = !session.can_undo;
    redoBtn.disabled = !session.can_redo;
  };
  const run = async (op, value = 0, needsSelection = false) => {
    if (needsSelection && !v.selection) { toast("Select a part of the sample first", true); return; }
    const { start, end } = sel();
    try {
      session = await api("POST", `/api/audio-edit/${session.id}/op`, { op, start, end, value });
    } catch (err) { toast(err.message, true); return; }
    if (op === "crop") v.selection = null;
    else if (op === "delete") v.selection = null;
    await reload();
  };
  const history = async (which) => {
    session = await api("POST", `/api/audio-edit/${session.id}/${which}`);
    v.selection = null;
    await reload();
  };
  const playToggle = () => {
    if (wavePlayer.playing) return wavePlayer.stop();
    const s = v.selection;
    wavePlayer.play(v, s ? s.start : (v.cursor ?? 0), s ? s.end : v.frames);
  };

  const gainInput = el("input", { type: "number", value: 3, step: 0.5, title: "dB" });
  const normInput = el("input", { type: "number", value: -0.3, step: 0.1, max: 0, title: "Peak level in dB" });
  const undoBtn = el("button", { class: "small", title: "Undo (Ctrl+Z)", onclick: () => history("undo") }, "Undo");
  const redoBtn = el("button", { class: "small", title: "Redo (Ctrl+Shift+Z)", onclick: () => history("redo") }, "Redo");
  const btn = (label, title, fn) => el("button", { class: "small", title, onclick: fn }, label);
  fill(document.getElementById("ae-toolbar"),
    el("div", { class: "grp" }, btn("▶ / ■", "Play or stop (Space)", playToggle)),
    el("div", { class: "grp" }, btn("+", "Zoom in", () => v.zoom(0.5)), btn("-", "Zoom out", () => v.zoom(2)),
      btn("Fit", "Show the whole sample", () => v.fit()), btn("Zoom to selection", "", () => v.zoomToSelection())),
    el("div", { class: "grp" }, snapToggle()),
    el("div", { class: "grp" },
      btn("Trim to selection", "Keep only the selection", () => run("crop", 0, true)),
      btn("Delete", "Remove the selection (Del)", () => run("delete", 0, true)),
      btn("Silence", "Replace the selection with silence", () => run("silence", 0, true))),
    el("div", { class: "grp" },
      btn("Fade in", "Fade in over the selection", () => run("fade_in", 0, true)),
      btn("Fade out", "Fade out over the selection", () => run("fade_out", 0, true)),
      btn("Reverse", "Reverse the selection or the whole sample", () => run("reverse"))),
    el("div", { class: "grp" },
      btn("Gain", "Change the level by the given dB", () => run("gain", Number(gainInput.value))), gainInput, el("span", { class: "muted" }, "dB")),
    el("div", { class: "grp" },
      btn("Normalize", "Raise the loudest peak to the given level", () => run("normalize", Number(normInput.value))), normInput, el("span", { class: "muted" }, "dB")),
    el("div", { class: "grp" }, undoBtn, redoBtn));

  const title = document.getElementById("ae-title");
  const renamable = session.source.startsWith("card:") && !session.source.startsWith("card:Patches/");
  fill(title, `Edit audio: ${session.name}`,
    renamable ? el("button", { class: "small ae-rename", title: "Rename the file on the card and in every patch and project that uses it", onclick: async () => {
      const result = await renameSample(session.source);
      if (!result) return;
      session.source = result.source;
      session.name = result.name;
      title.firstChild.textContent = `Edit audio: ${result.name}`;
      document.getElementById("ae-path").textContent = sourcePath(result.source);
      if (target.slot != null) renderPads();
      if (target.onWritten) target.onWritten(result);
    } }, "Rename") : null);
  document.getElementById("ae-path").textContent = sourcePath(session.source);
  document.getElementById("ae-format").textContent = `${session.bits} bit, ${session.sample_rate / 1000} kHz, ${session.channels === 1 ? "mono" : "stereo"}`;

  const keys = (ev) => {
    if (ev.target.tagName === "INPUT") return;
    if (ev.key === " ") { ev.preventDefault(); playToggle(); }
    else if (ev.key === "Delete" || ev.key === "Backspace") { ev.preventDefault(); run("delete", 0, true); }
    else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === "z") { ev.preventDefault(); history(ev.shiftKey ? "redo" : "undo"); }
    else if (ev.key === "+") v.zoom(0.5);
    else if (ev.key === "-") v.zoom(2);
  };
  const close = () => {
    wavePlayer.stop();
    dialog.removeEventListener("keydown", keys);
    dialog.onclose = null;
    dialog.close();
  };
  const discard = () => {
    api("DELETE", `/api/audio-edit/${session.id}`).catch(() => {});
    close();
    if (!onCard) renderPads();
  };
  const useOnPad = async () => {
    if (session.changed) {
      try {
        const saved = await api("POST", `/api/audio-edit/${session.id}/save`);
        const current = state.pads[target.slot];
        if (current) {
          Object.assign(current, { source: saved.source, filename: null, start: null, length: null, frames: saved.frames });
        }
        toast(`Edited sample stored as ${saved.name}. It is copied into the patch when you save the patch.`);
      } catch (err) { toast(err.message, true); }
      close();
      renderPads();
    } else {
      discard();
    }
  };
  const writeToCard = async (mode) => {
    if (!session.changed) { toast("Nothing changed yet", true); return; }
    let impact;
    try {
      impact = await api("GET", `/api/audio-edit/${session.id}/impact`);
    } catch (err) { toast(err.message, true); return; }
    if (mode === "overwrite") {
      if (!impact.can_overwrite) { await showMessage("Cannot overwrite", impact.reason); return; }
      const lines = [
        `${impact.path} is replaced by the edited version (${impact.frames_before} frames before, ${impact.frames_after} after).`,
        "Markers and loop points inside the file move with the edit.",
        "",
      ];
      if (impact.references.length) {
        lines.push(`blackbook adjusts start, length, loop and slice positions in ${impact.references.length} file${impact.references.length > 1 ? "s" : ""}:`);
        impact.references.forEach((r) => lines.push(`  ${r.kind === "project" ? "Project" : "Patch"} ${r.xml}: ${r.changes.join("; ")}`));
      } else {
        lines.push("No patch or project uses this file.");
      }
      if (impact.cache) lines.push("", "The cache file next to it (.wav.pk) is deleted, the blackbox rebuilds it.");
      lines.push("", "A snapshot of the card is taken before and after, if the backup is set up.");
      if (!(await confirmDialog("Overwrite the original?", lines.join("\n"), "Overwrite"))) return;
    }
    try {
      const result = await api("POST", `/api/audio-edit/${session.id}/write`, { mode });
      close();
      toast(mode === "new"
        ? `Saved as ${result.path}`
        : `${result.name} overwritten${result.adjusted.length ? `, ${result.adjusted.length} file(s) adjusted` : ""}`);
      if (target.onWritten) target.onWritten(result);
    } catch (err) { toast(err.message, true); }
  };
  const applyBtn = document.getElementById("ae-apply");
  const newBtn = document.getElementById("ae-new");
  const overwriteBtn = document.getElementById("ae-overwrite");
  applyBtn.hidden = onCard;
  newBtn.hidden = !onCard;
  overwriteBtn.hidden = !onCard;
  document.getElementById("ae-cancel").onclick = discard;
  applyBtn.onclick = useOnPad;
  newBtn.onclick = () => writeToCard("new");
  overwriteBtn.onclick = () => writeToCard("overwrite");
  dialog.onclose = discard;
  dialog.addEventListener("keydown", keys);
  dialog.showModal();
  await reload();
}

// ---------- pad preview and graphics ----------

// Preview of what can be reproduced close to the device: level, pitch, pan, reverse, start and length.
// Filter, resonance, overdrive, envelope, LFO and the effect sends are left out on purpose.
const padPreview = {
  ctx: null,
  node: null,
  stop() {
    if (this.node) { try { this.node.stop(); } catch (_) { /* already stopped */ } this.node = null; }
  },
};

async function previewPad(pad) {
  if (!pad || !pad.source) return;
  // A second click on the same pad stops it, another pad takes over
  const same = padPreview.node && padPreview.pad === pad;
  padPreview.stop();
  if (same) return;
  stop();
  let audio;
  try { audio = await loadPcm(pad.source); } catch (err) { toast(err.message, true); return; }
  const p = pad.params || {};
  const frames = audio.channels[0].length;
  const start = Math.min(pad.start ?? 0, frames - 1);
  const length = Math.max(1, Math.min(pad.length && pad.length > 0 ? pad.length : frames - start, frames - start));
  const ctx = audioOut.context();
  const buffer = ctx.createBuffer(audio.channels.length, length, audio.rate);
  audio.channels.forEach((data, c) => {
    const part = data.slice(start, start + length);
    if (p.reverse) part.reverse();
    buffer.copyToChannel(part, c);
  });
  const node = ctx.createBufferSource();
  node.buffer = buffer;
  node.playbackRate.value = Math.pow(2, (p.pitch || 0) / 1000 / 12);
  const gain = ctx.createGain();
  gain.gain.value = Math.pow(10, (p.gaindb || 0) / 1000 / 20);
  const pan = ctx.createStereoPanner();
  pan.pan.value = Math.max(-1, Math.min(1, (p.panpos || 0) / 1000));
  node.loop = audioOut.loop;
  node.connect(gain).connect(pan).connect(audioOut.master);
  node.onended = () => { if (padPreview.node === node) padPreview.node = null; markPlaying(); };
  padPreview.node = node;
  padPreview.pad = pad;
  node.start();
  markPlaying();
}

// Envelope times at 100 % from the device manual: attack about 9 s, decay and release about 38 s
const ENV_MAX_SECONDS = { envattack: 9, envdecay: 38, envrel: 38 };
const SVG_NS = "http://www.w3.org/2000/svg";

function svgEl(tag, attrs) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

function envSeconds(params, key) { return ((params[key] ?? 0) / 1000) * ENV_MAX_SECONDS[key]; }

function fmtSec(s) { return s < 1 ? `${Math.round(s * 1000)} ms` : `${s.toFixed(s < 10 ? 2 : 1)} s`; }

function drawEnvelope(svg, params) {
  const w = 300, h = 90, top = 6, bottom = h - 6;
  const a = envSeconds(params, "envattack"), d = envSeconds(params, "envdecay"), r = envSeconds(params, "envrel");
  const sus = (params.envsus ?? 1000) / 1000;
  // Square root scale keeps short and long times readable side by side
  const part = (s) => Math.sqrt(s / 38);
  const hold = 0.35;
  const total = part(a) + part(d) + hold + part(r) || 1;
  const x = (u) => (u / total) * w;
  const y = (level) => bottom - level * (bottom - top);
  const xa = x(part(a)), xd = xa + x(part(d)), xs = xd + x(hold), xr = xs + x(part(r));
  svg.replaceChildren(
    svgEl("line", { x1: 0, y1: bottom, x2: w, y2: bottom, class: "gaxis" }),
    svgEl("polyline", { points: `0,${y(0)} ${xa},${y(1)} ${xd},${y(sus)} ${xs},${y(sus)} ${xr},${y(0)}`, class: "gline" }));
  return `Attack ${fmtSec(a)} · Decay ${fmtSec(d)} · Sustain ${Math.round(sus * 100)} % · Release ${fmtSec(r)}`;
}

function lfoValue(shape, phase, step) {
  const t = phase % 1;
  switch (shape) {
    case 0: return 1 - 2 * t; // Rev Saw
    case 1: return 2 * t - 1; // Saw
    case 2: return t < 0.5 ? 4 * t - 1 : 3 - 4 * t; // Triangle
    case 3: return t < 0.5 ? 2 * t : 2 - 2 * t; // Pos Tri
    case 4: return Math.sin(2 * Math.PI * t); // Sine
    case 5: return 0.5 + 0.5 * Math.sin(2 * Math.PI * t); // Pos Sine
    case 6: return t < 0.5 ? 1 : -1; // Square
    case 7: return t < 0.5 ? 1 : 0; // Pos Square
    default: { const v = Math.sin(step * 12.9898) * 43758.5453; return 2 * (v - Math.floor(v)) - 1; } // Random steps
  }
}

function drawLfo(svg, params) {
  const w = 300, h = 90, mid = h / 2, amp = (h / 2 - 6) * ((params.lfoamount ?? 1000) / 1000);
  const shape = params.lfowave ?? 0;
  const points = [];
  const cycles = 2, n = 240;
  for (let i = 0; i <= n; i++) {
    const phase = (i / n) * cycles;
    const step = Math.floor(phase * 8);
    points.push(`${(i / n) * w},${mid - lfoValue(shape, phase, step) * amp}`);
  }
  svg.replaceChildren(
    svgEl("line", { x1: 0, y1: mid, x2: w, y2: mid, class: "gaxis" }),
    svgEl("polyline", { points: points.join(" "), class: "gline" }));
}

function refreshPadGraphics(pad) {
  const env = document.getElementById("env-graph");
  const lfo = document.getElementById("lfo-graph");
  if (env) document.getElementById("env-caption").textContent = drawEnvelope(env, pad.params);
  if (lfo) drawLfo(lfo, pad.params);
}

function envLfoGraphics() {
  const graph = (id) => svgEl("svg", { id, viewBox: "0 0 300 90", preserveAspectRatio: "none", class: "pgraph" });
  return el("div", { class: "pgraphs" },
    el("figure", {}, graph("env-graph"), el("figcaption", { id: "env-caption", class: "muted" })),
    el("figure", {}, graph("lfo-graph"), el("figcaption", { class: "muted" }, "LFO shape and depth")));
}

// Pad clipboard as on the device: Clear and Copy keep the pad, Paste puts it on the selected pad
function copyPad(slot) {
  const pad = state.pads[slot];
  if (!pad) return;
  state.padClipboard = structuredClone(pad);
  toast(`Pad ${padNumber(slot)} copied`);
  renderPadEditor();
}

function clearPad(slot) {
  const pad = state.pads[slot];
  if (!pad) return;
  state.padClipboard = structuredClone(pad);
  delete state.pads[slot];
  toast(`Pad ${padNumber(slot)} cleared. Paste brings it back.`);
  renderPads();
}

function pastePad(slot) {
  if (slot == null || !state.padClipboard) return;
  state.pads[slot] = structuredClone(state.padClipboard);
  state.selectedPad = slot;
  renderPads();
}

function clipboardLabel() {
  const c = state.padClipboard;
  return c ? (c.source ? baseName(c.source) : c.filename) : "";
}

document.addEventListener("keydown", (ev) => {
  if (!(ev.ctrlKey || ev.metaKey) || ev.altKey) return;
  const inBuild = document.getElementById("view-build").classList.contains("active") && state.buildType === "oneshot";
  const inProject = typeof proj !== "undefined" && proj.padsOpen && document.getElementById("view-projects").classList.contains("active");
  if (!inBuild && !inProject) return;
  if (["INPUT", "TEXTAREA", "SELECT"].includes(ev.target.tagName) || document.querySelector("dialog[open]")) return;
  const key = ev.key.toLowerCase();
  const slot = state.selectedPad;
  if (slot == null) return;
  if (key === "c") { ev.preventDefault(); copyPad(slot); }
  else if (key === "x") { ev.preventDefault(); clearPad(slot); }
  else if (key === "v") { ev.preventDefault(); pastePad(slot); }
});

function renderPadEditor() {
  const panel = document.getElementById("pad-editor");
  const slot = state.selectedPad;
  const pad = slot != null ? state.pads[slot] : null;
  if (!pad) {
    fill(panel,
      el("span", { class: "muted" }, slot == null ? "Select a pad." : `Pad ${padNumber(slot)} is empty. Drop a WAV onto it.`),
      slot != null && state.padClipboard
        ? el("button", { class: "small", style: "margin-left:10px", title: "Ctrl+V", onclick: () => pastePad(slot) }, `Paste ${clipboardLabel()}`)
        : null);
    return;
  }

  if (!pad.source) {
    panel.replaceChildren(
      el("strong", {}, `Pad ${padNumber(slot)}: ${pad.filename}`),
      el("p", { class: "err" }, "The file of this pad is missing on the card. The pad stays unchanged unless you drop a new sample onto it or clear it."),
      el("button", { class: "small", onclick: () => clearPad(slot) }, "Clear"));
    return;
  }

  pad.params = { ...defaultPadParams(), ...(pad.params || {}) };
  const tab = state.padTab || "Sound";
  let content;
  if (tab === "WAV") {
    content = wavTab(pad, slot);
  } else {
    const visible = (state.padParams || []).filter((p) => p.group === tab && (!p.when || (pad.params[p.when[0]] ?? 0) === p.when[1]));
    content = [el("div", { class: "pad-form" }, visible.map((p) => paramControl(pad, p)))];
    if (tab === "Env/LFO") content.unshift(envLfoGraphics());
    if (tab !== "Setup") {
      content.push(el("p", { class: "muted hint-small" }, tab === "Env/LFO"
        ? "The envelope curve is an approximation: times follow the device manual (attack up to about 9 s, decay and release up to about 38 s), the exact curve shape is unknown. Envelope and LFO are heard on the device only."
        : "▶ plays the pad with level, pitch, pan, reverse, start and length. Filter, resonance, overdrive, delay and reverb are heard on the device only."));
    }
  }

  fill(panel,
    el("div", { class: "pad-head" },
      el("span", { class: "pad-title" }, el("strong", {}, `Pad ${padNumber(slot)}: ${baseName(pad.source)}`), el("span", { class: "muted path" }, sourcePath(pad.source))),
      el("span", {},
        el("button", { class: "small", title: "Preview with level, pitch, pan, reverse, start and length", onclick: () => previewPad(pad) }, "▶"), " ",
        el("button", { class: "small", title: "Copy pad with all settings (Ctrl+C)", onclick: () => copyPad(slot) }, "Copy"), " ",
        state.padClipboard ? el("button", { class: "small", title: `Replace this pad with ${clipboardLabel()} (Ctrl+V)`, onclick: () => pastePad(slot) }, "Paste") : null,
        state.padClipboard ? " " : null,
        el("button", { class: "small", title: "Remove the sample from this pad; Paste brings it back (Ctrl+X)", onclick: () => clearPad(slot) }, "Clear"))),
    el("div", { class: "tabs" }, PAD_TABS.map((name) =>
      el("button", { class: name === tab ? "active" : "", onclick: () => { state.padTab = name; renderPadEditor(); } }, name))),
    ...content,
  );
  if (tab === "Env/LFO") refreshPadGraphics(pad);
}

// ---------- builder: multisample ----------

const msDrop = document.getElementById("ms-drop");
makeDropTarget(msDrop, (sources) => addZones(sources));

async function addZones(sources) {
  const known = new Set(state.zones.map((z) => z.source));
  const fresh = [...new Set(sources)].filter((s) => !known.has(s));
  if (!fresh.length) return;
  const gap_rule = document.getElementById("ms-gap").value;
  try {
    const added = await api("POST", "/api/multisample/automap", { sources: fresh, gap_rule });
    const remapped = await api("POST", "/api/multisample/remap", { zones: [...state.zones, ...added], gap_rule });
    // Keep detection warnings, the remap only recalculates key ranges
    state.zones = remapped.map((z, i) => ({ ...z, warnings: ([...state.zones, ...added][i].warnings) || [] }));
  } catch (err) {
    toast(err.message, true);
    return;
  }
  renderZones();
}

document.getElementById("ms-add-folder").addEventListener("click", () => {
  const { root, entries } = state.browse;
  const sources = entries.filter((e) => e.kind === "wav").map((e) => `${root}:${e.path}`);
  if (!sources.length) return toast("No WAVs in the current folder", true);
  addZones(sources);
});

document.getElementById("ms-remap").addEventListener("click", async () => {
  if (!state.zones.length) return;
  state.zones = await api("POST", "/api/multisample/remap", { zones: state.zones, gap_rule: document.getElementById("ms-gap").value });
  renderZones();
});

document.getElementById("ms-clear").addEventListener("click", () => { state.zones = []; renderZones(); });

function renderZones() {
  const tbody = document.querySelector("#ms-table tbody");
  document.getElementById("ms-empty").hidden = state.zones.length > 0;
  const num = (zone, key, min, max) =>
    el("input", { type: "number", min, max, value: zone[key], oninput: (ev) => { zone[key] = Number(ev.target.value); renderKeyboard(); } });

  tbody.replaceChildren(
    ...state.zones.map((zone, i) =>
      el("tr", {},
        el("td", {}, el("button", { class: "small", onclick: () => play(zone.source) }, "▶"), " ", baseName(zone.source),
          zone.warnings && zone.warnings.length ? el("div", { class: "warn", style: "font-size:12px" }, zone.warnings.join("; ")) : null),
        el("td", {}, num(zone, "root", 0, 127), " ", el("span", { class: "muted" }, noteName(zone.root))),
        el("td", {}, num(zone, "key_low", 0, 127), " - ", num(zone, "key_high", 0, 127)),
        el("td", {}, num(zone, "vel_low", 0, 127), " - ", num(zone, "vel_high", 0, 127)),
        el("td", {}, el("button", { class: "small", onclick: () => { state.zones.splice(i, 1); renderZones(); } }, "✕")))
    )
  );
  renderKeyboard();
}

function renderKeyboard() {
  const kb = document.getElementById("ms-keyboard");
  const width = 100 / 128;
  const roots = [...new Set(state.zones.map((z) => z.root))].sort((a, b) => a - b);
  const nodes = [];
  for (let octave = 0; octave < 11; octave++) {
    nodes.push(el("span", { class: "oct", style: `left:${octave * 12 * width}%` }, "C" + (octave - 1)));
  }
  state.zones.forEach((z) => {
    const hue = (roots.indexOf(z.root) * 47) % 360;
    const top = 100 - (z.vel_high / 127) * 100;
    const height = ((z.vel_high - z.vel_low + 1) / 128) * 100;
    nodes.push(el("div", {
      class: "zone",
      title: `${baseName(z.source)}: ${noteName(z.key_low)}-${noteName(z.key_high)}, vel ${z.vel_low}-${z.vel_high}`,
      style: `left:${z.key_low * width}%;width:${(z.key_high - z.key_low + 1) * width}%;top:${top}%;height:${height}%;background:hsl(${hue} 45% 40%)`,
    }));
    nodes.push(el("div", { class: "root", style: `left:${(z.root + 0.5) * width}%` }));
  });
  kb.replaceChildren(...nodes);
}

// ---------- builder: edit and template mode ----------

function selectBuildType(type) {
  state.buildType = type;
  document.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("active", b.dataset.type === type));
  document.getElementById("b-oneshot").hidden = type !== "oneshot";
  document.getElementById("b-multisample").hidden = type !== "multisample";
}

function renderMode() {
  const banner = document.getElementById("b-mode");
  const name = document.getElementById("b-name");
  name.readOnly = state.mode === "edit";
  document.querySelectorAll(".seg button").forEach((b) => { b.disabled = state.mode !== "new"; });
  // The edit notice is shown once when a patch is loaded; after "Keep editing" or a save it stays away
  if (state.mode === "new" || (state.mode === "edit" && state.editAcknowledged)) {
    banner.hidden = true;
    return;
  }
  const name_ = state.baseRef.split("\\").pop();
  banner.hidden = false;
  const text = state.mode === "edit"
    ? [el("strong", {}, `You are editing "${name_}".`), " Saving overwrites this patch on the card. A backup snapshot is made right before."]
    : [el("strong", {}, `Template: "${name_}".`), " Saving creates a new user patch with the name above. The original stays unchanged."];
  fill(banner,
    el("span", { class: "grow" }, ...text),
    state.mode === "edit"
      ? el("button", { class: "small primary", title: "Edit this patch; saving overwrites it", onclick: () => { state.editAcknowledged = true; renderMode(); } }, "Keep editing")
      : null,
    state.mode === "edit"
      ? el("button", { class: "small", title: "Keep the original and save the changes under a new name", onclick: () => { state.mode = "copy"; document.getElementById("b-name").value += " copy"; renderMode(); } }, "Save as new patch instead")
      : null,
    el("button", { class: "small", title: "Discard all changes and start with an empty builder", onclick: resetBuilder }, "Discard and start empty"));
}

function resetBuilder() {
  state.mode = "new";
  state.baseRef = null;
  state.pads = {};
  state.zones = [];
  state.selectedPad = null;
  state.buildTags.clear();
  document.getElementById("b-name").value = "";
  tagChips(document.getElementById("b-tags"), state.buildTags);
  renderPads();
  renderZones();
  renderMode();
  // A new build starts with the sample browser at the top of the card
  openFolder("card", "").catch(() => {});
}

async function loadIntoBuilder(ref, mode, switchView = true, acknowledged = false) {
  let data;
  try {
    data = await api("GET", "/api/patch/load?ref=" + encodeURIComponent(ref));
  } catch (err) {
    toast(err.message, true);
    return;
  }
  state.mode = mode;
  state.baseRef = ref;
  state.editAcknowledged = acknowledged;
  state.buildTags = new Set(data.tags);
  tagChips(document.getElementById("b-tags"), state.buildTags);
  document.getElementById("b-name").value = mode === "edit" ? data.name : data.name + " copy";
  selectBuildType(data.type);
  if (data.type === "oneshot") {
    state.pads = {};
    data.pads.forEach((p) => { state.pads[p.slot] = p; });
    state.selectedPad = data.pads.length ? PAD_SLOTS_BY_NUMBER.find((s) => state.pads[s]) : null;
    renderPads();
  } else {
    state.zones = data.zones;
    renderZones();
  }
  renderMode();
  if (data.missing && data.missing.length) toast(`${data.missing.length} referenced files are missing on the card`, true);
  else if (data.adjusted && data.adjusted.length) {
    showMessage("Sample shorter than the patch",
      `The file on the card is shorter than the patch expects (${data.adjusted.join(", ")}), for example after restoring a WAV from the backup. Start and length were shortened to the file. Saving the patch writes the shortened values.`);
  }
  if (switchView) document.querySelector('nav button[data-view="build"]').click();
}

// ---------- projects ----------

async function loadProjects() {
  const wrap = document.getElementById("proj-list");
  if (!state.projects) wrap.replaceChildren(el("p", { class: "muted", style: "padding:12px" }, "Loading..."));
  try {
    state.projects = await api("GET", "/api/projects");
  } catch (err) {
    wrap.replaceChildren(el("p", { class: "err", style: "padding:12px" }, err.message));
    return;
  }
  renderProjectList();
  if (state.selectedProject && state.projects.some((p) => p.name === state.selectedProject)) showProject(state.selectedProject);
}

function fmtAgo(seconds) {
  const diff = Date.now() / 1000 - seconds;
  if (diff < 90) return "just now";
  if (diff < 3600) return `${Math.round(diff / 60)} min ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)} h ago`;
  if (diff < 86400 * 14) return `${Math.round(diff / 86400)} days ago`;
  return new Date(seconds * 1000).toLocaleDateString();
}

const META_ICONS = {
  metronome: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round" stroke-linecap="round"><path d="M5.5 2h5l2.5 12H3z"/><path d="M8 11l3.5-7"/><path d="M5 11h6"/></svg>',
  wave: '<svg viewBox="0 0 16 16" fill="currentColor"><rect x="1" y="6.5" width="1.6" height="3" rx=".8"/><rect x="4" y="4" width="1.6" height="8" rx=".8"/><rect x="7" y="1.5" width="1.6" height="13" rx=".8"/><rect x="10" y="4.5" width="1.6" height="7" rx=".8"/><rect x="13" y="6" width="1.6" height="4" rx=".8"/></svg>',
};

function metaIcon(name, text, cls, title) {
  const icon = el("span", { class: "mi" });
  icon.innerHTML = META_ICONS[name];
  return el("span", { class: "pc-mi " + cls, title }, icon, text);
}

function renderProjectList() {
  const wrap = document.getElementById("proj-list");
  const search = document.getElementById("proj-search").value.trim().toLowerCase();
  const sort = document.getElementById("proj-sort").value;
  const type = document.getElementById("proj-type").value;
  const autosave = document.getElementById("proj-autosave").checked;
  const missingOnly = document.getElementById("proj-missing").checked;
  const projects = (state.projects || []).filter((p) =>
    (autosave || !p.is_autosave) &&
    (!missingOnly || p.missing.length) &&
    (!type || p.tracks.some((t) => t.type === type)) &&
    (!search || p.name.toLowerCase().includes(search) || p.tracks.some((t) => t.name.toLowerCase().includes(search))));
  const order = {
    name: (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }),
    modified: (a, b) => b.modified - a.modified,
    tempo: (a, b) => a.tempo - b.tempo || a.name.localeCompare(b.name),
  }[sort];
  projects.sort(order);
  wrap.replaceChildren(...projects.map((p) => {
    const strip = el("div", { class: "pc-strip" }, [0, 1, 2, 3].map((pos) => {
      const t = p.tracks.find((x) => x.position === pos);
      if (!t) return el("span", { class: "pc-slot empty" });
      const icon = trackIcon(t.type);
      icon.title = `${pos + 1}: ${t.name || TRACK_LABELS[t.type] || t.type} (${TRACK_LABELS[t.type] || t.type})`;
      return el("span", { class: "pc-slot", style: `--track:${TRACK_COLORS[pos]}` }, icon);
    }));
    return el("div", {
      class: "pcard" + (p.name === state.selectedProject ? " selected" : ""),
      "data-name": p.name,
      title: "Show tracks, sequences and samples of this project",
      onclick: () => showProject(p.name),
    },
      el("div", { class: "pc-top" },
        el("span", { class: "pc-name" }, p.name.replace(/ - autosave$/, "")),
        p.is_autosave ? el("span", { class: "badge" }, "autosave") : null),
      strip,
      el("div", { class: "pc-meta" },
        metaIcon("metronome", p.tempo ? String(p.tempo) : "-", "", "Tempo in BPM"),
        metaIcon("wave", String(p.references), "", "Sample references"),
        p.missing.length
          ? metaIcon("wave", String(p.missing.length), "err", "Missing samples:\n" + p.missing.join("\n"))
          : el("span"),
        el("span", { class: "pc-ago", title: "Last changed " + new Date(p.modified * 1000).toLocaleString() }, fmtAgo(p.modified))));
  }));
  if (!projects.length) {
    wrap.append(el("p", { class: "muted", style: "padding:12px" }, (state.projects || []).length ? "No project matches." : "No projects on the card."));
  }
}

["proj-search", "proj-sort", "proj-type", "proj-autosave", "proj-missing"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderProjectList));

async function renderProjectSamples(name, detail) {
  if (!detail) return;
  let samples;
  try {
    samples = await api("GET", "/api/project/samples?name=" + encodeURIComponent(name));
  } catch (err) {
    detail.replaceChildren(el("p", { class: "err" }, err.message));
    return;
  }
  fill(detail,
    el("div", { class: "label" }, `Samples of ${name} (${samples.length})`),
    el("table", { class: "samples-table" }, el("tbody", {}, samples.map((s) =>
      el("tr", {},
        el("td", {}, el("button", { class: "small playbtn", disabled: !s.source, "data-src": s.source || "", onclick: () => play(s.source) })),
        el("td", {}, s.path || s.filename, s.source ? null : el("span", { class: "err" }, " (missing)")),
        el("td", { class: "muted" }, s.uses > 1 ? `${s.uses} uses` : ""),
        el("td", { class: "sample-actions" }, s.source
          ? [
            el("button", { class: "small", title: "Edit the sample, save as new file or overwrite the original", onclick: () => openAudioEditor(s.source, { card: true, onWritten: () => showProject(name) }) }, "Edit wave"),
            s.path && !s.path.startsWith("Patches/")
              ? el("button", { class: "small", title: "Rename the file on the card and in every patch and project that uses it",
                onclick: async () => { if (await renameSample(s.source)) renderProjectSamples(name, detail); } }, "Rename")
              : null,
          ]
          : null))))));
  markPlaying();
}

// ---------- backup ----------

function fmtBytes(n) {
  if (n > 1e9) return (n / 1e9).toFixed(2) + " GB";
  if (n > 1e6) return (n / 1e6).toFixed(1) + " MB";
  return Math.round(n / 1e3) + " kB";
}

function fmtDate(iso) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

function groupKey(path) {
  const parts = path.split("/");
  if (parts[0] === "Projects" && parts.length > 2) return parts.slice(0, 2).join("/");
  if ((parts[0] === "UserPatches" || parts[0] === "Patches") && parts.length > 3) return parts.slice(0, 3).join("/");
  if (parts[0] === "Samples" && parts.length > 2) return parts.slice(0, 2).join("/");
  return path;
}

function eventsBox(events) {
  const filter = el("input", { type: "search", placeholder: "Filter events", value: state.eventsFilter || "" });
  const body = el("tbody");
  const renderRows = () => {
    const q = (state.eventsFilter || "").toLowerCase();
    const shown = events.filter((e) => !q || e.text.toLowerCase().includes(q) || e.time.includes(q));
    fill(body, shown.length
      ? shown.map((e) => el("tr", {}, el("td", { class: "muted" }, e.time), el("td", {}, e.text)))
      : el("tr", {}, el("td", { class: "muted" }, "No matching events.")));
  };
  filter.addEventListener("input", () => { state.eventsFilter = filter.value; renderRows(); });
  renderRows();
  const box = el("details", { class: "events", open: !!state.eventsOpen },
    el("summary", { class: "label" }, `Events since start (${events.length})`),
    filter,
    el("div", { class: "events-scroll" }, el("table", { class: "facts" }, body)));
  box.addEventListener("toggle", () => { state.eventsOpen = box.open; });
  return box;
}

async function loadBackup() {
  const status = await api("GET", "/api/backup/status");
  const target = document.getElementById("bk-target");
  if (status.target && document.activeElement !== target) target.value = status.target;
  if (!status.target && !target.value && state.suggestedBackup) target.value = state.suggestedBackup;

  const facts = [];
  if (!status.target) facts.push(["Backup", "no folder set"]);
  else if (!status.initialized) facts.push(["Backup", "folder not initialized yet"]);
  else {
    facts.push(["Snapshots", `${status.commits}` + (status.last ? `, last ${fmtDate(status.last.date)}` : "")]);
    facts.push(["Size", `${fmtBytes(status.size_bytes)} in total (card copy ${fmtBytes(status.mirror_bytes)}, history ${fmtBytes(status.history_bytes)})`]);
  }
  facts.push(["Card", status.card_present ? "connected" : "not connected"]);
  if (status.git_missing) facts.unshift(["Problem", el("span", { class: "err" }, status.git_missing)]);
  if (status.in_use_by) facts.unshift(["Problem", el("span", { class: "err" }, status.in_use_by.charAt(0).toUpperCase() + status.in_use_by.slice(1))]);
  if (status.inside_program) facts.unshift(["Problem", el("span", { class: "err" }, "The backup folder is inside the blackbook folder. An update or a new installation could delete it. Choose a folder outside with Browse, then move or delete the old one.")]);
  const events = status.events || [];
  state.backupStamp = `${status.commits}|${events.length ? events[0].time + events[0].text : ""}`;
  fill(document.getElementById("bk-status"),
    el("table", { class: "facts" }, el("tbody", {}, facts.map(([k, v]) => el("tr", {}, el("td", { class: "muted" }, k), el("td", {}, v))))),
    events.length ? eventsBox(events) : null);
  state.backupInitialized = status.initialized;
  setBackupBusy(!!state.backupBusy, document.getElementById("bk-snapshot").textContent);

  if (!status.initialized) {
    document.getElementById("bk-log").replaceChildren();
    return;
  }
  const [log, config] = await Promise.all([api("GET", "/api/backup/log"), api("GET", "/api/backup/config")]);
  const configBox = document.getElementById("bk-config");
  if (document.activeElement !== configBox) configBox.value = config.text;

  document.getElementById("bk-log").replaceChildren(
    ...log.map((c) =>
      el("div", {
        class: "row" + (c.id === state.selectedCommit ? " selected" : ""),
        onclick: () => showCommit(c.id, log),
      }, el("span", { class: "name" }, c.subject), el("span", { class: "meta" }, fmtDate(c.date) + "  ·  " + c.id.slice(0, 10)))
    )
  );
  if (!log.length) document.getElementById("bk-log").append(el("p", { class: "muted", style: "padding:10px" }, "No snapshots yet."));
}

// Explanation for restoring a single WAV: only the file comes back, patches and projects stay as they are
async function wavRestoreNote(commit, path) {
  let check;
  try {
    check = await api("GET", `/api/backup/restore-check?commit=${encodeURIComponent(commit)}&path=${encodeURIComponent(path)}`);
  } catch (_) { return ""; }
  if (!check.is_wav) return "";
  const lines = ["", "", "Only this WAV file is restored. Patches and projects that use it are not changed."];
  if (!check.in_snapshot) lines.push("The file does not exist in this snapshot, so it is deleted from the card.");
  const refs = check.references || [];
  if (refs.length) {
    lines.push("", `Used in ${refs.length} place${refs.length === 1 ? "" : "s"}:`);
    const shown = refs.slice(0, 12).map((r) => `  ${r.kind === "project" ? "Project" : "Patch"}: ${r.xml.split("/").slice(0, -1).join("/")}  (length ${r.samlen} frames)`);
    lines.push(...shown);
    if (refs.length > 12) lines.push(`  and ${refs.length - 12} more`);
  } else {
    lines.push("", "No patch or project on the card uses this file.");
  }
  const mismatch = check.frames_snapshot != null && refs.some((r) => r.samlen && r.samlen > check.frames_snapshot);
  if (check.frames_snapshot != null && check.frames_now != null && check.frames_snapshot !== check.frames_now) {
    lines.push("", `The length changes from ${check.frames_now} to ${check.frames_snapshot} frames.`);
  }
  if (mismatch) {
    lines.push("Some of the places above play more frames than the restored file has. Restore the whole patch or project folder instead to keep everything consistent.");
  }
  return lines.join("\n");
}

async function restore(commit, path, label) {
  const scope = path ? `"${path}"` : "ALL backed up folders";
  const wavNote = path ? await wavRestoreNote(commit, path) : "";
  const ok = await confirmDialog(
    "Restore from backup",
    `Restore ${scope} from snapshot ${commit.slice(0, 10)}?\n\nThe current card state is saved as a snapshot first. Within the restored scope, files that do not exist in the snapshot are deleted from the card.${wavNote}`,
    "Restore");
  if (!ok) return;
  try {
    const result = await api("POST", "/api/backup/restore", { commit, path });
    toast(`${label}: ${result.restored.length} files restored, ${result.removed.length} removed`);
    await loadBackup();
    await loadLibrary();
  } catch (err) {
    toast(err.message, true);
  }
}

async function showCommit(id, log) {
  state.selectedCommit = id;
  const commit = log.find((c) => c.id === id);
  document.querySelectorAll("#bk-log .row").forEach((row, i) => row.classList.toggle("selected", log[i].id === id));
  const detail = document.getElementById("bk-detail");
  detail.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  const changes = await api("GET", "/api/backup/commit?id=" + encodeURIComponent(id));
  const parent = id + "~1";
  const isFirst = log[log.length - 1].id === id;

  const groups = new Map();
  changes.forEach((c) => {
    const key = groupKey(c.path);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  });

  const diffBox = el("div");
  const rows = [];
  for (const [key, files] of groups) {
    const allDeleted = files.every((f) => f.status === "D");
    rows.push(el("tr", { class: "group-head" },
      el("td", { colspan: "2" }, key),
      el("td", { class: "actions" },
        el("button", { class: "small", title: "Restore this folder as it was in this snapshot", onclick: () => restore(allDeleted ? parent : id, key, key) }, allDeleted ? "Restore deleted" : "Restore state"),
        " ",
        isFirst ? null : el("button", { class: "small", title: "Undo the changes of this snapshot for this folder", onclick: () => restore(parent, key, key) }, "Restore before"))));
    files.forEach((f) => {
      const isText = /\.(xml|mml|toml)$/i.test(f.path);
      rows.push(el("tr", { class: "file-row" },
        el("td", { class: "status-" + f.status }, f.status),
        el("td", {}, f.path),
        el("td", { class: "actions" },
          isText && f.status !== "A" ? el("button", { class: "small", onclick: async () => {
            if (diffBox.dataset.path === f.path) {
              delete diffBox.dataset.path;
              diffBox.replaceChildren();
              return;
            }
            diffBox.dataset.path = f.path;
            const result = await api("GET", `/api/backup/diff?id=${encodeURIComponent(id)}&path=${encodeURIComponent(f.path)}`);
            diffBox.replaceChildren(el("div", { class: "label" }, "Diff " + f.path), el("pre", {}, result.diff || "(no textual difference)"));
            diffBox.scrollIntoView({ behavior: "smooth" });
          } }, "Diff") : null,
          " ",
          el("button", { class: "small", onclick: () => restore(f.status === "D" ? parent : id, f.path, f.path) }, f.status === "D" ? "Restore deleted" : "Restore"))));
    });
  }

  detail.replaceChildren(
    el("h2", {}, commit.subject),
    el("div", { class: "muted" }, fmtDate(commit.date), "  ·  ", id),
    el("div", { style: "margin:12px 0" },
      el("button", { onclick: () => restore(id, "", "Snapshot") }, "Restore everything to this snapshot")),
    el("div", { class: "label" }, `Changes (${changes.length} files)`),
    changes.length ? el("table", {}, el("tbody", {}, rows)) : el("p", { class: "muted" }, "Configuration only."),
    diffBox
  );
}

document.getElementById("bk-target-save").addEventListener("click", () => setBackupFolder(document.getElementById("bk-target").value.trim()));
document.getElementById("bk-target-browse").addEventListener("click", chooseBackupFolder);

document.getElementById("bk-snapshot").addEventListener("click", async () => {
  if (state.backupBusy) return;
  setBackupBusy(true);
  try {
    const result = await api("POST", "/api/backup/snapshot", { message: document.getElementById("bk-message").value });
    toast(result.commit ? result.commit.subject : "No changes since the last snapshot");
    document.getElementById("bk-message").value = "";
    await loadBackup();
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBackupBusy(false);
    await loadBackup();
  }
});

document.getElementById("bk-config-save").addEventListener("click", async () => {
  try {
    await api("PUT", "/api/backup/config", { text: document.getElementById("bk-config").value });
    toast("Configuration saved, it is part of the next snapshot");
  } catch (err) {
    toast(err.message, true);
  }
});

// ---------- card connection ----------

async function pollCard() {
  let present = false;
  try {
    present = (await api("GET", "/api/card/status")).present;
  } catch (_) { /* server unreachable */ }
  if (present) state.cardEjected = false;
  const indicator = document.getElementById("card-state");
  const text = present
    ? `Card connected${state.cardPath ? ": " + state.cardPath : ""}`
    : state.cardEjected
      ? "Card ejected, safe to remove. blackbook finds it again when you connect it."
      : "Card not connected: switch the blackbox to microSD mode";
  indicator.title = text;
  indicator.setAttribute("aria-label", text);
  indicator.className = "iconbtn cardicon " + (present ? "ok" : state.cardEjected ? "off" : "err");
  document.getElementById("eject-btn").disabled = !present;
  document.getElementById("b-plan").disabled = !present;
  if (present && state.cardPresent === false) {
    toast("Card connected again, patches and projects reloaded");
    await loadLibrary();
  }
  state.cardPresent = present;
  await refreshBackupIfVisible();
  await showCodeCommit();
}

document.getElementById("eject-btn").addEventListener("click", async (ev) => {
  const button = ev.currentTarget;
  button.disabled = true;
  try {
    await api("POST", "/api/card/eject");
    state.cardEjected = true;
    await pollCard();
    await showMessage("Card ejected", "You can now unplug the blackbox or leave microSD mode.\n\nWhen you connect the card again, blackbook finds it by itself.");
  } catch (err) {
    await showMessage("The card could not be ejected", err.message);
  } finally {
    button.disabled = !state.cardPresent;
  }
});

// Show the running code version and warn when the checkout moved on since the start
async function showCodeCommit() {
  let info;
  try {
    info = await api("GET", "/api/info");
  } catch (_) { return; }
  const box = document.getElementById("code-commit");
  const stale = info.current_commit && info.commit !== info.current_commit;
  // Installations from a ZIP have no git commit, they show the version instead
  const label = info.commit || (info.version ? `v${info.version}` : "");
  box.textContent = stale ? `${label} restart needed` : label;
  box.title = stale ? `blackbook was updated to ${info.current_commit}. Click to restart blackbook.` : "";
  box.className = stale ? "err clickable" : "muted";
  box.onclick = stale ? restartServer : null;
  const pid = document.getElementById("server-pid");
  pid.textContent = info.pid ? `PID ${info.pid}` : "";
  pid.title = info.pid ? "Process id of the blackbook server" : "";
  document.title = label ? `blackbook ${label}` : "blackbook";
  state.suggestedBackup = info.suggested_backup;
  renderBackupBanner(info);
}

// Ask once per session to set up the backup while the card is connected and nothing is backed up
function renderBackupBanner(info) {
  const banner = document.getElementById("backup-banner");
  const show = state.cardPresent && !info.backup_ready && !info.first_start && !state.backupBannerDismissed && !state.backupBusy;
  banner.hidden = !show;
  const key = show ? `${info.git_available}|${info.suggested_backup}` : "";
  if (!show || banner.dataset.key === key) return;
  banner.dataset.key = key;
  const later = el("button", { class: "small", onclick: () => { state.backupBannerDismissed = true; banner.hidden = true; } }, "Later");
  if (info.git_available) {
    fill(banner,
      el("span", { class: "grow" }, el("strong", {}, "Your card is not backed up yet. "), "blackbook can keep snapshots of the card in ", el("code", {}, info.suggested_backup), "."),
      el("button", { class: "primary small", onclick: () => setBackupFolder(info.suggested_backup) }, "Set up backup"),
      el("button", { class: "small", onclick: chooseBackupFolder }, "Other folder"),
      later);
  } else {
    fill(banner,
      el("span", { class: "grow" }, el("strong", {}, "Backups are off: git is not installed. "), "Everything else works."),
      el("button", { class: "small", onclick: () => openHelp("git") }, "How to install git"),
      later);
  }
}

// ---------- backup setup ----------

const FIRST_SNAPSHOT_HINT = "The first snapshot copies the whole card into the backup folder. With a full card this can take several minutes. Keep blackbook open until it is done.";

// Disable every backup action while a snapshot runs, also across view changes
function setBackupBusy(busy, label = "Running ...") {
  state.backupBusy = busy;
  const snap = document.getElementById("bk-snapshot");
  snap.disabled = busy || !state.backupInitialized || !state.cardPresent;
  snap.textContent = busy ? label : "Snapshot now";
  ["bk-target-save", "bk-target-browse"].forEach((id) => { document.getElementById(id).disabled = busy; });
  document.querySelectorAll("#backup-banner button").forEach((b) => { b.disabled = busy; });
  document.getElementById("bk-busy").hidden = !busy;
}

async function setBackupFolder(path) {
  if (state.backupBusy) return;
  setBackupBusy(true, "First snapshot ...");
  toast(FIRST_SNAPSHOT_HINT);
  try {
    const status = await api("PUT", "/api/backup/target", { path });
    toast(status.commits ? `Backup set up in ${status.target}, first snapshot taken` : `Backup folder set: ${status.target}`);
    document.getElementById("backup-banner").hidden = true;
  } catch (err) {
    toast(err.message, true);
  } finally {
    setBackupBusy(false);
    await loadBackup();
  }
}

async function chooseBackupFolder() {
  const current = document.getElementById("bk-target").value.trim();
  const path = await pickFolder(current || state.suggestedBackup);
  if (path) await setBackupFolder(path);
}

// ---------- folder picker ----------

function pickFolder(start) {
  const dialog = document.getElementById("folder-dialog");
  let current = null;

  async function open(path) {
    let data;
    try {
      data = await api("GET", "/api/fs/dirs?path=" + encodeURIComponent(path || ""));
    } catch (_) {
      // A suggested folder that does not exist yet: start at its parent
      if (path) return open(path.replace(/[\\/][^\\/]*[\\/]?$/, "") || "");
      throw _;
    }
    current = data.path;
    document.getElementById("folder-path").textContent = data.path;
    document.getElementById("folder-warn").textContent = data.is_card
      ? "This folder is on the blackbox card. Choose a folder on your computer."
      : data.is_program ? "This folder is inside the blackbook folder. An update or a new installation could delete it. Choose a folder outside." : "";
    document.getElementById("folder-choose").disabled = data.is_card || data.is_program;
    fill(document.getElementById("folder-roots"), data.roots.map((r, i) => el("button", { class: "small", title: r, onclick: () => open(r) }, i === 0 ? "Home" : r)));
    const rows = [];
    if (data.parent) rows.push(el("div", { class: "row dir", onclick: () => open(data.parent) }, el("span", { class: "name" }, "..")));
    data.dirs.forEach((d) => rows.push(el("div", { class: "row dir", onclick: () => open(data.path.replace(/[\\/]$/, "") + (data.path.includes("\\") ? "\\" : "/") + d) }, el("span", { class: "name" }, d))));
    if (!data.dirs.length) rows.push(el("p", { class: "muted", style: "padding:10px" }, "No subfolders."));
    fill(document.getElementById("folder-list"), rows);
  }

  return new Promise((resolve) => {
    const done = (value) => {
      dialog.close();
      ["folder-choose", "folder-cancel", "folder-create"].forEach((id) => { document.getElementById(id).onclick = null; });
      resolve(value);
    };
    document.getElementById("folder-choose").onclick = () => done(current);
    document.getElementById("folder-cancel").onclick = () => done(null);
    dialog.oncancel = () => done(null);
    document.getElementById("folder-create").onclick = async () => {
      const input = document.getElementById("folder-new");
      try {
        const created = await api("POST", "/api/fs/mkdir", { path: current, name: input.value });
        input.value = "";
        await open(created.path);
      } catch (err) {
        toast(err.message, true);
      }
    };
    document.getElementById("folder-new").onkeydown = (ev) => { if (ev.key === "Enter") document.getElementById("folder-create").click(); };
    open(start).then(() => dialog.showModal(), (err) => { toast(err.message, true); resolve(null); });
  });
}

// ---------- first start ----------

function showWelcome(info) {
  const dialog = document.getElementById("welcome-dialog");
  const finish = async () => {
    dialog.close();
    try { await api("POST", "/api/welcome/done"); } catch (_) { /* shown again next time */ }
  };
  const content = [
    el("h2", {}, "Welcome to blackbook"),
    el("p", {}, el("strong", {}, "This is a very early version. "), "Please try it and tell me what you need: ",
      el("a", { href: "https://github.com/nightanvil/blackbook/issues", target: "_blank", rel: "noopener noreferrer" }, "ideas and feedback"), "."),
    el("p", {}, "Card: ", state.cardPresent ? el("span", { class: "ok" }, "connected") : "not connected yet, switch the blackbox to microSD mode."),
  ];
  const actions = [];
  if (info.backup_ready) {
    content.push(el("p", {}, "The backup is already set up."));
    actions.push(el("button", { class: "primary", onclick: finish }, "Start"));
  } else if (info.git_available) {
    content.push(
      el("h3", {}, "Your card is not backed up yet"),
      el("p", {}, "blackbook can keep snapshots of the card in ", el("code", {}, info.suggested_backup),
        ". With snapshots you can go back to any earlier state of the card, for a single file or everything."),
      el("p", { class: "hint" }, FIRST_SNAPSHOT_HINT));
    actions.push(
      el("button", { onclick: finish }, "Later"),
      el("button", { onclick: async () => { await finish(); await chooseBackupFolder(); } }, "Choose folder"),
      el("button", { class: "primary", onclick: async () => { await finish(); await setBackupFolder(info.suggested_backup); } }, "Set up backup"));
  } else {
    content.push(
      el("h3", {}, "Backups are off"),
      el("p", {}, "git is not installed, so blackbook cannot make backups of the card. Everything else works. Copy the whole card to your computer yourself before you save anything."));
    actions.push(
      el("button", { onclick: async () => { await finish(); openHelp("git"); } }, "How to install git"),
      el("button", { class: "primary", onclick: finish }, "Start"));
  }
  fill(document.getElementById("welcome-content"), content);
  fill(document.getElementById("welcome-actions"), actions);
  dialog.oncancel = finish;
  dialog.showModal();
}

// ---------- updates ----------

async function checkForUpdate() {
  let info;
  try { info = await api("GET", "/api/update/check"); } catch (_) { return; }
  if (!info.available) return;
  const banner = document.getElementById("update-banner");
  if (info.mode === "git") {
    fill(banner,
      el("span", { class: "grow" }, el("strong", {}, `${info.behind} new commit${info.behind === 1 ? "" : "s"} available. `), "Development checkout: update with git pull, then start blackbook again."),
      el("button", { class: "small", onclick: () => { banner.hidden = true; } }, "Later"));
  } else {
    fill(banner,
      el("span", { class: "grow" }, el("strong", {}, `blackbook ${info.latest} is available. `), `You have ${info.current}.`),
      info.url ? el("a", { href: info.url, target: "_blank", rel: "noopener noreferrer" }, "What is new") : null,
      el("button", { class: "primary small", onclick: installUpdate }, "Update now"),
      el("button", { class: "small", onclick: () => { banner.hidden = true; } }, "Later"));
  }
  banner.hidden = false;
}

async function installUpdate(ev) {
  const button = ev.currentTarget;
  button.disabled = true;
  button.textContent = "Updating ...";
  try {
    const result = await api("POST", "/api/update/apply");
    fill(document.getElementById("update-content"),
      el("h2", {}, `Updated to ${result.version}`),
      el("p", {}, "blackbook stops now. Start it again the same way as before (start.sh, start.bat or start.command). The next start may take a moment to set up the new version."),
      el("p", { class: "hint" }, "Your settings, your backup and your card are not changed by the update."));
    document.getElementById("update-ok").onclick = async () => {
      try { await api("POST", "/api/shutdown"); } catch (_) { /* already stopping */ }
      document.getElementById("update-dialog").close();
      showStopped("Start it again to use the new version, then reload this page.");
    };
    document.getElementById("update-dialog").showModal();
  } catch (err) {
    toast(err.message, true);
    button.disabled = false;
    button.textContent = "Update now";
  }
}

// ---------- server control ----------

function showStopped(text) {
  clearInterval(state.pollTimer);
  document.body.replaceChildren(el("div", { class: "stopped" }, el("h2", {}, "blackbook has stopped"), el("p", {}, text)));
}

async function shutdownServer() {
  const ok = await confirmDialog("Stop blackbook",
    "blackbook stops and this page no longer works.\n\nTo use blackbook again, start it the same way as before (start.sh, start.bat or start.command).",
    "Stop");
  if (!ok) return;
  try { await api("POST", "/api/shutdown"); } catch (_) { /* already stopping */ }
  showStopped("Start it again the same way as before, then reload this page.");
}

async function restartServer() {
  const ok = await confirmDialog("Restart blackbook",
    "blackbook stops and starts again. This takes a few seconds, the page reloads by itself.",
    "Restart");
  if (!ok) return;
  let before;
  try {
    before = (await api("GET", "/api/info")).started_at;
    await api("POST", "/api/restart");
  } catch (err) {
    toast(err.message, true);
    return;
  }
  clearInterval(state.pollTimer);
  document.body.replaceChildren(el("div", { class: "stopped" }, el("h2", {}, "Restarting blackbook ..."), el("p", { class: "muted" }, "The page reloads when blackbook is back.")));
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 1000));
    try {
      if ((await api("GET", "/api/info")).started_at !== before) { location.reload(); return; }
    } catch (_) { /* not up yet */ }
  }
  showStopped("blackbook did not come back. Start it again the same way as before, then reload this page.");
}

document.getElementById("restart-btn").addEventListener("click", restartServer);
document.getElementById("shutdown-btn").addEventListener("click", shutdownServer);

// Reload the backup view when snapshots or events changed while it is shown
async function refreshBackupIfVisible() {
  if (!document.getElementById("view-backup").classList.contains("active")) return;
  try {
    const status = await api("GET", "/api/backup/status");
    const events = status.events || [];
    if (`${status.commits}|${events.length ? events[0].time + events[0].text : ""}` !== state.backupStamp) await loadBackup();
  } catch (_) { /* server unreachable */ }
}

// ---------- start ----------

async function start() {
  setupAudioControls();
  const info = await api("GET", "/api/info");
  state.padParams = await api("GET", "/api/padparams");
  state.roots = info.roots;
  state.cardPath = info.card;
  await loadLibrary();
  loadProjects();
  tagChips(document.getElementById("b-tags"), state.buildTags);
  renderPads();
  renderZones();
  await pollCard();
  state.pollTimer = setInterval(pollCard, 4000);
  const fresh = await api("GET", "/api/info");
  if (fresh.first_start) showWelcome(fresh);
  checkForUpdate();
  await loadBrowser();
}

start().catch((err) => toast(err.message, true));
