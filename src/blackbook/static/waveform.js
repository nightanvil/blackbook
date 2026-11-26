"use strict";

// Waveform view with zoom, selection, a playback region and zero crossing snapping.
// Audio is held as one Float32Array per channel; positions are frames.

const WAVE_SNAP_RADIUS = 4000;

class WaveView {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.mode = options.mode || "select"; // select: free selection, region: drag start and end of the region
    this.snap = options.snap || (() => true);
    this.onChange = options.onChange || (() => {});
    this.channels = [];
    this.rate = 48000;
    this.frames = 0;
    this.viewStart = 0;
    this.viewEnd = 0;
    this.selection = null;
    this.region = null;
    this.playhead = null;
    this.drag = null;
    // Window listeners exist only while dragging, so discarded views leave nothing behind
    this.onMove = (ev) => this.mouseMove(ev);
    this.onUp = () => {
      window.removeEventListener("mousemove", this.onMove);
      window.removeEventListener("mouseup", this.onUp);
      this.mouseUp();
    };
    canvas.addEventListener("mousedown", (ev) => {
      this.mouseDown(ev);
      if (this.drag) {
        window.addEventListener("mousemove", this.onMove);
        window.addEventListener("mouseup", this.onUp);
      }
    });
    canvas.addEventListener("wheel", (ev) => this.wheel(ev), { passive: false });
    canvas.addEventListener("dblclick", () => { this.selection = null; this.draw(); this.onChange("selection"); });
    new ResizeObserver(() => this.draw()).observe(canvas);
  }

  setAudio(channels, rate) {
    this.channels = channels;
    this.rate = rate;
    this.frames = channels.length ? channels[0].length : 0;
    this.viewStart = 0;
    this.viewEnd = this.frames;
    if (this.selection && this.selection.end > this.frames) this.selection = null;
    this.draw();
  }

  // ---- coordinates ----

  width() { return this.canvas.clientWidth || 1; }

  frameAt(x) {
    const f = this.viewStart + (x / this.width()) * (this.viewEnd - this.viewStart);
    return Math.max(0, Math.min(this.frames, Math.round(f)));
  }

  xOf(frame) { return ((frame - this.viewStart) / Math.max(1, this.viewEnd - this.viewStart)) * this.width(); }

  snapFrame(frame) {
    if (!this.snap() || !this.frames || frame <= 0 || frame >= this.frames) return frame;
    return nearestZeroCrossing(this.channels, frame, WAVE_SNAP_RADIUS);
  }

  // ---- view ----

  zoom(factor, center) {
    const span = this.viewEnd - this.viewStart;
    const pivot = center ?? (this.viewStart + span / 2);
    const minSpan = Math.min(this.frames, 64);
    const next = Math.max(minSpan, Math.min(this.frames, span * factor));
    const ratio = span ? (pivot - this.viewStart) / span : 0.5;
    this.viewStart = Math.round(pivot - next * ratio);
    this.viewEnd = Math.round(this.viewStart + next);
    this.clampView();
    this.draw();
  }

  zoomToSelection() {
    const s = this.selection;
    if (!s || s.end - s.start < 16) return;
    const pad = Math.round((s.end - s.start) * 0.05);
    this.viewStart = s.start - pad;
    this.viewEnd = s.end + pad;
    this.clampView();
    this.draw();
  }

  fit() { this.viewStart = 0; this.viewEnd = this.frames; this.draw(); }

  scroll(frames) {
    const span = this.viewEnd - this.viewStart;
    this.viewStart += frames;
    this.viewEnd = this.viewStart + span;
    this.clampView();
    this.draw();
  }

  clampView() {
    const span = this.viewEnd - this.viewStart;
    if (this.viewStart < 0) { this.viewStart = 0; this.viewEnd = span; }
    if (this.viewEnd > this.frames) { this.viewEnd = this.frames; this.viewStart = Math.max(0, this.frames - span); }
  }

  wheel(ev) {
    ev.preventDefault();
    const rect = this.canvas.getBoundingClientRect();
    if (ev.shiftKey || Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) {
      const delta = ev.shiftKey ? ev.deltaY : ev.deltaX;
      this.scroll(Math.round((delta / this.width()) * (this.viewEnd - this.viewStart)));
    } else {
      this.zoom(ev.deltaY > 0 ? 1.25 : 0.8, this.frameAt(ev.clientX - rect.left));
    }
  }

  // ---- mouse ----

  mouseDown(ev) {
    if (!this.frames || ev.button !== 0) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    const frame = this.frameAt(x);
    if (this.mode === "region" && this.region) {
      const near = (f) => Math.abs(this.xOf(f) - x) <= 7;
      if (near(this.region.start)) this.drag = { kind: "start" };
      else if (near(this.region.end)) this.drag = { kind: "end" };
      else {
        // Click moves the nearer edge
        const toStart = Math.abs(frame - this.region.start);
        const toEnd = Math.abs(frame - this.region.end);
        this.drag = { kind: toStart <= toEnd ? "start" : "end" };
        this.mouseMove(ev);
      }
      return;
    }
    const anchor = this.snapFrame(frame);
    if (ev.shiftKey && this.selection) {
      const keep = Math.abs(frame - this.selection.start) > Math.abs(frame - this.selection.end) ? this.selection.start : this.selection.end;
      this.drag = { kind: "select", anchor: keep };
      this.mouseMove(ev);
      return;
    }
    this.drag = { kind: "select", anchor, moved: false };
    this.cursor = anchor;
  }

  mouseMove(ev) {
    if (!this.drag) return;
    const rect = this.canvas.getBoundingClientRect();
    const frame = this.snapFrame(this.frameAt(ev.clientX - rect.left));
    if (this.drag.kind === "start") {
      this.region.start = Math.min(frame, this.region.end - 1);
      this.onChange("region");
    } else if (this.drag.kind === "end") {
      this.region.end = Math.max(frame, this.region.start + 1);
      this.onChange("region");
    } else {
      const a = this.drag.anchor;
      if (frame !== a) {
        this.drag.moved = true;
        this.selection = { start: Math.min(a, frame), end: Math.max(a, frame) };
        this.onChange("selection");
      }
    }
    this.draw();
  }

  mouseUp() {
    if (!this.drag) return;
    if (this.drag.kind === "select" && !this.drag.moved) {
      // A plain click clears the selection and sets the playback cursor
      this.selection = null;
      this.cursor = this.drag.anchor;
      this.onChange("click", this.drag.anchor);
    }
    this.drag = null;
    this.draw();
  }

  // ---- drawing ----

  draw() {
    const canvas = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    if (!w || !h) return;
    if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(canvas);
    const color = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
    ctx.fillStyle = color("--panel-2", "#1d1d1d");
    ctx.fillRect(0, 0, w, h);
    if (!this.frames) return;

    if (this.region) {
      ctx.fillStyle = "rgba(0,0,0,0.45)";
      const rs = this.xOf(this.region.start), re = this.xOf(this.region.end);
      if (rs > 0) ctx.fillRect(0, 0, Math.min(rs, w), h);
      if (re < w) ctx.fillRect(Math.max(re, 0), 0, w - Math.max(re, 0), h);
    }
    if (this.selection) {
      ctx.fillStyle = "rgba(232,163,61,0.22)";
      const x0 = this.xOf(this.selection.start), x1 = this.xOf(this.selection.end);
      ctx.fillRect(x0, 0, Math.max(1, x1 - x0), h);
    }

    const n = this.channels.length;
    const laneH = h / n;
    const span = this.viewEnd - this.viewStart;
    const perPx = span / w;
    ctx.strokeStyle = color("--line", "#333");
    ctx.lineWidth = 1;
    for (let c = 0; c < n; c++) {
      const mid = laneH * c + laneH / 2;
      ctx.beginPath(); ctx.moveTo(0, mid + 0.5); ctx.lineTo(w, mid + 0.5); ctx.stroke();
    }
    ctx.fillStyle = color("--accent", "#e8a33d");
    ctx.strokeStyle = color("--accent", "#e8a33d");
    for (let c = 0; c < n; c++) {
      const data = this.channels[c];
      const mid = laneH * c + laneH / 2;
      const amp = laneH / 2 - 2;
      if (perPx <= 1.5) {
        // Close zoom: draw the samples as a line with points
        ctx.beginPath();
        const first = Math.max(0, Math.floor(this.viewStart)), last = Math.min(this.frames - 1, Math.ceil(this.viewEnd));
        for (let f = first; f <= last; f++) {
          const x = this.xOf(f), y = mid - data[f] * amp;
          if (f === first) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
        if (perPx < 0.25) {
          for (let f = first; f <= last; f++) ctx.fillRect(this.xOf(f) - 1.5, mid - data[f] * amp - 1.5, 3, 3);
        }
      } else {
        for (let x = 0; x < w; x++) {
          const a = Math.floor(this.viewStart + x * perPx), b = Math.min(this.frames, Math.floor(this.viewStart + (x + 1) * perPx));
          let lo = 1, hi = -1;
          for (let f = a; f < b; f++) { const v = data[f]; if (v < lo) lo = v; if (v > hi) hi = v; }
          if (hi < lo) continue;
          ctx.fillRect(x, mid - hi * amp, 1, Math.max(1, (hi - lo) * amp));
        }
      }
    }

    if (this.region) {
      ctx.fillStyle = "#fff";
      for (const f of [this.region.start, this.region.end]) {
        const x = this.xOf(f);
        if (x < -2 || x > w + 2) continue;
        ctx.fillRect(Math.round(x) - 1, 0, 2, h);
        ctx.fillRect(Math.round(x) - 5, 0, 10, 6);
      }
    }
    if (this.mode === "select" && this.cursor != null && !this.selection) {
      ctx.fillStyle = color("--muted", "#999");
      ctx.fillRect(Math.round(this.xOf(this.cursor)), 0, 1, h);
    }
    if (this.playhead != null) {
      const x = this.xOf(this.playhead);
      ctx.fillStyle = "#fff";
      ctx.fillRect(Math.round(x), 0, 1, h);
    }
  }
}

function nearestZeroCrossing(channels, frame, radius) {
  const len = channels[0].length;
  const lo = Math.max(1, frame - radius), hi = Math.min(len - 1, frame + radius);
  const mono = (f) => { let s = 0; for (const ch of channels) s += ch[f]; return s; };
  for (let d = 0; d <= radius; d++) {
    for (const f of [frame - d, frame + d]) {
      if (f < lo || f > hi) continue;
      const a = mono(f - 1), b = mono(f);
      if (b === 0 || (a < 0) !== (b < 0)) return f;
    }
  }
  return frame;
}

function deinterleave(buffer, channelCount) {
  const all = new Float32Array(buffer);
  const frames = Math.floor(all.length / channelCount);
  const channels = Array.from({ length: channelCount }, () => new Float32Array(frames));
  for (let i = 0, f = 0; f < frames; f++) {
    for (let c = 0; c < channelCount; c++) channels[c][f] = all[i++];
  }
  return channels;
}

// Shared audio output: one context with a master gain, volume and loop apply to all Web Audio playback
const audioOut = {
  ctx: null,
  master: null,
  volume: 1,
  loop: false,
  context() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.volume;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
    return this.ctx;
  },
  setVolume(value) {
    this.volume = value;
    if (this.master) this.master.gain.value = value;
  },
};

// Plays a frame range of the view's audio and moves its playhead
const wavePlayer = {
  ctx: null,
  node: null,
  view: null,
  raf: 0,

  play(view, start, end, onEnd) {
    this.stop();
    if (!view.frames) return;
    this.ctx = audioOut.context();
    const length = Math.max(1, end - start);
    const buffer = this.ctx.createBuffer(view.channels.length, length, view.rate);
    view.channels.forEach((data, c) => buffer.copyToChannel(data.subarray(start, end), c));
    const node = this.ctx.createBufferSource();
    node.buffer = buffer;
    node.loop = audioOut.loop;
    node.connect(audioOut.master);
    const t0 = this.ctx.currentTime;
    node.onended = () => {
      if (this.node !== node) return;
      this.node = null;
      cancelAnimationFrame(this.raf);
      view.playhead = null;
      view.draw();
      if (onEnd) onEnd();
      if (typeof markPlaying === "function") markPlaying();
    };
    node.start();
    this.node = node;
    this.view = view;
    const tick = () => {
      const played = (this.ctx.currentTime - t0) * view.rate;
      view.playhead = start + (node.loop ? played % length : Math.min(length, played));
      view.draw();
      this.raf = requestAnimationFrame(tick);
    };
    tick();
    if (typeof markPlaying === "function") markPlaying();
  },

  stop() {
    if (this.node) {
      const node = this.node;
      this.node = null;
      try { node.stop(); } catch (_) { /* already stopped */ }
    }
    cancelAnimationFrame(this.raf);
    if (this.view) { this.view.playhead = null; this.view.draw(); }
    if (typeof markPlaying === "function") markPlaying();
  },

  get playing() { return this.node !== null; },
};
