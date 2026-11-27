// Project view: tracks, MIDI channels, sequences and the step editor for one-shot tracks

const TICKS = 960;
const OFFSET_UNIT = 10;
// Length of one step in quarter notes, by notesteplen index
const STEP_QUARTERS = [32, 16, 8, 4, 2, 4 / 3, 1, 2 / 3, 0.5, 1 / 3, 0.25, 1 / 6, 0.125, 1 / 12, 0.0625, 1 / 24];

const CELL_PITCH = 28; // grid column width plus gap in pixels
const ROW_PITCH = 24;
// Grid for moving notes, in ticks
const NUDGE = [
  { label: "Step", ticks: TICKS },
  { label: "1/2 step", ticks: TICKS / 2 },
  { label: "1/4 step", ticks: TICKS / 4 },
  { label: "1/8 step", ticks: TICKS / 8 },
  { label: "Free (10 ticks)", ticks: OFFSET_UNIT },
];

const proj = {
  nudge: 0, // index into NUDGE
  euclid: null, // open Euclid panel: { chan, hits, length, rotate, velocity, before }
  name: null,
  data: null,
  track: null, // index into data.tracks
  slot: 0,
  selected: null, // the selected event object
  dirty: false,
  tempo: 120,
  swing: 50,
};

// View settings per project in this browser, such as the grid for moving notes
function projectPrefs(name) {
  try {
    return JSON.parse(localStorage.getItem("blackbook-projects") || "{}")[name] || {};
  } catch (_) {
    return {};
  }
}

function saveProjectPrefs(name, values) {
  try {
    const all = JSON.parse(localStorage.getItem("blackbook-projects") || "{}");
    all[name] = { ...(all[name] || {}), ...values };
    localStorage.setItem("blackbook-projects", JSON.stringify(all));
  } catch (_) {
    // Storage blocked or full: the setting lasts until the page is reloaded
  }
}

// Pad slots in the order pad 1 to pad 16
const PAD_SLOTS = [8, 9, 10, 11, 12, 13, 14, 15, 0, 1, 2, 3, 4, 5, 6, 7];

function midiOptions(value) {
  const options = [el("option", { value: 0 }, "None")];
  for (let c = 1; c <= 16; c++) options.push(el("option", { value: c }, String(c)));
  const select = el("select", {}, options);
  select.value = String(value);
  return select;
}

function currentTrack() { return proj.data ? proj.data.tracks[proj.track] : null; }

function currentSeq(create = false) {
  const track = currentTrack();
  if (!track) return null;
  let seq = track.sequences.find((s) => s.slot === proj.slot);
  if (!seq && create) {
    seq = { slot: proj.slot, name: `Seq ${proj.slot + 1}`, steplen: 10, stepcount: 16, quant: 1, snap: true, automation: false, events: [], isNew: true };
    track.sequences.push(seq);
    track.sequences.sort((a, b) => a.slot - b.slot);
  }
  return seq;
}

function markDirty(seq) {
  if (seq) seq.changed = true;
  proj.dirty = true;
  renderProjectHead();
}

// ---------- pads of a one-shot track, edited with the pad grid and pad editor of the builder ----------

function padKey(pads) {
  return JSON.stringify(Object.entries(pads || {})
    .map(([slot, p]) => {
      // The pad editor fills in defaults for parameters a pad does not have; they are no change
      const params = { ...defaultPadParams(), ...(p.params || {}) };
      const sorted = Object.fromEntries(Object.keys(params).sort().map((k) => [k, params[k]]));
      return [Number(slot), p.source, p.loop_mode || 0, sorted, p.start ?? null, p.length ?? null];
    })
    .sort((a, b) => a[0] - b[0]));
}

function padsChanged(track) { return !!track.padState && padKey(track.padState) !== track.padOrig; }

function isDirty() { return proj.dirty || (proj.data ? proj.data.tracks.some(padsChanged) : false); }

// Pads as the sequencer plays them: the edited ones while the Pads tab has changes
function trackPads(track) {
  if (!track.padState) return track.pads;
  return Object.entries(track.padState).map(([slot, p]) => ({
    slot: Number(slot),
    source: p.source,
    filename: p.filename || (p.source ? p.source.split("/").pop() : ""),
    start: p.start ?? 0,
    length: p.length ?? 0,
    params: p.params || {},
  }));
}

function openPads(container) {
  const track = currentTrack();
  const browser = document.querySelector("#view-build aside.browser");
  const oneshot = document.getElementById("b-oneshot");
  if (!proj.padsOpen) {
    proj.padsOpen = {
      pads: state.pads, selectedPad: state.selectedPad, oneshotHidden: oneshot.hidden,
      browserHome: [browser.parentNode, browser.nextSibling], oneshotHome: [oneshot.parentNode, oneshot.nextSibling],
    };
  }
  if (!track.padState) {
    track.padState = Object.fromEntries(track.pads.map((p) => [p.slot, structuredClone(p)]));
    track.padOrig = padKey(track.padState);
  }
  state.pads = track.padState;
  if (state.selectedPad == null || !state.pads[state.selectedPad]) state.selectedPad = PAD_SLOTS.find((s) => state.pads[s]) ?? 8;
  oneshot.hidden = false;
  fill(container,
    el("div", { class: "proj-pads" }, browser, el("div", { class: "proj-pads-main" }, oneshot)),
    el("p", { class: "muted hint-small" }, "These are the pads of the track in this project. Drag WAVs from the browser onto a pad, change the sound in the pad editor. Save to card writes them into the project: samples on the card are used where they are, samples from the inbox or a library are copied into the project folder. The patch on the card is not changed."));
  renderPads();
}

function closePads() {
  const home = proj.padsOpen;
  if (!home) return;
  const browser = document.querySelector("aside.browser");
  const oneshot = document.getElementById("b-oneshot");
  home.browserHome[0].insertBefore(browser, home.browserHome[1]);
  home.oneshotHome[0].insertBefore(oneshot, home.oneshotHome[1]);
  oneshot.hidden = home.oneshotHidden;
  state.pads = home.pads;
  state.selectedPad = home.selectedPad;
  proj.padsOpen = null;
  renderPads();
}

// The builder redraws its pads after every change; the project head then shows unsaved changes
const builderRenderPads = renderPads;
renderPads = function renderPadsAndProject(...args) {
  builderRenderPads(...args);
  if (proj.padsOpen) renderProjectHead();
};

document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => {
  if (button.dataset.view !== "projects" && proj.padsOpen) closePads();
}));

// ---------- project detail ----------

const PROJECT_TABS = [
  { id: "seq", label: "Sequences" },
  { id: "pads", label: "Pads", oneShotOnly: true },
  { id: "samples", label: "Samples" },
];

function renderProjectTabs() {
  const wrap = document.getElementById("proj-tabs");
  const track = currentTrack();
  if (!wrap) return;
  const oneShot = track && track.type === "samtrack";
  if (proj.tab === "pads" && !oneShot) proj.tab = "seq";
  wrap.style.setProperty("--track", track ? TRACK_COLORS[track.position] : "var(--accent)");
  fill(wrap, PROJECT_TABS.filter((t) => !t.oneShotOnly || oneShot).map((t) =>
    el("button", { class: proj.tab === t.id ? "active" : "", onclick: () => selectProjectTab(t.id) },
      t.label, t.id === "pads" && track && padsChanged(track) ? el("span", { class: "dot", title: "unsaved changes" }) : null)));
}

function selectProjectTab(id) {
  proj.tab = id;
  renderProjectBody();
}

function renderProjectBody() {
  const body = document.getElementById("proj-body");
  if (!body) return;
  if (proj.tab !== "pads" && proj.padsOpen) closePads();
  renderProjectTabs();
  if (proj.tab === "pads") {
    openPads(body);
  } else if (proj.tab === "samples") {
    const box = el("div", {});
    fill(body, box);
    renderProjectSamples(proj.name, box);
  } else {
    fill(body, el("div", { id: "proj-seq" }));
    renderSequencer();
  }
}

function renderProjectDetail() {
  const detail = document.getElementById("proj-detail");
  fill(detail,
    el("div", { id: "proj-head" }),
    el("div", { id: "proj-tracks" }),
    el("div", { id: "proj-tabs", class: "proj-tabs" }),
    el("div", { id: "proj-body" }));
  renderProjectHead();
  renderTracks();
  renderProjectBody();
}

async function showProject(name) {
  if (isDirty() && proj.name !== name) {
    const ok = await confirmDialog("Discard changes?", `The changes to ${proj.name} are not saved yet.`, "Discard");
    if (!ok) return;
  }
  const keepEdits = isDirty() && proj.name === name && proj.data;
  if (!keepEdits) seqPlayer.stop();
  if (proj.padsOpen) closePads();
  state.selectedProject = name;
  document.querySelectorAll("#proj-list .pcard").forEach((row) => row.classList.toggle("selected", row.dataset.name === name));
  const detail = document.getElementById("proj-detail");
  if (!detail) return;
  if (keepEdits) { renderProjectDetail(); return; }
  detail.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  let data;
  try {
    data = await api("GET", "/api/project/detail?name=" + encodeURIComponent(name));
  } catch (err) {
    detail.replaceChildren(el("p", { class: "err" }, err.message));
    return;
  }
  const sameProject = proj.name === name;
  const keepTrack = sameProject ? proj.track : null;
  Object.assign(proj, { name, data, dirty: false, selected: null, euclid: null, tempo: data.tempo, swing: data.swing });
  if (!sameProject || !proj.tab) proj.tab = "seq";
  const prefs = projectPrefs(name);
  proj.nudge = Number.isInteger(prefs.nudge) && NUDGE[prefs.nudge] ? prefs.nudge : 0;
  const firstOneShot = data.tracks.findIndex((t) => t.type === "samtrack");
  proj.track = keepTrack != null && keepTrack < data.tracks.length ? keepTrack : Math.max(0, firstOneShot);
  const firstSeq = currentTrack() && currentTrack().sequences[0];
  if (keepTrack == null) proj.slot = firstSeq ? firstSeq.slot : 0;
  renderProjectDetail();
}

function renderProjectHead() {
  const head = document.getElementById("proj-head");
  if (!head || !proj.data) return;
  const dirty = isDirty();
  const summary = (state.projects || []).find((p) => p.name === proj.name);
  const stat = (label, value, cls, title) => el("span", { class: "proj-stat " + (cls || ""), title: title || "" }, el("b", {}, String(value)), " ", label);
  fill(head,
    el("div", { class: "proj-title" },
      el("h2", {}, proj.name),
      proj.data.autosave ? el("span", { class: "badge", title: "The device keeps an autosave copy of this project. blackbook changes only the project you selected here." }, "has autosave") : null,
      el("span", { class: "grow" }),
      dirty ? el("span", { class: "warn" }, "unsaved changes") : null,
      el("button", { disabled: !dirty, onclick: () => showProjectReload() }, "Discard"),
      el("button", { class: "primary", disabled: !dirty, onclick: saveProject }, "Save to card")),
    summary ? el("div", { class: "proj-stats" },
      stat("WAVs in folder", summary.wav_files),
      stat("references", summary.references),
      stat("missing", summary.missing.length, summary.missing.length ? "err" : "muted", summary.missing.join("\n")),
      stat("unused in folder", summary.unused.length, summary.unused.length ? "warn" : "muted", summary.unused.join("\n"))) : null);
  renderProjectTabs();
}

async function showProjectReload() {
  proj.dirty = false;
  if (proj.padsOpen) closePads();
  if (proj.data) proj.data.tracks.forEach((t) => { t.padState = null; });
  await showProject(proj.name);
}

// Track colors of the device by position, from the Tracks screen in the manual
const TRACK_COLORS = ["#00c0f0", "#f06000", "#00705a", "#f000f0"];
const TRACK_INK = ["#001018", "#1a0a00", "#ffffff", "#1a001a"];

// Track type icons in the style of the device, drawn for blackbook
const TRACK_ICONS = {
  samtrack: '<svg viewBox="0 0 24 24"><g fill="currentColor"><rect x="3" y="7" width="4" height="4"/><rect x="8" y="7" width="4" height="4"/><rect x="13" y="7" width="4" height="4"/><rect x="18" y="7" width="4" height="4"/><rect x="3" y="12" width="4" height="4"/><rect x="8" y="12" width="4" height="4"/><rect x="13" y="12" width="4" height="4"/><rect x="18" y="12" width="4" height="4"/></g></svg>',
  looptrack: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7h7a5 5 0 0 1 0 10H9a5 5 0 0 1-3.6-8.5"/><path d="M10 4L7.5 7 10 10"/></svg>',
  multisamtrack: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" fill="none" stroke="currentColor" stroke-width="1.6"/><g fill="currentColor"><rect x="6" y="4" width="2.4" height="9"/><rect x="10.8" y="4" width="2.4" height="9"/><rect x="15.6" y="4" width="2.4" height="9"/></g><g stroke="currentColor" stroke-width="1.2"><path d="M9.6 13v7M14.4 13v7"/></g></svg>',
  slicertrack: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M8.5 7.8L20 17M8.5 16.2L20 7"/></svg>',
  granslicertrack: '<svg viewBox="0 0 24 24"><g fill="currentColor"><rect x="3" y="9" width="3" height="3"/><rect x="7" y="9" width="3" height="3"/><rect x="11" y="9" width="3" height="3"/><rect x="5" y="13" width="3" height="3"/><rect x="9" y="13" width="3" height="3"/><rect x="3" y="17" width="2" height="2"/><rect x="7" y="17" width="2" height="2"/><rect x="11" y="17" width="2" height="2"/><rect x="16" y="3" width="2.4" height="10"/></g><path d="M17.2 13v4" stroke="currentColor" stroke-width="1.4"/></svg>',
  exttrack: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="8"/><g fill="currentColor" stroke="none"><circle cx="8" cy="11" r="1.2"/><circle cx="16" cy="11" r="1.2"/><circle cx="12" cy="8" r="1.2"/><circle cx="9.5" cy="14.5" r="1.2"/><circle cx="14.5" cy="14.5" r="1.2"/></g></svg>',
};

function trackIcon(type) {
  const node = el("span", { class: "bb-icon", title: TRACK_LABELS[type] || type });
  node.innerHTML = TRACK_ICONS[type] || TRACK_ICONS.exttrack;
  return node;
}

function renderTracks() {
  const wrap = document.getElementById("proj-tracks");
  if (!wrap) return;
  const tracks = proj.data.tracks;
  const byPos = new Map(tracks.map((t, i) => [t.position, i]));
  const cards = [0, 1, 2, 3].map((pos) => {
    const i = byPos.get(pos);
    if (i == null) return el("div", { class: "bb-track empty", title: "Empty track" });
    const t = tracks[i];
    const inSel = midiOptions(t.midiinchan);
    const outSel = midiOptions(t.midioutchan);
    for (const sel of [inSel, outSel]) sel.addEventListener("click", (ev) => ev.stopPropagation());
    inSel.addEventListener("change", () => { t.midiinchan = Number(inSel.value); t.midiChanged = true; markDirty(); });
    outSel.addEventListener("change", () => { t.midioutchan = Number(outSel.value); t.midiChanged = true; markDirty(); });
    const used = t.sequences.filter((s) => s.events.length).length;
    return el("div", {
      class: "bb-track" + (i === proj.track ? " selected" : ""),
      style: `--track:${TRACK_COLORS[pos]};--track-ink:${TRACK_INK[pos]}`,
      title: `Track ${pos + 1}: ${TRACK_LABELS[t.type] || t.type}`,
      onclick: () => selectTrack(i),
    },
      el("div", { class: "bb-head" }, t.name || `Track ${pos + 1}`),
      trackIcon(t.type),
      el("div", { class: "bb-config" },
        el("div", { class: "bb-config-title" }, "Config"),
        el("label", { title: "MIDI channel the track listens on (MIDI In Chan)" }, "MIDI In", inSel),
        el("label", { title: "MIDI channel the track sends on (MIDI OutCh)" }, "MIDI Out", outSel)),
      el("div", { class: "bb-foot" }, `Samples: ${t.samples}`, el("span", {}, `Seq: ${used}/8`)));
  });
  fill(wrap,
    el("div", { class: "bb-screen" },
      el("div", { class: "bb-tracks" }, cards),
      el("div", { class: "bb-toolbar" },
        el("span", {}, proj.name),
        el("span", { class: "sep" }),
        metaIcon("metronome", `${proj.data.tempo} BPM`, "", "Tempo of the project"),
        el("span", { title: "Swing of the project, 50 is straight" }, `Swing ${proj.data.swing}%`),
        el("span", { class: "grow" }),
        el("span", { class: "muted" }, `${tracks.length} of 4 tracks`))));
}

function selectTrack(i) {
  if (proj.track === i) return;
  seqPlayer.stop();
  if (proj.padsOpen) closePads();
  proj.euclid = null;
  proj.track = i;
  proj.selected = null;
  const first = currentTrack().sequences.find((s) => s.events.length) || currentTrack().sequences[0];
  proj.slot = first ? first.slot : 0;
  renderTracks();
  renderProjectBody();
}

function selectSlot(slot) {
  if (proj.euclid) closeEuclid(true);
  proj.slot = slot;
  proj.selected = null;
  if (seqPlayer.playing) seqPlayer.restart();
  renderSequencer();
}

// Offset range in ticks: the Offset knob reaches +-47 (10 ticks each); notes recorded with Snap off sit up to half a step away
function offsetLimits(seq) {
  return seq && !seq.snap ? [-TICKS / 2, TICKS / 2 - OFFSET_UNIT] : [-47 * OFFSET_UNIT, 47 * OFFSET_UNIT];
}

function placeEvent(ev, absTicks, steps, seq) {
  const [low, high] = offsetLimits(seq);
  const abs = Math.max(0, Math.min(absTicks, (steps - 1) * TICKS + high));
  let step = Math.max(0, Math.min(steps - 1, Math.round(abs / TICKS)));
  let off = abs - step * TICKS;
  if (off > high) { step = Math.min(steps - 1, step + 1); off = abs - step * TICKS; }
  off = Math.max(step === 0 ? 0 : low, Math.min(high, off));
  ev.step = step;
  ev.strtks = step * TICKS + off;
  ev.offset = Math.round(off / OFFSET_UNIT);
}

// Number of steps the grid shows
function gridSteps(seq) {
  if (seq.stepcount > 0) return seq.stepcount;
  const end = seq.events.reduce((m, e) => Math.max(m, e.step + Math.max(1, e.lencount)), 0);
  return Math.max(16, Math.ceil(end / 16) * 16);
}

function renderSequencer() {
  const wrap = document.getElementById("proj-seq");
  const track = currentTrack();
  if (!wrap || !track) { if (wrap) wrap.replaceChildren(); return; }
  const seq = currentSeq();
  const tabs = el("div", { class: "seq-tabs" }, [0, 1, 2, 3, 4, 5, 6, 7].map((slot) => {
    const s = track.sequences.find((x) => x.slot === slot);
    return el("button", {
      class: "small" + (slot === proj.slot ? " active" : "") + (s && s.events.length ? "" : " empty"),
      title: s ? `${s.name}: ${s.events.length} notes` : "Empty slot, add notes to create the sequence",
      onclick: () => selectSlot(slot),
    }, s && s.name ? s.name : `Seq ${slot + 1}`);
  }));
  const editable = track.type === "samtrack";
  const settings = seqSettings(seq, editable);
  const body = editable ? stepGrid(track, seq) : el("p", { class: "muted" },
    seq ? `${seq.events.length} notes. Editing sequences of ${TRACK_LABELS[track.type] || track.type} tracks is not supported yet, only one-shot tracks.` : "Empty slot.");
  wrap.style.setProperty("--track", TRACK_COLORS[track.position] || "var(--accent)");
  wrap.style.setProperty("--track-ink", TRACK_INK[track.position] || "var(--accent-ink)");
  fill(wrap,
    el("div", { class: "label" }, `Sequences of track ${track.position + 1}${track.name ? ": " + track.name : ""}`),
    tabs,
    settings,
    body,
    editable ? euclidPanel() : null,
    editable && !proj.euclid ? eventInspector(track, seq) : null,
    seq && seq.automation ? el("p", { class: "muted hint-small" }, "This sequence has automation. blackbook keeps it as it is; it is not shown or played here.") : null);
}

function seqSettings(seq, editable) {
  const s = seq || { name: `Seq ${proj.slot + 1}`, steplen: 10, stepcount: 16, quant: 1, snap: true };
  const change = (fn) => () => { const target = currentSeq(true); fn(target); markDirty(target); renderSequencer(); };
  const lenSel = el("select", { disabled: !editable }, proj.data.step_lengths.map((l, i) => el("option", { value: i }, l)));
  lenSel.value = String(s.steplen);
  Object.assign(lenSel.dataset, { default: "10", resetKey: `seq:${proj.track}:${proj.slot}:steplen` });
  lenSel.addEventListener("change", change((t) => { t.steplen = Number(lenSel.value); }));
  const quantSel = el("select", { disabled: !editable }, proj.data.quant_sizes.map((l, i) => el("option", { value: i }, l)));
  quantSel.value = String(s.quant);
  Object.assign(quantSel.dataset, { default: "1", resetKey: `seq:${proj.track}:${proj.slot}:quant` });
  quantSel.addEventListener("change", change((t) => { t.quant = Number(quantSel.value); }));
  const open = s.stepcount === 0;
  const countIn = el("input", { type: "number", min: 1, max: 256, value: open ? 16 : s.stepcount, disabled: !editable || open, class: "num" });
  Object.assign(countIn.dataset, { default: "16", resetKey: `seq:${proj.track}:${proj.slot}:stepcount` });
  countIn.addEventListener("change", change((t) => { t.stepcount = Math.max(1, Math.min(256, Math.round(Number(countIn.value) || 16))); }));
  const openBox = el("input", { type: "checkbox", checked: open, disabled: !editable });
  openBox.addEventListener("change", change((t) => { t.stepcount = openBox.checked ? 0 : gridSteps(t); }));
  const snapBox = el("input", { type: "checkbox", checked: s.snap, disabled: !editable });
  snapBox.addEventListener("change", change((t) => { t.snap = snapBox.checked; }));
  const nameIn = el("input", { type: "text", value: s.name, maxlength: 16, disabled: !editable, class: "seq-name" });
  nameIn.addEventListener("change", change((t) => { t.name = nameIn.value.trim() || `Seq ${t.slot + 1}`; }));
  const tempoIn = el("input", { type: "number", min: 20, max: 300, value: proj.tempo, class: "num", title: "Tempo for playback here; the project tempo on the device is not changed" });
  Object.assign(tempoIn.dataset, { default: String(proj.data.tempo), resetKey: "seq:tempo" });
  tempoIn.addEventListener("change", () => { proj.tempo = Math.max(20, Math.min(300, Number(tempoIn.value) || 120)); });
  const playBtn = el("button", { class: "primary small seq-play" + (seqPlayer.playing ? " playing" : ""), disabled: !editable, onclick: () => seqPlayer.toggle() },
    seqPlayer.playing ? "■ Stop" : "▶ Play");
  return el("div", { class: "seq-settings" },
    playBtn,
    el("label", { title: "Tempo for playback here; the project tempo on the device is not changed" }, "BPM ", tempoIn),
    el("label", {}, "Name ", nameIn),
    el("label", {}, "Step Len ", lenSel),
    el("label", {}, "Steps ", countIn),
    el("label", { class: "check", title: "Open: the sequence grows while recording on the device" }, openBox, "Open"),
    el("label", {}, "Quant ", quantSel),
    el("label", { class: "check", title: "Snap events to the step grid" }, snapBox, "Snap"));
}

function stepGrid(track, seq) {
  const steps = seq ? gridSteps(seq) : 16;
  const grid = el("div", { class: "seq-grid", style: `grid-template-columns: 150px repeat(${steps}, 26px)` });
  const padBySlot = new Map(trackPads(track).filter((p) => p.source || p.filename).map((p) => [p.slot, p]));
  // Step numbers
  grid.append(el("div", { class: "seq-corner", style: "grid-row:1;grid-column:1" }));
  for (let s = 0; s < steps; s++) {
    grid.append(el("div", { class: "seq-num" + (s % 4 === 0 ? " beat" : ""), style: `grid-row:1;grid-column:${s + 2}` }, s % 4 === 0 ? String(s + 1) : ""));
  }
  PAD_SLOTS.forEach((slot, r) => {
    const row = r + 2;
    const pad = padBySlot.get(slot);
    const label = pad ? (pad.filename || "").split("\\").pop().replace(/\.wav$/i, "") : "empty";
    grid.append(el("div", { class: "seq-pad" + (pad ? "" : " empty") + (proj.euclid && proj.euclid.chan === slot ? " euclid" : ""), style: `grid-row:${row};grid-column:1`, title: pad ? pad.filename : "No sample on this pad",
      onclick: () => { if (pad) seqPlayer.hit(pad, 100); } },
      el("button", { class: "seq-eu", title: "Euclidean rhythm for this pad", onclick: (e) => { e.stopPropagation(); openEuclid(slot); } }, "E"),
      el("b", {}, String(padNumber(slot))), " ", el("span", { class: "seq-pad-name" }, label)));
    for (let s = 0; s < steps; s++) {
      grid.append(el("div", {
        class: "seq-cell" + (Math.floor(s / 4) % 2 ? " odd" : ""),
        style: `grid-row:${row};grid-column:${s + 2}`,
        onclick: () => addEvent(slot, s),
      }));
    }
  });
  if (seq) {
    for (const ev of seq.events) {
      const r = PAD_SLOTS.indexOf(ev.chan);
      if (r < 0 || ev.step >= steps) continue;
      const span = Math.max(1, Math.min(ev.lencount || 1, steps - ev.step));
      const vel = ev.velocity ?? 100;
      const offTicks = ev.strtks - ev.step * TICKS;
      const width = ev.lencount === 0 ? Math.max(6, (ev.lentks / TICKS) * CELL_PITCH - 2) : null;
      const node = el("div", {
        class: "seq-ev" + (ev === proj.selected ? " selected" : "") + (ev.prob < 100 ? " prob" : ""),
        style: `grid-row:${r + 2};grid-column:${ev.step + 2} / span ${span};opacity:${0.35 + 0.65 * vel / 127};transform:translateX(${(offTicks / TICKS) * CELL_PITCH}px)` + (width ? `;width:${width}px` : ""),
        title: `Pad ${padNumber(ev.chan)}, step ${ev.step + 1}, velocity ${vel}, prob ${ev.prob < 100 ? ev.prob + "%" : "always"}, offset ${offTicks} ticks, length ${ev.lencount || ev.lentks + " ticks"}. Drag to move.`,
      });
      node.addEventListener("pointerdown", (e) => dragEvent(e, ev, node, steps, seq));
      grid.append(node);
    }
  }
  const head = el("div", { class: "seq-playhead", id: "seq-playhead", style: `grid-row:1 / span ${PAD_SLOTS.length + 1};grid-column:2`, hidden: true });
  grid.append(head);
  const nudgeSel = el("select", { title: "Grid for dragging notes sideways" }, NUDGE.map((n, i) => el("option", { value: i }, n.label)));
  nudgeSel.value = String(proj.nudge);
  Object.assign(nudgeSel.dataset, { default: "0", resetKey: "seq:nudge" });
  nudgeSel.addEventListener("change", () => {
    proj.nudge = Number(nudgeSel.value);
    saveProjectPrefs(proj.name, { nudge: proj.nudge });
  });
  const [low, high] = offsetLimits(seq);
  return el("div", {},
    el("div", { class: "seq-toolbar" },
      el("label", {}, "Move notes by ", nudgeSel),
      el("span", { class: "muted hint-small" }, `Off the step grid a note can sit ${low} to +${high} ticks from its step (a step has ${TICKS}).` + (seq && seq.snap ? " Turn Snap off for up to half a step, as with notes recorded on the device." : ""))),
    el("div", { class: "seq-grid-wrap" }, grid),
    el("p", { class: "muted hint-small" }, "Click an empty cell to add a note, click a note to select it, click the selected note again to remove it. Drag a note sideways to move it on the chosen grid, up or down to move it to another pad. E next to a pad opens the Euclidean generator. Click a pad name to hear the pad. Playback follows step length, velocity, probability, offset and the pad's level, pitch, pan, start and length; swing and choke groups are approximated, effects are heard on the device only."));
}

function addEvent(chan, step) {
  const seq = currentSeq(true);
  const last = proj.selected;
  const ev = {
    step, chan, offset: 0, strtks: step * TICKS, pitch: 0, lencount: 1, lentks: TICKS,
    velocity: last ? (last.velocity ?? 100) : 100, prob: 100, type: "note", extra: {},
  };
  seq.events.push(ev);
  proj.selected = ev;
  markDirty(seq);
  const pad = trackPads(currentTrack()).find((p) => p.slot === chan);
  if (pad && !seqPlayer.playing) seqPlayer.hit(pad, ev.velocity);
  renderSequencer();
}

function dragEvent(down, ev, node, steps, seq) {
  if (down.button !== 0) return;
  down.stopPropagation();
  const startTicks = ev.strtks;
  const startRow = PAD_SLOTS.indexOf(ev.chan);
  let moved = false;
  const move = (e) => {
    const dx = e.clientX - down.clientX;
    const dy = e.clientY - down.clientY;
    if (!moved && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    moved = true;
    const grid = NUDGE[proj.nudge].ticks;
    const delta = Math.round(((dx / CELL_PITCH) * TICKS) / grid) * grid;
    placeEvent(ev, startTicks + delta, steps, seq);
    const row = Math.max(0, Math.min(PAD_SLOTS.length - 1, startRow + Math.round(dy / ROW_PITCH)));
    ev.chan = PAD_SLOTS[row];
    const span = Math.max(1, Math.min(ev.lencount || 1, steps - ev.step));
    node.style.gridRow = String(row + 2);
    node.style.gridColumn = `${ev.step + 2} / span ${span}`;
    node.style.transform = `translateX(${((ev.strtks - ev.step * TICKS) / TICKS) * CELL_PITCH}px)`;
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    if (!moved) { clickEvent(ev); return; }
    proj.selected = ev;
    markDirty(seq);
    renderSequencer();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

// Euclidean rhythm: hits spread as evenly as possible over length steps, shifted by rotate
function euclidPattern(hits, length, rotate) {
  const pattern = [];
  for (let i = 0; i < length; i++) {
    const j = (((i - rotate) % length) + length) % length;
    pattern.push(hits > 0 && (j * hits) % length < hits);
  }
  return pattern;
}

// Last Euclid settings per track, sequence and pad, so every pad keeps its own
const euclidMemory = new Map();

function openEuclid(chan) {
  // Another pad's open panel stays as it is; its notes only changed if a value was touched
  if (proj.euclid) {
    if (proj.euclid.chan === chan) { closeEuclid(true); return; }
    proj.euclid = null;
  }
  const seq = currentSeq(true);
  const existing = seq.events.filter((e) => e.chan === chan);
  const steps = gridSteps(seq);
  const key = `${proj.name}:${proj.track}:${proj.slot}:${chan}`;
  const remembered = euclidMemory.get(key);
  proj.euclid = {
    key,
    chan,
    hits: remembered ? remembered.hits : 4,
    length: remembered ? Math.min(remembered.length, steps) : Math.min(16, steps),
    rotate: remembered ? remembered.rotate : 0,
    velocity: remembered ? remembered.velocity : (existing[0] ? (existing[0].velocity ?? 100) : 100),
    touched: false,
    before: existing.map((e) => ({ ...e })),
  };
  renderSequencer();
}

function applyEuclid() {
  const eu = proj.euclid;
  eu.touched = true;
  euclidMemory.set(eu.key, { hits: eu.hits, length: eu.length, rotate: eu.rotate, velocity: eu.velocity });
  const seq = currentSeq(true);
  const steps = gridSteps(seq);
  seq.events = seq.events.filter((e) => e.chan !== eu.chan);
  const pattern = euclidPattern(eu.hits, eu.length, eu.rotate);
  for (let s = 0; s < steps; s++) {
    if (!pattern[s % eu.length]) continue;
    seq.events.push({ step: s, chan: eu.chan, offset: 0, strtks: s * TICKS, pitch: 0, lencount: 1, lentks: TICKS, velocity: eu.velocity, prob: 100, type: "note", extra: {} });
  }
  proj.selected = null;
  markDirty(seq);
  renderSequencer();
}

function closeEuclid(keep) {
  const eu = proj.euclid;
  if (!keep && eu) {
    const seq = currentSeq(true);
    seq.events = seq.events.filter((e) => e.chan !== eu.chan).concat(eu.before);
  }
  proj.euclid = null;
  renderSequencer();
}

// Common patterns as starting points: hits, length, rotation
const EUCLID_PRESETS = [
  { label: "4/4", hits: 4, length: 16, rotate: 0, title: "Four on the floor: every beat" },
  { label: "Offbeat", hits: 4, length: 16, rotate: 2, title: "Between the beats, like an open hi-hat" },
  { label: "Backbeat", hits: 2, length: 16, rotate: 4, title: "Beats 2 and 4, like a snare" },
  { label: "8ths", hits: 8, length: 16, rotate: 0, title: "Every eighth note" },
  { label: "16ths", hits: 16, length: 16, rotate: 0, title: "Every step" },
  { label: "Tresillo", hits: 3, length: 8, rotate: 0, title: "3 in 8: x..x..x." },
  { label: "Cinquillo", hits: 5, length: 8, rotate: 0, title: "5 in 8: x.xx.xx." },
  { label: "Bossa", hits: 5, length: 16, rotate: 0, title: "5 in 16" },
  { label: "7 in 16", hits: 7, length: 16, rotate: 0, title: "7 in 16, a busy syncopated line" },
  { label: "Clear", hits: 0, length: 16, rotate: 0, title: "No notes on this pad" },
];

function euclidPanel() {
  const eu = proj.euclid;
  if (!eu) return null;
  const seq = currentSeq(true);
  const steps = gridSteps(seq);
  const defaults = { hits: 4, length: Math.min(16, steps), rotate: 0, velocity: 100 };
  const field = (label, key, min, max, title) => {
    const input = el("input", { type: "number", min, max, value: eu[key], class: "num", title });
    Object.assign(input.dataset, { default: String(defaults[key]), resetKey: `euclid:${key}` });
    const apply = () => {
      const v = Math.max(min, Math.min(max, Math.round(Number(input.value))));
      if (Number.isFinite(v)) { eu[key] = v; if (eu.hits > eu.length) eu.hits = eu.length; applyEuclid(); }
    };
    input.addEventListener("change", apply);
    return el("label", { title }, label + " ", input);
  };
  const pattern = euclidPattern(eu.hits, eu.length, eu.rotate);
  const presets = el("div", { class: "eu-presets" }, EUCLID_PRESETS.map((p) => {
    const length = Math.min(p.length, steps);
    const active = eu.touched && eu.hits === Math.min(p.hits, length) && eu.length === length && eu.rotate === p.rotate % length;
    return el("button", {
      class: "small" + (active ? " active" : ""),
      title: p.title,
      onclick: () => { Object.assign(eu, { hits: Math.min(p.hits, length), length, rotate: p.rotate % length }); applyEuclid(); },
    }, p.label);
  }));
  return el("div", { class: "seq-euclid" },
    el("b", {}, `Euclid for pad ${padNumber(eu.chan)}`),
    presets,
    field("Hits", "hits", 0, eu.length, "Number of notes in the pattern"),
    field("Length", "length", 1, Math.min(64, steps), "Steps of the pattern; it repeats over the whole sequence"),
    field("Rotate", "rotate", 0, eu.length - 1, "Shifts the pattern to the right"),
    field("Velocity", "velocity", 1, 127, "Velocity of the notes"),
    el("span", { class: "eu-preview" + (eu.touched ? "" : " pending"), title: eu.touched ? "Pattern" : "Preview, the pad's notes change as soon as you change a value" }, pattern.map((on) => el("i", { class: on ? "on" : "" }))),
    eu.touched ? null : el("button", { class: "small", onclick: applyEuclid, title: "Write this pattern into the pad's row" }, "Apply"),
    el("button", { class: "small", onclick: () => closeEuclid(false), title: "Restore the notes this pad had before" }, "Cancel"),
    el("button", { class: "small primary", onclick: () => closeEuclid(true) }, "Done"));
}

function clickEvent(ev) {
  const seq = currentSeq();
  if (proj.selected === ev) {
    seq.events.splice(seq.events.indexOf(ev), 1);
    proj.selected = null;
    markDirty(seq);
  } else {
    proj.selected = ev;
  }
  renderSequencer();
}

function eventInspector(track, seq) {
  const ev = proj.selected;
  if (!ev || !seq || !seq.events.includes(ev)) {
    return el("div", { class: "seq-inspector muted" }, "Select a note to change velocity, probability, offset and length.");
  }
  const update = () => { markDirty(seq); renderSequencer(); };
  const num = (label, value, min, max, title, apply, fallback) => {
    const input = el("input", { type: "number", min, max, value, class: "num", title });
    Object.assign(input.dataset, { default: String(fallback), resetKey: `note:${label}` });
    input.addEventListener("change", () => {
      const v = Math.max(min, Math.min(max, Math.round(Number(input.value))));
      if (Number.isFinite(v)) { apply(v); update(); }
    });
    return el("label", { title }, label + " ", input);
  };
  return el("div", { class: "seq-inspector" },
    el("b", {}, `Pad ${padNumber(ev.chan)}, step ${ev.step + 1}`),
    num("Velocity", ev.velocity ?? 100, 1, 127, "How hard the pad plays, 1 to 127", (v) => { ev.velocity = v; }, 100),
    num("Prob %", ev.prob, 1, 100, "Probability that the note plays each time, 100 is Always", (v) => { ev.prob = v; }, 100),
    num("Offset", ev.strtks - ev.step * TICKS, offsetLimits(seq)[0], offsetLimits(seq)[1], "Ticks before or after the step, a step has 960. The Offset knob of the device moves in steps of 10 up to +-470.", (v) => {
      placeEvent(ev, ev.step * TICKS + v, gridSteps(seq), seq);
    }, 0),
    ev.lencount === 0
      ? el("span", { class: "muted", title: "Recorded with Snap off" }, `Length ${ev.lentks} ticks`)
      : num("Length", ev.lencount, 1, 256, "Length in steps", (v) => { ev.lencount = v; ev.lentks = v * TICKS; }, 1),
    el("button", { class: "small", onclick: () => { seq.events.splice(seq.events.indexOf(ev), 1); proj.selected = null; update(); } }, "Remove"));
}

async function saveProject() {
  const changes = proj.data.tracks.map((t) => {
    const sequences = t.sequences.filter((s) => s.changed && !(s.isNew && !s.events.length));
    const pads = padsChanged(t);
    if (!sequences.length && !t.midiChanged && !pads) return null;
    const change = { index: t.index, sequences };
    if (t.midiChanged) Object.assign(change, { midiinchan: t.midiinchan, midioutchan: t.midioutchan });
    if (pads) {
      change.pads = Object.entries(t.padState).map(([slot, pad]) => ({
        slot: Number(slot), source: pad.source, loop_mode: pad.loop_mode || 0,
        params: pad.params || {}, start: pad.start ?? null, length: pad.length ?? null,
      }));
    }
    return change;
  }).filter(Boolean);
  if (!changes.length) { proj.dirty = false; renderProjectHead(); return; }
  const lines = [`blackbook writes the changes into Projects/${proj.name}/project.xml. Everything else in the project stays as it is.`];
  if (changes.some((c) => c.pads)) lines.push("", "Pads: samples on the card are used where they are, samples from the inbox or a library are copied into the project folder. The patches in Patches are not changed.");
  if (proj.data.autosave) lines.push("", `The autosave copy (${proj.name} - autosave) is not changed. If the device loads the autosave, the changes are not in it.`);
  lines.push("", "If the project is open on the blackbox, load it again there after the card is back in the device. A snapshot is taken before and after, if the backup is set up.");
  if (!(await confirmDialog("Save the project to the card?", lines.join("\n"), "Save"))) return;
  try {
    await api("PUT", "/api/project/sequences", { name: proj.name, tracks: changes });
    toast("Saved to the card");
    proj.dirty = false;
    if (proj.padsOpen) closePads();
    proj.data.tracks.forEach((t) => { t.padState = null; });
    await showProject(proj.name);
    loadProjects();
  } catch (err) {
    toast(err.message, true);
  }
}

// ---------- playback ----------

const seqPlayer = {
  playing: false,
  timer: 0,
  raf: 0,
  buffers: new Map(),
  loopStart: 0,
  until: 0,
  loopPushed: false,
  loops: [], // started loops for the playhead: { start, steps, stepDur }
  voices: [],

  async buffer(pad) {
    const key = `${pad.source}|${pad.start}|${pad.length}|${pad.params.reverse ? 1 : 0}`;
    if (this.buffers.has(key)) return this.buffers.get(key);
    const audio = await loadPcm(pad.source);
    const ctx = audioOut.context();
    const frames = audio.channels[0].length;
    const start = Math.min(pad.start || 0, frames - 1);
    const length = Math.max(1, Math.min(pad.length > 0 ? pad.length : frames - start, frames - start));
    const buffer = ctx.createBuffer(audio.channels.length, length, audio.rate);
    audio.channels.forEach((data, c) => {
      const part = data.slice(start, start + length);
      if (pad.params.reverse) part.reverse();
      buffer.copyToChannel(part, c);
    });
    this.buffers.set(key, buffer);
    return buffer;
  },

  voice(pad, buffer, velocity, when) {
    const ctx = audioOut.context();
    const p = pad.params || {};
    const node = ctx.createBufferSource();
    node.buffer = buffer;
    node.playbackRate.value = Math.pow(2, (p.pitch || 0) / 1000 / 12);
    const gain = ctx.createGain();
    gain.gain.value = Math.pow(10, (p.gaindb || 0) / 1000 / 20) * (velocity / 127);
    const pan = ctx.createStereoPanner();
    pan.pan.value = Math.max(-1, Math.min(1, (p.panpos || 0) / 1000));
    node.connect(gain).connect(pan).connect(audioOut.master);
    // A pad in a choke group cuts the other pads of its group
    const group = p.chokegrp || 0;
    if (group) {
      for (const v of this.voices) if (v.group === group && v.slot !== pad.slot) { try { v.node.stop(when); } catch (_) { /* ended */ } }
    }
    node.start(when);
    const entry = { node, group, slot: pad.slot };
    this.voices.push(entry);
    node.onended = () => { this.voices = this.voices.filter((v) => v !== entry); };
  },

  async hit(pad, velocity) {
    if (!pad.source) return;
    try { this.voice(pad, await this.buffer(pad), velocity, 0); } catch (err) { toast(err.message, true); }
  },

  stepSeconds(seq) { return (60 / proj.tempo) * STEP_QUARTERS[seq.steplen]; },

  async toggle() {
    if (this.playing) { this.stop(); renderSequencer(); return; }
    const track = currentTrack();
    if (!track || track.type !== "samtrack") return;
    stopAll();
    try {
      await Promise.all(trackPads(track).filter((p) => p.source).map((p) => this.buffer(p)));
    } catch (err) { toast(err.message, true); return; }
    this.playing = true;
    this.restart();
    this.timer = setInterval(() => this.schedule(), 25);
    const draw = () => { this.drawHead(); if (this.playing) this.raf = requestAnimationFrame(draw); };
    this.raf = requestAnimationFrame(draw);
    renderSequencer();
  },

  restart() {
    const start = audioOut.context().currentTime + 0.08;
    this.loopStart = start; // start of the loop being scheduled
    this.until = start; // everything before this time is scheduled
    this.loops = [];
    this.loopPushed = false;
  },

  // Schedules only the next fraction of a second from the current notes, so an edit ahead of the
  // playhead is heard in the same pass
  schedule() {
    const seq = currentSeq();
    const track = currentTrack();
    if (!this.playing || !track) return;
    const ctx = audioOut.context();
    const horizon = ctx.currentTime + 0.12;
    const stepDur = this.stepSeconds(seq || { steplen: 10 });
    const steps = seq ? gridSteps(seq) : 16;
    const loopDur = steps * stepDur;
    const swingDelay = (proj.swing / 50 - 1) * stepDur;
    const pads = new Map(trackPads(track).filter((p) => p.source).map((p) => [p.slot, p]));
    const events = (seq ? seq.events : []).filter((e) => e.step < steps);
    while (this.until < horizon) {
      if (!this.loopPushed) {
        this.loops.push({ start: this.loopStart, steps, stepDur });
        if (this.loops.length > 4) this.loops.shift();
        this.loopPushed = true;
      }
      const loopEnd = this.loopStart + loopDur;
      if (loopEnd > this.until) {
        const windowEnd = Math.min(horizon, loopEnd);
        for (const e of events) {
          const t = this.loopStart + (e.strtks / TICKS) * stepDur + (e.step % 2 ? swingDelay : 0);
          if (t < this.until || t >= windowEnd) continue;
          const pad = pads.get(e.chan);
          if (!pad || Math.random() * 100 >= e.prob) continue;
          const buffer = this.buffers.get(`${pad.source}|${pad.start}|${pad.length}|${pad.params.reverse ? 1 : 0}`);
          if (buffer) this.voice(pad, buffer, e.velocity ?? 100, Math.max(t, ctx.currentTime));
          else this.buffer(pad).catch(() => {}); // a pad changed while playing is loaded for the next pass
        }
        this.until = windowEnd;
      }
      if (this.until >= loopEnd) {
        this.loopStart = loopEnd;
        this.loopPushed = false;
      }
    }
    // The current loop follows changes of step length and step count for the playhead
    const current = this.loops[this.loops.length - 1];
    if (current) Object.assign(current, { steps, stepDur });
  },

  drawHead() {
    const head = document.getElementById("seq-playhead");
    if (!head) return;
    const now = audioOut.context().currentTime;
    const loop = [...this.loops].reverse().find((l) => l.start <= now);
    if (!loop) { head.hidden = true; return; }
    const step = Math.min(loop.steps - 1, Math.floor((now - loop.start) / loop.stepDur));
    head.hidden = false;
    head.style.gridColumn = String(step + 2);
  },

  stop() {
    this.playing = false;
    clearInterval(this.timer);
    cancelAnimationFrame(this.raf);
    for (const v of this.voices) { try { v.node.stop(); } catch (_) { /* ended */ } }
    this.voices = [];
    const head = document.getElementById("seq-playhead");
    if (head) head.hidden = true;
  },
};
