"use strict";

const state = {
  patches: [],
  tags: [],
  libTags: new Set(),
  selectedRef: null,
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

const player = document.getElementById("player");

function setPlaying(source) {
  state.playing = source;
  document.getElementById("stop-btn").hidden = !source;
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
document.getElementById("stop-btn").addEventListener("click", stop);
document.addEventListener("keydown", (ev) => {
  if (ev.key === "Escape" && state.playing) stop();
});

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
function noteName(n) { return NOTE_NAMES[n % 12] + (Math.floor(n / 12) - 1); }
// Pad 1 is bottom left (celldisppos 8) and counts to the right and upwards; the top row holds pads 9-16
function padNumber(slot) { return slot >= 8 ? slot - 7 : slot + 9; }
const PAD_SLOTS_BY_NUMBER = [8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7];
function baseName(source) { return source.split("/").pop(); }
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

// ---------- navigation ----------

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

function renderLibrary() {
  const search = document.getElementById("lib-search").value.toLowerCase();
  const source = document.getElementById("lib-source").value;
  const type = document.getElementById("lib-type").value;
  const list = document.getElementById("lib-list");

  const items = state.patches.filter((p) =>
    (!search || p.name.toLowerCase().includes(search)) &&
    (!source || p.root === source) &&
    (!type || p.type === type) &&
    [...state.libTags].every((t) => p.tags.includes(t))
  );

  list.replaceChildren(
    ...items.map((p) =>
      el("div", {
        class: "row" + (p.ref === state.selectedRef ? " selected" : ""),
        onclick: () => showPatch(p.ref),
      },
      el("span", { class: "name" }, p.name),
      p.is_user ? el("span", { class: "badge user" }, "user") : null,
      el("span", { class: "meta" }, p.type),
      el("span", { class: "meta" }, p.tags.length ? p.tags.join(", ") : "untagged"))
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
      el("td", {}, el("button", { class: "small", disabled: !s.source, onclick: () => play(s.source) }, "▶")),
      el("td", {}, s.filename, s.source ? null : el("span", { class: "err" }, " (missing)")),
      el("td", { class: "muted" }, isMulti
        ? `${s.root_name}  keys ${noteName(s.key_low)}-${noteName(s.key_high)}  vel ${s.vel_low}-${s.vel_high}`
        : s.slot != null ? "pad " + padNumber(s.slot) : "")
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
    el("div", { class: "muted" }, ref.replaceAll("\\", " / "), "  ·  ", data.track_type),
    editButtons,
    el("div", { class: "label" }, "Preview"),
    data.preview
      ? el("button", { onclick: () => play(data.preview) }, "▶ Play preview")
      : el("span", { class: "muted" }, "no preview.wav"),
    el("div", { class: "label" }, "Tags" + (isUser ? "" : " (factory, read only)")),
    tagBox,
    isUser ? el("div", { style: "margin-top:8px" }, saveButton) : null,
    el("div", { class: "label" }, `Samples (${rows.length})`),
    el("table", {}, el("tbody", {}, rows))
  );
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
        onclick: () => play(source),
        ondragstart: (ev) => {
          ev.dataTransfer.setData("application/x-blackbook", JSON.stringify([source]));
          ev.dataTransfer.effectAllowed = "copy";
        },
      }, el("span", { class: "name" }, e.name), el("span", { class: "meta" }, fmtSeconds(e.duration)));
    })
  );
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
      slot: Number(slot), source: pad.source, gain: pad.gain, pitch: pad.pitch, pan: pad.pan,
      choke_group: pad.choke_group, reverse: pad.reverse, loop_mode: pad.loop_mode,
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
    toast(`Written ${result.ref.replaceAll("\\", "/")} (${result.written.length} files)`);
    await loadLibrary();
    // Continue with the saved patch in edit mode
    await loadIntoBuilder(result.ref, "edit", false);
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
          if (pad) play(pad.source);
          renderPads();
        },
      }, el("span", { class: "num" }, padNumber(slot)), el("span", { class: "sample" }, pad ? (pad.source ? baseName(pad.source) : pad.filename + " (missing)") : ""));
      makeDropTarget(node, (sources) => {
        // Several dropped files fill the following pads in pad number order
        const start = PAD_SLOTS_BY_NUMBER.indexOf(slot);
        sources.forEach((source, i) => {
          const target = PAD_SLOTS_BY_NUMBER[start + i];
          if (target === undefined) return;
          const old = state.pads[target];
          // Replacing the sample keeps the pad settings
          state.pads[target] = old ? { ...old, source, filename: null } : { source, gain: 0, pitch: 0, pan: 0, choke_group: 0, reverse: false, loop_mode: 0 };
        });
        state.selectedPad = slot;
        renderPads();
      });
      return node;
    })
  );
  renderPadEditor();
}

function renderPadEditor() {
  const panel = document.getElementById("pad-editor");
  const slot = state.selectedPad;
  const pad = slot != null ? state.pads[slot] : null;
  if (!pad) {
    panel.replaceChildren(el("span", { class: "muted" }, slot == null ? "Select a pad." : `Pad ${padNumber(slot)} is empty. Drop a WAV onto it.`));
    return;
  }
  const field = (label, key, attrs) =>
    el("label", {}, label, el("input", { type: "number", value: pad[key], ...attrs, oninput: (ev) => { pad[key] = Number(ev.target.value); } }));
  const check = (label, key) =>
    el("label", { class: "check" }, el("input", { type: "checkbox", checked: pad[key], onchange: (ev) => { pad[key] = ev.target.checked; } }), label);

  if (!pad.source) {
    panel.replaceChildren(
      el("strong", {}, `Pad ${padNumber(slot)}: ${pad.filename}`),
      el("p", { class: "err" }, "The file of this pad is missing on the card. The pad stays unchanged unless you drop a new sample onto it or clear it."),
      el("button", { class: "small", onclick: () => { delete state.pads[slot]; renderPads(); } }, "Clear"));
    return;
  }

  panel.replaceChildren(
    el("div", { style: "display:flex;justify-content:space-between;margin-bottom:10px" },
      el("strong", {}, `Pad ${padNumber(slot)}: ${baseName(pad.source)}`),
      el("span", {},
        el("button", { class: "small", onclick: () => play(pad.source) }, "▶"), " ",
        el("button", { class: "small", onclick: () => { delete state.pads[slot]; renderPads(); } }, "Clear"))),
    el("div", { class: "pad-form" },
      field("Gain (dB)", "gain", { step: "0.1", min: "-60", max: "12" }),
      field("Pitch (semitones)", "pitch", { step: "0.01", min: "-24", max: "24" }),
      field("Pan (-1000..1000)", "pan", { step: "1", min: "-1000", max: "1000" }),
      field("Choke group (0 = off)", "choke_group", { step: "1", min: "0", max: "16" }),
      check("Reverse", "reverse"),
      field("Loop mode (0 = off)", "loop_mode", { step: "1", min: "0", max: "8" })),
    el("p", { class: "muted", style: "margin:10px 0 0;font-size:12px" }, "Gain and pitch are stored in thousandths. The unit mapping to the device display is unverified.")
  );
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
  if (state.mode === "new") {
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
      ? el("button", { class: "small", title: "Keep the original and save the changes under a new name", onclick: () => { state.mode = "copy"; document.getElementById("b-name").value += " copy"; renderMode(); } }, "Save as new patch instead")
      : null,
    el("button", { class: "small", title: "Discard the loaded patch and start with an empty builder", onclick: resetBuilder }, "Close"));
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
}

async function loadIntoBuilder(ref, mode, switchView = true) {
  let data;
  try {
    data = await api("GET", "/api/patch/load?ref=" + encodeURIComponent(ref));
  } catch (err) {
    toast(err.message, true);
    return;
  }
  state.mode = mode;
  state.baseRef = ref;
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
  if (switchView) document.querySelector('nav button[data-view="build"]').click();
}

// ---------- projects ----------

async function loadProjects() {
  const wrap = document.getElementById("proj-list");
  wrap.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  const projects = await api("GET", "/api/projects");
  wrap.replaceChildren(
    el("table", {},
      el("thead", {}, el("tr", {}, ["Project", "WAVs in folder", "References", "Missing", "Unused in folder"].map((h) => el("th", {}, h)))),
      el("tbody", {}, projects.map((p) =>
        el("tr", {},
          el("td", {}, p.name, p.is_autosave ? el("span", { class: "badge", style: "margin-left:6px" }, "autosave") : null),
          el("td", {}, p.wav_files),
          el("td", {}, p.references),
          el("td", { class: p.missing.length ? "err" : "muted", title: p.missing.join("\n") }, p.missing.length || "0"),
          el("td", { class: p.unused.length ? "warn" : "muted", title: p.unused.join("\n") }, p.unused.length ? p.unused.join(", ") : "0"))
      )))
  );
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

async function loadBackup() {
  const status = await api("GET", "/api/backup/status");
  const target = document.getElementById("bk-target");
  if (status.target && document.activeElement !== target) target.value = status.target;

  const lines = [];
  if (!status.target) lines.push("No backup folder set.");
  else if (!status.initialized) lines.push("Folder not initialized yet.");
  else {
    lines.push(`${status.commits} snapshots, repository ${fmtBytes(status.size_bytes)}`);
    if (status.last) lines.push("Last: " + fmtDate(status.last.date));
  }
  lines.push(status.card_present ? "Card connected" : "Card not connected");
  if (status.last_event) lines.push(status.last_event);
  document.getElementById("bk-status").replaceChildren(...lines.map((l) => el("div", {}, l)));
  document.getElementById("bk-snapshot").disabled = !status.initialized || !status.card_present;

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

async function restore(commit, path, label) {
  const scope = path ? `"${path}"` : "ALL backed up folders";
  if (!confirm(`Restore ${scope} from snapshot ${commit.slice(0, 10)}?\n\nThe current card state is saved as a snapshot first. Within the restored scope, files that do not exist in the snapshot are deleted from the card.`)) return;
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

document.getElementById("bk-target-save").addEventListener("click", async () => {
  try {
    await api("PUT", "/api/backup/target", { path: document.getElementById("bk-target").value.trim() });
    toast("Backup folder set");
    await loadBackup();
  } catch (err) {
    toast(err.message, true);
  }
});

document.getElementById("bk-snapshot").addEventListener("click", async (ev) => {
  const button = ev.target;
  button.disabled = true;
  button.textContent = "Running...";
  try {
    const result = await api("POST", "/api/backup/snapshot", { message: document.getElementById("bk-message").value });
    toast(result.commit ? result.commit.subject : "No changes since the last snapshot");
    document.getElementById("bk-message").value = "";
    await loadBackup();
  } catch (err) {
    toast(err.message, true);
  } finally {
    button.textContent = "Snapshot now";
    button.disabled = false;
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
  const indicator = document.getElementById("card-state");
  indicator.textContent = present ? "Card connected" : "Card not connected: switch the blackbox to microSD mode";
  indicator.className = present ? "ok" : "err";
  document.getElementById("b-plan").disabled = !present;
  if (present && state.cardPresent === false) {
    toast("Card connected again, library reloaded");
    await loadLibrary();
  }
  state.cardPresent = present;
}

// ---------- start ----------

async function start() {
  const info = await api("GET", "/api/info");
  state.roots = info.roots;
  document.getElementById("card-path").textContent = info.card;
  await loadLibrary();
  tagChips(document.getElementById("b-tags"), state.buildTags);
  renderPads();
  renderZones();
  await pollCard();
  setInterval(pollCard, 4000);
  await loadBrowser();
}

start().catch((err) => toast(err.message, true));
