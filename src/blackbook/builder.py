"""Patch builder: turns a patch specification into a change plan and applies it."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import templates
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
    source: Path
    gain: float = 0.0
    pitch: float = 0.0
    pan: int = 0
    choke_group: int = 0
    reverse: bool = False
    loop: bool = False


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
class FileCopy:
    source: Path
    target_name: str
    info: str


@dataclass
class Plan:
    patch_type: str
    target_dir: Path
    target_ref: str
    xml: str
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


def unique_names(sources: list[Path]) -> dict[Path, str]:
    """Assign a unique target file name to every distinct source file."""
    names: dict[Path, str] = {}
    used: set[str] = set()
    for source in sources:
        if source in names:
            continue
        stem, suffix = source.stem, source.suffix or ".wav"
        candidate = stem + suffix
        n = 2
        while candidate.casefold() in used or candidate.casefold() == "preview.wav":
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


def plan_oneshot(card: Card, spec: OneShotSpec) -> Plan:
    errors: list[str] = []
    warnings: list[str] = []
    target, ref = target_for(card, "OneShots", spec.name, errors, warnings)

    if not spec.pads:
        errors.append("no pad has a sample")

    infos: dict[Path, WavInfo] = {}
    for slot, pad in sorted(spec.pads.items()):
        if not 0 <= slot <= 15:
            errors.append(f"invalid pad {slot}")
            continue
        info = check_wav(pad.source, f"pad {slot + 1}", errors, warnings)
        if info:
            infos[pad.source] = info

    names = unique_names([pad.source for _, pad in sorted(spec.pads.items())])
    pads_xml: dict[int, tuple[dict, dict]] = {}
    for slot, pad in spec.pads.items():
        info = infos.get(pad.source)
        frames = info.frames if info else 0
        inst = {
            "gaindb": milli(pad.gain),
            "pitch": milli(pad.pitch),
            "panpos": pad.pan,
            "chokegrp": pad.choke_group,
            "reverse": int(pad.reverse),
            "loopmodes": int(pad.loop),
        }
        asst = {"filename": names[pad.source], "samlen": frames, "loopend": frames}
        pads_xml[slot] = (inst, asst)

    xml = templates.oneshot_patch({"cellname": spec.name, "trkgain": milli(spec.track_gain)}, pads_xml)
    copies = [FileCopy(src, names[src], infos[src].describe() if src in infos else "") for src in names]

    preview = None
    if not errors:
        segments = [infos_audio(pad.source, infos[pad.source], 0.5) for _, pad in sorted(spec.pads.items())]
        preview = build_preview(segments)

    return Plan("OneShots", target, ref, xml, copies, spec.tags, preview, errors, warnings)


def plan_multisample(card: Card, spec: MultisampleSpec) -> Plan:
    errors: list[str] = []
    warnings: list[str] = []
    target, ref = target_for(card, "SampInst", spec.name, errors, warnings)

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
    names = unique_names([i.source for i in ordered])
    zones_xml = []
    for item in ordered:
        z = item.zone
        frames = infos[item.source].frames if item.source in infos else 0
        zones_xml.append(
            {
                "filename": names[item.source],
                "rootnote": z.root,
                "keyrangebottom": z.key_low,
                "keyrangetop": z.key_high,
                "velroot": z.vel_root,
                "velrangebottom": z.vel_low,
                # Factory patches store 128 as upper bound of the top layer
                "velrangetop": 128 if z.vel_high == 127 else z.vel_high,
                "samlen": frames,
                "loopend": frames,
            }
        )

    xml = templates.multisample_patch(
        {"cellname": spec.name, "trkgain": milli(spec.track_gain)}, {"gaindb": milli(spec.gain)}, zones_xml
    )
    copies = [FileCopy(src, names[src], infos[src].describe() if src in infos else "") for src in names]

    preview = None
    if not errors:
        preview = build_preview([infos_audio(pick_preview_zone(ordered).source, None, 2.0)])

    return Plan("SampInst", target, ref, xml, copies, spec.tags, preview, errors, warnings)


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
    """Write the patch folder and update UserPatches/patchindex.xml. Returns written paths."""
    if not plan.ok:
        raise ValueError("plan contains errors")
    if plan.target_dir.exists():
        raise FileExistsError(plan.target_dir)

    written: list[str] = []
    tmp_dir = plan.target_dir.with_name(plan.target_dir.name + ".blackbook-tmp")
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True)
    try:
        for copy in plan.copies:
            shutil.copyfile(copy.source, tmp_dir / copy.target_name)
        # Files written by the device carry a BOM
        (tmp_dir / "patch.xml").write_bytes(("﻿" + plan.xml).encode("utf-8"))
        if plan.preview is not None:
            write_pcm24(tmp_dir / "preview.wav", plan.preview, PREVIEW_RATE)
        tmp_dir.rename(plan.target_dir)
    except BaseException:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    written += [card.relative(p) for p in sorted(plan.target_dir.iterdir())]
    backup.record_created(plan.target_dir)

    if plan.tags:
        index_path = card.index_path("UserPatches")
        backup.save(index_path)
        index = PatchIndex(index_path)
        index.set_tags(plan.target_ref, plan.tags)
        index.save()
        written.append(card.relative(index_path))

    return written
