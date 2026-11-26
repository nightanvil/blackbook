"""Patch builder: turns a patch specification into a change plan and applies it."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import patchedit, templates
from .backup import Backup
from .card import Card
from .cardpath import join_reference, validate_name
from .mapping import Zone
from .patchindex import PatchIndex
from .wav import WavError, WavInfo, read_audio, read_info, resample, to_stereo, write_pcm24

PREVIEW_RATE = 48000
SUPPORTED_RATES = {44100, 48000}
SUPPORTED_BITS = {16, 24}


@dataclass
class Pad:
    # None keeps the pad of the base patch untouched (for example when its file is missing)
    source: Path | None
    gain: float = 0.0
    pitch: float = 0.0
    pan: int = 0
    choke_group: int = 0
    reverse: bool = False
    loop_mode: int = 0


@dataclass
class OneShotSpec:
    name: str
    tags: list[str]
    pads: dict[int, Pad]
    track_gain: float = 0.0


@dataclass
class MultisampleZone:
    source: Path
    zone: Zone


@dataclass
class MultisampleSpec:
    name: str
    tags: list[str]
    zones: list[MultisampleZone]
    track_gain: float = 0.0
    gain: float = 0.0


@dataclass
class Base:
    """Existing patch used as starting point. mode 'edit' changes it in place, 'copy' saves a new patch."""

    patch_dir: Path
    mode: str
    text: str
    has_bom: bool

    @classmethod
    def load(cls, patch_dir: Path, mode: str) -> Base:
        raw = (patch_dir / "patch.xml").read_bytes().decode("utf-8")
        has_bom = raw.startswith("﻿")
        return cls(patch_dir, mode, raw[1:] if has_bom else raw, has_bom)


@dataclass
class FileCopy:
    source: Path
    target_name: str
    info: str


@dataclass
class Plan:
    patch_type: str
    mode: str
    target_dir: Path
    target_ref: str
    xml: str
    xml_bom: bool
    copies: list[FileCopy]
    tags: list[str]
    preview: np.ndarray | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def milli(value: float) -> int:
    """Device values for gain and pitch are stored in thousandths (dB, semitones)."""
    return round(value * 1000)


def check_wav(path: Path, label: str, errors: list[str], warnings: list[str]) -> WavInfo | None:
    if not path.is_file():
        errors.append(f"{label}: file not found ({path})")
        return None
    try:
        info = read_info(path)
    except (WavError, OSError) as exc:
        errors.append(f"{label}: {exc}")
        return None
    if info.is_float:
        warnings.append(f"{label}: 32 bit float is not used in factory content, support is unverified")
    elif info.bits not in SUPPORTED_BITS:
        warnings.append(f"{label}: {info.bits} bit is not used in factory content, support is unverified")
    if info.sample_rate not in SUPPORTED_RATES:
        warnings.append(f"{label}: {info.sample_rate} Hz is not used in factory content, support is unverified")
    if info.channels not in (1, 2):
        errors.append(f"{label}: {info.channels} channels are not supported")
    if info.frames == 0:
        errors.append(f"{label}: file contains no audio")
    return info


def assign_names(sources: list[Path], base_dir: Path | None = None) -> dict[Path, str]:
    """Assign a unique target file name to every distinct source file.

    Files inside base_dir keep their name, all other names avoid the files of base_dir.
    """
    names: dict[Path, str] = {}
    used: set[str] = {"preview.wav"}
    if base_dir is not None:
        used |= {p.name.casefold() for p in base_dir.iterdir()}
        for source in sources:
            if source.parent == base_dir:
                names[source] = source.name
    for source in sources:
        if source in names:
            continue
        stem, suffix = source.stem, source.suffix or ".wav"
        candidate = stem + suffix
        n = 2
        while candidate.casefold() in used:
            candidate = f"{stem}_{n}{suffix}"
            n += 1
        used.add(candidate.casefold())
        names[source] = candidate
    return names


def target_for(card: Card, type_dir: str, name: str, errors: list[str], warnings: list[str]) -> tuple[Path, str]:
    name_errors, name_warnings = validate_name(name)
    errors += name_errors
    warnings += name_warnings
    target = card.root / "UserPatches" / type_dir / name
    if name and target.exists():
        errors.append(f"patch already exists: UserPatches/{type_dir}/{name}")
    else:
        parent = card.root / "UserPatches" / type_dir
        if parent.is_dir() and any(p.name.casefold() == name.casefold() for p in parent.iterdir()):
            errors.append(f"patch already exists with different case: UserPatches/{type_dir}/{name}")
    return target, join_reference("UserPatches", type_dir, name)


def resolve_target(card: Card, type_dir: str, spec_name: str, base: Base | None, errors, warnings):
    if base is not None and base.mode == "edit":
        user_root = card.root / "UserPatches"
        if not base.patch_dir.is_relative_to(user_root):
            errors.append("only user patches can be edited in place, use the patch as template instead")
        return base.patch_dir, join_reference(*base.patch_dir.relative_to(card.root).parts)
    return target_for(card, type_dir, spec_name, errors, warnings)


def copies_for(names: dict[Path, str], infos: dict[Path, WavInfo], base: Base | None) -> list[FileCopy]:
    """Files to copy into the target folder. Editing in place only copies files from outside."""
    result = []
    for src, name in names.items():
        if base is not None and base.mode == "edit" and src.parent == base.patch_dir:
            continue
        result.append(FileCopy(src, name, infos[src].describe() if src in infos else ""))
    return result


def plan_oneshot(card: Card, spec: OneShotSpec, base: Base | None = None) -> Plan:
    errors: list[str] = []
    warnings: list[str] = []
    target, ref = resolve_target(card, "OneShots", spec.name, base, errors, warnings)
    mode = base.mode if base else "new"

    active = {slot: pad for slot, pad in spec.pads.items() if pad.source is not None}
    if not spec.pads:
        errors.append("no pad has a sample")

    infos: dict[Path, WavInfo] = {}
    for slot, pad in sorted(active.items()):
        if not 0 <= slot <= 15:
            errors.append(f"invalid pad {slot}")
            continue
        info = check_wav(pad.source, f"pad {slot + 1}", errors, warnings)
        if info:
            infos[pad.source] = info

    names = assign_names([pad.source for _, pad in sorted(active.items())], base.patch_dir if base else None)

    def inst_values(pad: Pad) -> dict:
        return {
            "gaindb": milli(pad.gain),
            "pitch": milli(pad.pitch),
            "panpos": pad.pan,
            "chokegrp": pad.choke_group,
            "reverse": int(pad.reverse),
            "loopmodes": pad.loop_mode,
        }

    def new_sample(pad: Pad) -> dict:
        frames = infos[pad.source].frames if pad.source in infos else 0
        return {
            "filename": names[pad.source],
            "samstart": 0,
            "samlen": frames,
            "loopstart": 0,
            "loopend": frames,
        }

    samples_changed = base is None
    if base is None:
        pads_xml = {slot: (inst_values(pad), new_sample(pad)) for slot, pad in active.items()}
        xml = templates.oneshot_patch({"cellname": spec.name, "trkgain": milli(spec.track_gain)}, pads_xml)
        xml_bom = True
    else:
        existing = {
            int(c.attrs["celldisppos"]): (
                cells_[i + 1].attrs.get("filename", "")
                if i + 1 < len(cells_) and cells_[i + 1].type == "samasst"
                else ""
            )
            for cells_ in [patchedit.cells(base.text)]
            for i, c in enumerate(cells_)
            if c.type == "saminst" and "celldisppos" in c.attrs
        }
        updates: dict[int, tuple[dict, dict]] = {}
        for slot, pad in active.items():
            same_file = (
                pad.source.parent == base.patch_dir and existing.get(slot, "").casefold() == pad.source.name.casefold()
            )
            sample = {} if same_file else new_sample(pad)
            samples_changed |= bool(sample)
            updates[slot] = (inst_values(pad), sample)
        for slot, filename in existing.items():
            if filename and slot not in spec.pads:
                updates[slot] = ({}, {"filename": "", "samstart": 0, "samlen": 0, "loopstart": 0, "loopend": 0})
                samples_changed = True
        xml, edit_errors = patchedit.edit_oneshot(base.text, updates)
        errors += edit_errors
        if mode == "copy":
            xml = patchedit.set_track_params(xml, {"cellname": spec.name})
        xml_bom = base.has_bom
        kept = [slot for slot, pad in spec.pads.items() if pad.source is None]
        if kept and mode == "copy":
            warnings.append(
                "pads with missing files are copied as references without file: "
                + ", ".join(str(s + 1) for s in sorted(kept))
            )

    copies = copies_for(names, infos, base)

    preview = None
    if not errors and samples_changed and active:
        segments = [infos_audio(pad.source, infos[pad.source], 0.5) for _, pad in sorted(active.items())]
        preview = build_preview(segments)

    return Plan("OneShots", mode, target, ref, xml, xml_bom, copies, spec.tags, preview, errors, warnings)


def plan_multisample(card: Card, spec: MultisampleSpec, base: Base | None = None) -> Plan:
    errors: list[str] = []
    warnings: list[str] = []
    target, ref = resolve_target(card, "SampInst", spec.name, base, errors, warnings)
    mode = base.mode if base else "new"

    if not spec.zones:
        errors.append("no zones defined")

    infos: dict[Path, WavInfo] = {}
    for item in spec.zones:
        label = item.source.name
        info = check_wav(item.source, label, errors, warnings)
        if info:
            infos[item.source] = info
        z = item.zone
        if not (0 <= z.key_low <= z.root <= z.key_high <= 127):
            if 0 <= z.key_low <= z.key_high <= 127:
                warnings.append(f"{label}: root note {z.root} lies outside its key range")
            else:
                errors.append(f"{label}: invalid key range {z.key_low}-{z.key_high}")
        if not (0 <= z.vel_low <= z.vel_high <= 127):
            errors.append(f"{label}: invalid velocity range {z.vel_low}-{z.vel_high}")

    covered = np.zeros((128, 128), dtype=bool)
    for item in spec.zones:
        z = item.zone
        if 0 <= z.key_low <= z.key_high <= 127 and 0 <= z.vel_low <= z.vel_high <= 127:
            covered[z.key_low : z.key_high + 1, z.vel_low : z.vel_high + 1] = True
    if spec.zones and not covered.all():
        missing_keys = int((~covered).any(axis=1).sum())
        warnings.append(f"{missing_keys} keys have velocities without a sample")

    ordered = sorted(spec.zones, key=lambda i: (i.zone.root, i.zone.vel_low))
    names = assign_names([i.source for i in ordered], base.patch_dir if base else None)

    def mapping_values(z: Zone) -> dict:
        return {
            "rootnote": z.root,
            "keyrangebottom": z.key_low,
            "keyrangetop": z.key_high,
            "velroot": z.vel_root,
            "velrangebottom": z.vel_low,
            # Factory patches store 128 as upper bound of the top layer
            "velrangetop": 128 if z.vel_high == 127 else z.vel_high,
        }

    def full_values(item: MultisampleZone) -> dict:
        frames = infos[item.source].frames if item.source in infos else 0
        return {"filename": names[item.source], **mapping_values(item.zone), "samlen": frames, "loopend": frames}

    samples_changed = base is None
    if base is None:
        zones_xml = [full_values(item) for item in ordered]
        xml = templates.multisample_patch(
            {"cellname": spec.name, "trkgain": milli(spec.track_gain)}, {"gaindb": milli(spec.gain)}, zones_xml
        )
        xml_bom = True
    else:
        existing = [c.attrs.get("filename", "") for c in patchedit.cells(base.text) if c.type == "samasst"]
        available = [f.casefold() for f in existing]
        keep: list[tuple[str, dict]] = []
        add: list[dict] = []
        for item in ordered:
            name = item.source.name
            if item.source.parent == base.patch_dir and name.casefold() in available:
                available.remove(name.casefold())
                keep.append((name, mapping_values(item.zone)))
            else:
                add.append(full_values(item))
        samples_changed = bool(add) or bool(available)
        xml, edit_errors = patchedit.edit_multisample(base.text, {"gaindb": milli(spec.gain)}, keep, add)
        errors += edit_errors
        if mode == "copy":
            xml = patchedit.set_track_params(xml, {"cellname": spec.name})
        xml_bom = base.has_bom

    copies = copies_for(names, infos, base)

    preview = None
    if not errors and samples_changed and ordered:
        preview = build_preview([infos_audio(pick_preview_zone(ordered).source, None, 2.0)])

    return Plan("SampInst", mode, target, ref, xml, xml_bom, copies, spec.tags, preview, errors, warnings)


def pick_preview_zone(zones: list[MultisampleZone]) -> MultisampleZone:
    """Zone closest to C3 (48) with the loudest layer at or below velocity 100."""
    best_root = min({z.zone.root for z in zones}, key=lambda r: abs(r - 48))
    layer = [z for z in zones if z.zone.root == best_root]
    soft = [z for z in layer if z.zone.vel_low <= 100]
    return max(soft or layer, key=lambda z: z.zone.vel_high)


def infos_audio(path: Path, info: WavInfo | None, max_seconds: float) -> np.ndarray:
    data, rate = read_audio(path, info)
    data = to_stereo(resample(data, rate, PREVIEW_RATE))
    limit = int(max_seconds * PREVIEW_RATE)
    if len(data) > limit:
        data = data[:limit].copy()
        fade = min(len(data), int(0.02 * PREVIEW_RATE))
        data[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)[:, None]
    return data


def build_preview(segments: list[np.ndarray]) -> np.ndarray:
    """Concatenate segments with short gaps and normalize to -1 dBFS."""
    gap = np.zeros((int(0.05 * PREVIEW_RATE), 2), dtype=np.float32)
    parts: list[np.ndarray] = []
    for segment in segments:
        parts += [segment, gap]
    audio = np.concatenate(parts) if parts else np.zeros((PREVIEW_RATE // 10, 2), dtype=np.float32)
    peak = float(np.abs(audio).max()) if len(audio) else 0.0
    if peak > 0:
        audio = audio * (10 ** (-1 / 20) / peak)
    return audio.astype(np.float32)


def apply(card: Card, plan: Plan, backup: Backup) -> list[str]:
    """Write the patch and update UserPatches/patchindex.xml. Returns written paths."""
    if not plan.ok:
        raise ValueError("plan contains errors")
    xml_bytes = (("﻿" if plan.xml_bom else "") + plan.xml).encode("utf-8")

    if plan.mode == "edit":
        written = write_in_place(card, plan, backup, xml_bytes)
    else:
        written = write_new(card, plan, backup, xml_bytes)

    index_path = card.index_path("UserPatches")
    index = PatchIndex(index_path)
    if index.tags_for(plan.target_ref) != plan.tags:
        backup.save(index_path)
        index.set_tags(plan.target_ref, plan.tags)
        index.save()
        written.append(card.relative(index_path))
    return written


def write_new(card: Card, plan: Plan, backup: Backup, xml_bytes: bytes) -> list[str]:
    if plan.target_dir.exists():
        raise FileExistsError(plan.target_dir)
    tmp_dir = plan.target_dir.with_name(plan.target_dir.name + ".blackbook-tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for copy in plan.copies:
            shutil.copyfile(copy.source, tmp_dir / copy.target_name)
        (tmp_dir / "patch.xml").write_bytes(xml_bytes)
        if plan.preview is not None:
            write_pcm24(tmp_dir / "preview.wav", plan.preview, PREVIEW_RATE)
        tmp_dir.rename(plan.target_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    backup.record_created(plan.target_dir)
    return [card.relative(p) for p in sorted(plan.target_dir.iterdir())]


def write_in_place(card: Card, plan: Plan, backup: Backup, xml_bytes: bytes) -> list[str]:
    written: list[str] = []
    for copy in plan.copies:
        target = plan.target_dir / copy.target_name
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(copy.source, target)
        backup.record_created(target)
        written.append(card.relative(target))

    xml_path = plan.target_dir / "patch.xml"
    backup.save(xml_path)
    tmp = xml_path.with_name("patch.xml.blackbook-tmp")
    tmp.write_bytes(xml_bytes)
    os.replace(tmp, xml_path)
    written.append(card.relative(xml_path))

    if plan.preview is not None:
        preview_path = plan.target_dir / "preview.wav"
        backup.save(preview_path)
        write_pcm24(preview_path, plan.preview, PREVIEW_RATE)
        written.append(card.relative(preview_path))
    return written
