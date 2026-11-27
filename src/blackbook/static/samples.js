// Samples tab: every WAV on the card, where it is used, play, edit, rename, delete

const lib = {
  items: null,
  factory: false,
  loading: false,
};

function fmtDuration(seconds) {
  if (seconds == null) return "";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 2 : 1)} s`;
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.round(seconds - m * 60)).padStart(2, "0")} min`;
}

async function loadSamples(force = false) {
  const list = document.getElementById("smp-list");
  const wantFactory = document.getElementById("smp-factory").checked;
  if (lib.items && !force && lib.factory === wantFactory) { renderSamples(); return; }
  if (lib.loading) return;
  lib.loading = true;
  if (!lib.items) list.replaceChildren(el("p", { class: "muted", style: "padding:12px" }, "Reading the card ..."));
  try {
    lib.items = await api("GET", "/api/samples" + (wantFactory ? "?factory=true" : ""));
    lib.factory = wantFactory;
  } catch (err) {
    list.replaceChildren(el("p", { class: "err", style: "padding:12px" }, err.message));
    return;
  } finally {
    lib.loading = false;
  }
  fillProjectFilter();
  renderSamples();
}

function fillProjectFilter() {
  const select = document.getElementById("smp-project");
  const current = select.value;
  const projects = [...new Set(lib.items.filter((s) => s.path.startsWith("Projects/")).map((s) => s.path.split("/")[1]))].sort();
  select.replaceChildren(el("option", { value: "" }, "All places"),
    el("option", { value: "@Samples" }, "Samples folder"),
    el("option", { value: "@UserPatches" }, "User patches"),
    lib.factory ? el("option", { value: "@Patches" }, "Factory patches") : null,
    ...projects.map((p) => el("option", { value: p }, `Project: ${p}`)));
  select.value = [...select.options].some((o) => o.value === current) ? current : "";
}

function sampleMatches(s) {
  const q = document.getElementById("smp-search").value.trim().toLowerCase();
  const where = document.getElementById("smp-project").value;
  if (document.getElementById("smp-recordings").checked && !s.recording) return false;
  if (document.getElementById("smp-unused").checked && s.uses.length) return false;
  if (where.startsWith("@") && !s.path.startsWith(where.slice(1) + "/")) return false;
  if (where && !where.startsWith("@") && !s.path.startsWith(`Projects/${where}/`) && !s.uses.some((u) => u.kind === "project" && u.name === where)) return false;
  if (q && !s.path.toLowerCase().includes(q) && !s.uses.some((u) => u.name.toLowerCase().includes(q))) return false;
  return true;
}

function renderSamples() {
  const list = document.getElementById("smp-list");
  if (!lib.items) return;
  const sort = document.getElementById("smp-sort").value;
  const items = lib.items.filter(sampleMatches);
  const by = {
    name: (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }),
    folder: (a, b) => a.folder.localeCompare(b.folder) || a.name.localeCompare(b.name, undefined, { numeric: true }),
    duration: (a, b) => (b.duration ?? 0) - (a.duration ?? 0),
  }[sort];
  items.sort(by);
  const unused = items.filter((s) => !s.uses.length && !s.factory).length;
  const usePill = (u) => el("span", { class: "use-pill " + u.kind, title: `${u.kind === "project" ? "Project" : "Patch"}: ${u.xml}` }, u.name);
  fill(list,
    el("div", { class: "smp-head" },
      el("span", {}, `${items.length} sample${items.length === 1 ? "" : "s"}`),
      unused ? el("span", { class: "muted" }, ` · ${unused} not used by any patch or project`) : null),
    el("table", { class: "samples-table smp-table" }, el("tbody", {}, items.slice(0, 1000).map((s) =>
      el("tr", {},
        el("td", {}, el("button", { class: "small playbtn", "data-src": s.source, onclick: () => play(s.source) })),
        el("td", { class: "smp-name" },
          el("div", {}, s.recording ? el("span", { class: "rec-dot", title: "Recording" }) : null, s.name),
          el("div", { class: "muted smp-folder" }, s.folder)),
        el("td", { class: "muted smp-dur" }, fmtDuration(s.duration)),
        el("td", { class: "smp-uses" }, s.uses.length ? s.uses.map(usePill) : el("span", { class: "use-pill unused" }, "unused")),
        el("td", { class: "sample-actions" },
          el("button", { class: "small", title: s.factory ? "Edit and save as a new file; factory samples stay unchanged" : "Edit the sample", onclick: () => openAudioEditor(s.source, { card: true, onWritten: () => loadSamples(true) }) }, "Edit wave"),
          s.factory ? null : el("button", { class: "small", title: "Rename the file and every reference to it", onclick: async () => { if (await renameSample(s.source)) loadSamples(true); } }, "Rename"),
          s.factory ? null : el("button", {
            class: "small", disabled: s.uses.length > 0,
            title: s.uses.length ? "Used by a patch or project, it cannot be deleted" : "Delete the file from the card",
            onclick: () => deleteSample(s),
          }, "Delete")))))),
    items.length > 1000 ? el("p", { class: "muted", style: "padding:8px" }, `Showing the first 1000 of ${items.length}. Narrow the search.`) : null);
  markPlaying();
}

async function deleteSample(s) {
  const text = [`${s.path}`, "", "No patch or project uses this file. It is removed from the card; a copy stays in the local backup folder of this session, and a snapshot is taken before and after if the backup is set up."].join("\n");
  if (!(await confirmDialog("Delete sample?", text, "Delete"))) return;
  try {
    await api("POST", "/api/sample/delete", { source: s.source });
    toast(`Deleted ${s.name}`);
    stop();
    loadSamples(true);
  } catch (err) { toast(err.message, true); }
}

["smp-search", "smp-project", "smp-sort", "smp-recordings", "smp-unused"].forEach((id) =>
  document.getElementById(id).addEventListener("input", renderSamples));
document.getElementById("smp-factory").addEventListener("change", () => loadSamples(true));
document.getElementById("smp-reload").addEventListener("click", () => loadSamples(true));
document.querySelectorAll("nav button").forEach((button) => button.addEventListener("click", () => {
  if (button.dataset.view === "samples") loadSamples(!lib.items);
}));
