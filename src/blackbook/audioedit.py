"""Destructive WAV editing with undo: sessions hold the audio in memory until it is saved.

Audio is kept as float32 with shape (frames, channels). PCM is scaled by 2^(bits-1) in both directions,
so samples that are not touched by an edit are written back bit-identical.
"""

from __future__ import annotations

import struct
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .wav import FORMAT_FLOAT, FORMAT_PCM, WavError, read_audio, read_info

MAX_SESSIONS = 8
MAX_HISTORY = 50

OPS = ("crop", "delete", "silence", "fade_in", "fade_out", "gain", "normalize", "reverse")


class EditError(Exception):
    pass


@dataclass
class Session:
    id: str
    source: str
    name: str
    sample_rate: int
    bits: int
    is_float: bool
    history: list[np.ndarray] = field(default_factory=list)
    # Per history entry the operations from the opened file to that version, for mapping frame positions
    chains: list[list[tuple[str, int, int]]] = field(default_factory=list)
    position: int = 0

    @property
    def data(self) -> np.ndarray:
        return self.history[self.position]

    @property
    def ops(self) -> list[tuple[str, int, int]]:
        return self.chains[self.position]

    def map_position(self, frame: int) -> int:
        return map_position(self.ops, frame)

    def state(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "name": self.name,
            "sample_rate": self.sample_rate,
            "channels": self.data.shape[1],
            "bits": self.bits,
            "frames": len(self.data),
            "version": self.position,
            "can_undo": self.position > 0,
            "can_redo": self.position < len(self.history) - 1,
            "changed": self.position > 0,
        }


class Editor:
    def __init__(self) -> None:
        self.sessions: OrderedDict[str, Session] = OrderedDict()

    def open(self, path: Path, source: str) -> Session:
        try:
            info = read_info(path)
            data, rate = read_audio(path, info)
        except (WavError, OSError) as exc:
            raise EditError(str(exc)) from exc
        if info.format_tag not in (FORMAT_PCM, FORMAT_FLOAT) or (not info.is_float and info.bits not in (16, 24, 32)):
            raise EditError(f"{path.name}: {info.describe()} cannot be edited, supported are 16, 24 and 32 bit")
        session = Session(uuid.uuid4().hex, source, path.name, rate, info.bits, info.is_float, [data.copy()], [[]])
        self.sessions[session.id] = session
        while len(self.sessions) > MAX_SESSIONS:
            self.sessions.popitem(last=False)
        return session

    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise EditError("edit session expired, open the sample again")
        self.sessions.move_to_end(session_id)
        return session

    def close(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)

    def apply(self, session: Session, op: str, start: int, end: int, value: float = 0.0) -> None:
        result = apply_op(session.data, op, start, end, value)
        chain = session.chains[session.position] + [(op, start, end)]
        del session.history[session.position + 1:]
        del session.chains[session.position + 1:]
        session.history.append(result)
        session.chains.append(chain)
        if len(session.history) > MAX_HISTORY:
            session.history.pop(0)
            session.chains.pop(0)
        session.position = len(session.history) - 1

    def undo(self, session: Session) -> None:
        if session.position > 0:
            session.position -= 1

    def redo(self, session: Session) -> None:
        if session.position < len(session.history) - 1:
            session.position += 1


def apply_op(data: np.ndarray, op: str, start: int, end: int, value: float = 0.0) -> np.ndarray:
    """Return a new array with op applied to the frames start..end (end exclusive)."""
    frames = len(data)
    if op not in OPS:
        raise EditError(f"unknown operation {op}")
    if not 0 <= start < end <= frames:
        raise EditError(f"invalid selection {start} to {end} of {frames} frames")
    if op == "crop":
        return data[start:end].copy()
    if op == "delete":
        if end - start >= frames:
            raise EditError("cannot delete the whole sample")
        return np.concatenate([data[:start], data[end:]])
    result = data.copy()
    part = result[start:end]
    if op == "silence":
        part[:] = 0
    elif op in ("fade_in", "fade_out"):
        # Equal power curve: smooth onset, no audible step at the ends
        ramp = np.sin(np.linspace(0.0, np.pi / 2, end - start, dtype=np.float64)) ** 2
        if op == "fade_out":
            ramp = ramp[::-1]
        part *= ramp[:, None].astype(np.float32)
    elif op == "gain":
        part *= np.float32(10 ** (value / 20))
    elif op == "normalize":
        peak = float(np.max(np.abs(part))) if part.size else 0.0
        if peak == 0:
            raise EditError("the selection is silent, nothing to normalize")
        part *= np.float32(10 ** (value / 20) / peak)
    elif op == "reverse":
        part[:] = part[::-1].copy()
    return result


def map_position(ops: list[tuple[str, int, int]], frame: int) -> int:
    """Where a frame of the opened file ends up after the operations; removed frames go to the cut."""
    for op, start, end in ops:
        if op == "crop":
            frame = min(max(frame - start, 0), end - start)
        elif op == "delete":
            if frame >= end:
                frame -= end - start
            elif frame > start:
                frame = start
    return frame


def nearest_zero_crossing(data: np.ndarray, position: int, radius: int = 2000) -> int:
    """Frame closest to position where the channel sum changes sign or is zero."""
    frames = len(data)
    if frames == 0:
        return 0
    low, high = max(0, position - radius), min(frames - 1, position + radius)
    mono = data[low:high + 1].sum(axis=1)
    if mono.size < 2:
        return position
    signs = np.signbit(mono)
    candidates = np.nonzero((signs[1:] != signs[:-1]) | (mono[1:] == 0))[0] + 1 + low
    if candidates.size == 0:
        return position
    return int(candidates[np.argmin(np.abs(candidates - position))])


def pcm_bytes(data: np.ndarray) -> bytes:
    """Interleaved little endian float32 for the browser."""
    return np.ascontiguousarray(data, dtype="<f4").tobytes()


def write_wav(path: Path, data: np.ndarray, sample_rate: int, bits: int, is_float: bool) -> None:
    """Write audio in the given format, PCM scaled by 2^(bits-1) and clipped."""
    channels = data.shape[1]
    format_tag, payload = wav_payload(data, bits, is_float)
    block_align = channels * bits // 8
    fmt = struct.pack("<HHIIHH", format_tag, channels, sample_rate, sample_rate * block_align, block_align, bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    if len(payload) & 1:
        body += b"\x00"
    tmp = path.with_name(path.name + ".blackbook-tmp")
    tmp.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    tmp.replace(path)


def wav_payload(data: np.ndarray, bits: int, is_float: bool) -> tuple[int, bytes]:
    """Format tag and interleaved little endian sample bytes, PCM scaled by 2^(bits-1) and clipped."""
    if is_float:
        if bits != 32:
            raise EditError(f"unsupported float width {bits}")
        return FORMAT_FLOAT, np.ascontiguousarray(data, dtype="<f4").tobytes()
    full = float(2 ** (bits - 1))
    ints = np.clip(np.round(data.astype(np.float64) * full), -full, full - 1).astype(np.int64).reshape(-1)
    if bits == 16:
        return FORMAT_PCM, ints.astype("<i2").tobytes()
    if bits == 24:
        raw = np.empty((len(ints), 3), dtype=np.uint8)
        raw[:, 0] = ints & 0xFF
        raw[:, 1] = (ints >> 8) & 0xFF
        raw[:, 2] = (ints >> 16) & 0xFF
        return FORMAT_PCM, raw.tobytes()
    if bits == 32:
        return FORMAT_PCM, ints.astype("<i4").tobytes()
    raise EditError(f"unsupported PCM width {bits}")


def rewrite_wav(path: Path, session: Session) -> None:
    """Replace the audio of an existing WAV in place.

    All chunks except the audio stay byte-identical and in their order. Positions in cue and smpl
    chunks follow the edit, so markers and loops stay on the same sound.
    """
    original = path.read_bytes()
    if original[:4] != b"RIFF" or original[8:12] != b"WAVE":
        raise EditError(f"{path.name} is not a RIFF/WAVE file")
    _tag, payload = wav_payload(session.data, session.bits, session.is_float)
    frames = len(session.data)
    out = bytearray()
    pos = 12
    while pos + 8 <= len(original):
        chunk_id, size = struct.unpack_from("<4sI", original, pos)
        body = original[pos + 8:pos + 8 + size]
        if chunk_id == b"data":
            body = payload
        elif chunk_id == b"cue " and len(body) >= 4:
            body = bytearray(body)
            count = struct.unpack_from("<I", body, 0)[0]
            for i in range(count):
                offset = 4 + i * 24
                if offset + 24 > len(body):
                    break
                for field_offset in (4, 20):
                    old = struct.unpack_from("<I", body, offset + field_offset)[0]
                    struct.pack_into("<I", body, offset + field_offset, min(session.map_position(old), frames))
            body = bytes(body)
        elif chunk_id == b"smpl" and len(body) >= 36:
            body = bytearray(body)
            count = struct.unpack_from("<I", body, 28)[0]
            for i in range(count):
                offset = 36 + i * 24
                if offset + 24 > len(body):
                    break
                for field_offset in (8, 12):
                    old = struct.unpack_from("<I", body, offset + field_offset)[0]
                    struct.pack_into("<I", body, offset + field_offset, min(session.map_position(old), frames))
            body = bytes(body)
        out += chunk_id + struct.pack("<I", len(body)) + body
        if len(body) & 1:
            out += b"\x00"
        pos += 8 + size + (size & 1)
    tmp = path.with_name(path.name + ".blackbook-tmp")
    tmp.write_bytes(b"RIFF" + struct.pack("<I", 4 + len(out)) + b"WAVE" + bytes(out))
    tmp.replace(path)


def free_name(folder: Path, stem: str, suffix: str = ".wav") -> Path:
    used = {p.name.casefold() for p in folder.iterdir()} if folder.is_dir() else set()
    candidate = f"{stem}{suffix}"
    n = 2
    while candidate.casefold() in used:
        candidate = f"{stem}_{n}{suffix}"
        n += 1
    return folder / candidate
