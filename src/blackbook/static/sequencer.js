// Project view: tracks, MIDI channels, sequences and the step editor for one-shot tracks

const TICKS = 960;
const OFFSET_UNIT = 10;
// Length of one step in quarter notes, by notesteplen index
const STEP_QUARTERS = [32, 16, 8, 4, 2, 4 / 3, 1, 2 / 3, 0.5, 1 / 3, 0.25, 1 / 6, 0.125, 1 / 12, 0.0625, 1 / 24];

const proj = {
  name: null,
  data: null,
  track: null, // index into data.tracks
  slot: 0,
  selected: null, // the selected event object
  dirty: false,
  tempo: 120,
  swing: 50,
};

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

async function showProject(name) {
  if (proj.dirty && proj.name !== name) {
    const ok = await confirmDialog("Discard changes?", `The changes to the sequences of ${proj.name} are not saved yet.`, "Discard");
    if (!ok) return;
  }
  const keepEdits = proj.dirty && proj.name === name && proj.data;
  if (!keepEdits) seqPlayer.stop();
  state.selectedProject = name;
  document.querySelectorAll("#proj-list tbody tr").forEach((row) =>
    row.classList.toggle("selected", row.firstChild.firstChild.textContent === name));
  const detail = document.getElementById("proj-detail");
  if (!detail) return;
  if (keepEdits) {
    fill(detail, el("div", { id: "proj-head" }), el("div", { id: "proj-tracks" }), el("div", { id: "proj-seq" }), el("div", { id: "proj-samples" }));
    renderProjectHead();
    renderTracks();
    renderSequencer();
    renderProjectSamples(name, document.getElementById("proj-samples"));
    return;
  }
  detail.replaceChildren(el("p", { class: "muted" }, "Loading..."));
  let data;
  try {
    data = await api("GET", "/api/project/detail?name=" + encodeURIComponent(name));
  } catch (err) {
    detail.replaceChildren(el("p", { class: "err" }, err.message));
    return;
  }
  const keepTrack = proj.name === name ? proj.track : null;
  Object.assign(proj, { name, data, dirty: false, selected: null, tempo: data.tempo, swing: data.swing });
  const firstOneShot = data.tracks.findIndex((t) => t.type === "samtrack");
  proj.track = keepTrack != null && keepTrack < data.tracks.length ? keepTrack : Math.max(0, firstOneShot);
  const firstSeq = currentTrack() && currentTrack().sequences[0];
  if (keepTrack == null) proj.slot = firstSeq ? firstSeq.slot : 0;
  fill(detail,
    el("div", { id: "proj-head" }),
    el("div", { id: "proj-tracks" }),
    el("div", { id: "proj-seq" }),
    el("div", { id: "proj-samples" }));
  renderProjectHead();
  renderTracks();
  renderSequencer();
  renderProjectSamples(name, document.getElementById("proj-samples"));
}

function renderProjectHead() {
  const head = document.getElementById("proj-head");
  if (!head || !proj.data) return;
  fill(head,
    el("div", { class: "proj-title" },
      el("h2", {}, proj.name),
      proj.data.autosave ? el("span", { class: "badge", title: "The device keeps an autosave copy of this project. blackbook changes only the project you selected here." }, "has autosave") : null,
      el("span", { class: "grow" }),
      proj.dirty ? el("span", { class: "warn" }, "unsaved changes") : null,
      el("button", { disabled: !proj.dirty, onclick: () => showProjectReload() }, "Discard"),
      el("button", { class: "primary", disabled: !proj.dirty, onclick: saveProject }, "Save to card")));
}

async function showProjectReload() {
  proj.dirty = false;
  await showProject(proj.name);
}

function renderTracks() {
  const wrap = document.getElementById("proj-tracks");
  if (!wrap) return;
  const tracks = proj.data.tracks;
  if (!tracks.length) { fill(wrap, el("p", { class: "muted" }, "This project has no tracks.")); return; }
  fill(wrap,
    el("div", { class: "label" }, "Tracks"),
    el("table", { class: "tracks" },
      el("thead", {}, el("tr", {}, ["Track", "Type", "Name", "MIDI in", "MIDI out", "Sequences"].map((h) => el("th", {}, h)))),
      el("tbody", {}, tracks.map((t, i) => {
        const inSel = midiOptions(t.midiinchan);
        const outSel = midiOptions(t.midioutchan);
        inSel.addEventListener("click", (ev) => ev.stopPropagation());
        outSel.addEventListener("click", (ev) => ev.stopPropagation());
        inSel.addEventListener("change", () => { t.midiinchan = Number(inSel.value); t.midiChanged = true; markDirty(); });
        outSel.addEventListener("change", () => { t.midioutchan = Number(outSel.value); t.midiChanged = true; markDirty(); });
        const used = t.sequences.filter((s) => s.events.length).length;
        return el("tr", { class: "clickable" + (i === proj.track ? " selected" : ""), onclick: () => selectTrack(i) },
          el("td", {}, String(i + 1)),
          el("td", {}, TRACK_LABELS[t.type] || t.type),
          el("td", {}, t.name),
          el("td", { title: "MIDI channel the track listens on" }, inSel),
          el("td", { title: "MIDI channel the track sends on" }, outSel),
          el("td", { class: "muted" }, `${used} of 8 with notes`));
      }))));
}

function selectTrack(i) {
  if (proj.track === i) return;
  seqPlayer.stop();
  proj.track = i;
  proj.selected = null;
  const first = currentTrack().sequences.find((s) => s.events.length) || currentTrack().sequences[0];
  proj.slot = first ? first.slot : 0;
  renderTracks();
  renderSequencer();
}

function selectSlot(slot) {
  proj.slot = slot;
  proj.selected = null;
  if (seqPlayer.playing) seqPlayer.restart();
  renderSequencer();
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
  fill(wrap,
    el("div", { class: "label" }, `Sequences of track ${proj.track + 1}${track.name ? ": " + track.name : ""}`),
    tabs,
    settings,
    body,
    editable ? eventInspector(track, seq) : null,
    seq && seq.automation ? el("p", { class: "muted hint-small" }, "This sequence has automation. blackbook keeps it as it is; it is not shown or played here.") : null);
}

function seqSettings(seq, editable) {
  const s = seq || { name: `Seq ${proj.slot + 1}`, steplen: 10, stepcount: 16, quant: 1, snap: true };
  const change = (fn) => () => { const target = currentSeq(true); fn(target); markDirty(target); renderSequencer(); };
  const lenSel = el("select", { disabled: !editable }, proj.data.step_lengths.map((l, i) => el("option", { value: i }, l)));
  lenSel.value = String(s.steplen);
  lenSel.addEventListener("change", change((t) => { t.steplen = Number(lenSel.value); }));
  const quantSel = el("select", { disabled: !editable }, proj.data.quant_sizes.map((l, i) => el("option", { value: i }, l)));
  quantSel.value = String(s.quant);
  quantSel.addEventListener("change", change((t) => { t.quant = Number(quantSel.value); }));
  const open = s.stepcount === 0;
  const countIn = el("input", { type: "number", min: 1, max: 256, value: open ? 16 : s.stepcount, disabled: !editable || open, class: "num" });
  countIn.addEventListener("change", change((t) => { t.stepcount = Math.max(1, Math.min(256, Math.round(Number(countIn.value) || 16))); }));
  const openBox = el("input", { type: "checkbox", checked: open, disabled: !editable });
  openBox.addEventListener("change", change((t) => { t.stepcount = openBox.checked ? 0 : gridSteps(t); }));
  const snapBox = el("input", { type: "checkbox", checked: s.snap, disabled: !editable });
  snapBox.addEventListener("change", change((t) => { t.snap = snapBox.checked; }));
  const nameIn = el("input", { type: "text", value: s.name, maxlength: 16, disabled: !editable, class: "seq-name" });
  nameIn.addEventListener("change", change((t) => { t.name = nameIn.value.trim() || `Seq ${t.slot + 1}`; }));
  const tempoIn = el("input", { type: "number", min: 20, max: 300, value: proj.tempo, class: "num", title: "Tempo for playback here; the project tempo on the device is not changed" });
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
  const padBySlot = new Map(track.pads.map((p) => [p.slot, p]));
  // Step numbers
  grid.append(el("div", { class: "seq-corner", style: "grid-row:1;grid-column:1" }));
  for (let s = 0; s < steps; s++) {
    grid.append(el("div", { class: "seq-num" + (s % 4 === 0 ? " beat" : ""), style: `grid-row:1;grid-column:${s + 2}` }, s % 4 === 0 ? String(s + 1) : ""));
  }
  PAD_SLOTS.forEach((slot, r) => {
    const row = r + 2;
    const pad = padBySlot.get(slot);
    const label = pad ? pad.filename.split("\\").pop().replace(/\.wav$/i, "") : "empty";
    grid.append(el("div", { class: "seq-pad" + (pad ? "" : " empty"), style: `grid-row:${row};grid-column:1`, title: pad ? pad.filename : "No sample on this pad",
      onclick: () => { if (pad) seqPlayer.hit(pad, 100); } },
      el("b", {}, String(padNumber(slot))), " ", label));
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
      const node = el("div", {
        class: "seq-ev" + (ev === proj.selected ? " selected" : "") + (ev.prob < 100 ? " prob" : ""),
        style: `grid-row:${r + 2};grid-column:${ev.step + 2} / span ${span};opacity:${0.35 + 0.65 * vel / 127}`,
        title: `Pad ${padNumber(ev.chan)}, step ${ev.step + 1}, velocity ${vel}, prob ${ev.prob < 100 ? ev.prob + "%" : "always"}, offset ${ev.offset}, length ${ev.lencount || ev.lentks + " ticks"}`,
        onclick: (e) => { e.stopPropagation(); clickEvent(ev); },
      });
      if (ev.offset) node.append(el("span", { class: "off" }, ev.offset > 0 ? "›" : "‹"));
      grid.append(node);
    }
  }
  const head = el("div", { class: "seq-playhead", id: "seq-playhead", style: `grid-row:1 / span ${PAD_SLOTS.length + 1};grid-column:2`, hidden: true });
  grid.append(head);
  return el("div", { class: "seq-grid-wrap" }, grid,
    el("p", { class: "muted hint-small" }, "Click an empty cell to add a note, click a note to select it, click the selected note again to remove it. Click a pad name to hear the pad. Playback follows step length, velocity, probability, offset and the pad's level, pitch, pan, start and length; swing and choke groups are approximated, effects are heard on the device only."));
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
  const pad = currentTrack().pads.find((p) => p.slot === chan);
  if (pad && !seqPlayer.playing) seqPlayer.hit(pad, ev.velocity);
  renderSequencer();
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
  const num = (label, value, min, max, title, apply) => {
    const input = el("input", { type: "number", min, max, value, class: "num", title });
    input.addEventListener("change", () => {
      const v = Math.max(min, Math.min(max, Math.round(Number(input.value))));
      if (Number.isFinite(v)) { apply(v); update(); }
    });
    return el("label", { title }, label + " ", input);
  };
  return el("div", { class: "seq-inspector" },
    el("b", {}, `Pad ${padNumber(ev.chan)}, step ${ev.step + 1}`),
    num("Velocity", ev.velocity ?? 100, 1, 127, "How hard the pad plays, 1 to 127", (v) => { ev.velocity = v; }),
    num("Prob %", ev.prob, 1, 100, "Probability that the note plays each time, 100 is Always", (v) => { ev.prob = v; }),
    num("Offset", ev.offset, -47, 47, "Nudges the note earlier or later, -47 to +47 (10 ticks each, a step has 960)", (v) => {
      ev.offset = ev.step === 0 ? Math.max(0, v) : v;
      ev.strtks = Math.max(0, ev.step * TICKS + ev.offset * OFFSET_UNIT);
    }),
    ev.lencount === 0
      ? el("span", { class: "muted", title: "Recorded with Snap off" }, `Length ${ev.lentks} ticks`)
      : num("Length", ev.lencount, 1, 256, "Length in steps", (v) => { ev.lencount = v; ev.lentks = v * TICKS; }),
    el("button", { class: "small", onclick: () => { seq.events.splice(seq.events.indexOf(ev), 1); proj.selected = null; update(); } }, "Remove"));
}

async function saveProject() {
  const changes = proj.data.tracks.map((t) => {
    const sequences = t.sequences.filter((s) => s.changed && !(s.isNew && !s.events.length));
    if (!sequences.length && !t.midiChanged) return null;
    const change = { index: t.index, sequences };
    if (t.midiChanged) Object.assign(change, { midiinchan: t.midiinchan, midioutchan: t.midioutchan });
    return change;
  }).filter(Boolean);
  if (!changes.length) { proj.dirty = false; renderProjectHead(); return; }
  const lines = [`blackbook writes the changes into Projects/${proj.name}/project.xml. Everything else in the project stays as it is.`];
  if (proj.data.autosave) lines.push("", `The autosave copy (${proj.name} - autosave) is not changed. If the device loads the autosave, the changes are not in it.`);
  lines.push("", "If the project is open on the blackbox, load it again there after the card is back in the device. A snapshot is taken before and after, if the backup is set up.");
  if (!(await confirmDialog("Save sequences to the card?", lines.join("\n"), "Save"))) return;
  try {
    await api("PUT", "/api/project/sequences", { name: proj.name, tracks: changes });
    toast("Saved to the card");
    proj.dirty = false;
    await showProject(proj.name);
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
  next: 0, // context time where the next loop starts
  loops: [], // scheduled loops: { start, steps, stepDur }
  queue: [], // events of the loop being scheduled, sorted by time
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
      await Promise.all(track.pads.filter((p) => p.source).map((p) => this.buffer(p)));
    } catch (err) { toast(err.message, true); return; }
    this.playing = true;
    this.restart();
    this.timer = setInterval(() => this.schedule(), 25);
    const draw = () => { this.drawHead(); if (this.playing) this.raf = requestAnimationFrame(draw); };
    this.raf = requestAnimationFrame(draw);
    renderSequencer();
  },

  restart() {
    this.next = audioOut.context().currentTime + 0.08;
    this.loops = [];
    this.queue = [];
  },

  schedule() {
    const seq = currentSeq();
    const track = currentTrack();
    if (!this.playing || !track) return;
    const ctx = audioOut.context();
    const horizon = ctx.currentTime + 0.15;
    const stepDur = seq ? this.stepSeconds(seq) : this.stepSeconds({ steplen: 10 });
    const steps = seq ? gridSteps(seq) : 16;
    const loopDur = steps * stepDur;
    const swingDelay = (proj.swing / 50 - 1) * stepDur;
    const pads = new Map(track.pads.filter((p) => p.source).map((p) => [p.slot, p]));
    while (true) {
      if (!this.queue.length) {
        const loopStart = this.next;
        if (loopStart > horizon) break;
        this.next = loopStart + loopDur;
        this.loops.push({ start: loopStart, steps, stepDur });
        if (this.loops.length > 4) this.loops.shift();
        this.queue = (seq ? seq.events : [])
          .filter((e) => e.step < steps)
          .map((e) => ({ e, t: loopStart + (e.strtks / TICKS) * stepDur + (e.step % 2 ? swingDelay : 0) }))
          .sort((a, b) => a.t - b.t);
        if (!this.queue.length) continue;
      }
      if (this.queue[0].t > horizon) break;
      const { e, t } = this.queue.shift();
      const pad = pads.get(e.chan);
      if (!pad || Math.random() * 100 >= e.prob) continue;
      const key = `${pad.source}|${pad.start}|${pad.length}|${pad.params.reverse ? 1 : 0}`;
      const buffer = this.buffers.get(key);
      if (buffer) this.voice(pad, buffer, e.velocity ?? 100, Math.max(t, ctx.currentTime));
    }
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
    this.queue = [];
    const head = document.getElementById("seq-playhead");
    if (head) head.hidden = true;
  },
};
