"""WAV file reading and writing based on RIFF chunks."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

FORMAT_PCM = 1
FORMAT_FLOAT = 3
FORMAT_EXTENSIBLE = 0xFFFE


class WavError(Exception):
    pass


@dataclass
class WavInfo:
    format_tag: int
    channels: int
    sample_rate: int
    bits: int
    frames: int
    data_offset: int
    data_size: int
    cues: list[int] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.frames / self.sample_rate if self.sample_rate else 0.0

    @property
    def is_float(self) -> bool:
        return self.format_tag == FORMAT_FLOAT

    def describe(self) -> str:
        kind = "float" if self.is_float else "PCM"
        channels = {1: "mono", 2: "stereo"}.get(self.channels, f"{self.channels} ch")
        return f"{kind} {self.bits} bit, {self.sample_rate / 1000:g} kHz, {channels}"


def read_info(path: Path) -> WavInfo:
    """Parse the RIFF structure of a WAV file without loading the audio data."""
    with open(path, "rb") as fh:
        header = fh.read(12)
        if len(header) < 12 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise WavError(f"not a RIFF/WAVE file: {path}")

        fmt = None
        data_offset = data_size = None
        cues: list[int] = []

        while True:
            chunk_header = fh.read(8)
            if len(chunk_header) < 8:
                break
            chunk_id, size = struct.unpack("<4sI", chunk_header)
            start = fh.tell()

            if chunk_id == b"fmt ":
                fmt = fh.read(size)
            elif chunk_id == b"data":
                data_offset = start
                data_size = size
            elif chunk_id == b"cue ":
                body = fh.read(size)
                if len(body) >= 4:
                    count = struct.unpack_from("<I", body, 0)[0]
                    for i in range(count):
                        offset = 4 + i * 24
                        if offset + 24 > len(body):
                            break
                        cues.append(struct.unpack_from("<I", body, offset + 20)[0])

            # Chunks are word aligned
            fh.seek(start + size + (size & 1))

    if fmt is None or len(fmt) < 16:
        raise WavError(f"missing fmt chunk: {path}")
    if data_offset is None:
        raise WavError(f"missing data chunk: {path}")

    format_tag, channels, sample_rate, _, block_align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if format_tag == FORMAT_EXTENSIBLE and len(fmt) >= 26:
        # The first two bytes of the sub format GUID hold the actual format tag
        format_tag = struct.unpack_from("<H", fmt, 24)[0]

    if block_align == 0:
        raise WavError(f"invalid block alignment: {path}")

    file_size = path.stat().st_size
    data_size = min(data_size, max(0, file_size - data_offset))
    frames = data_size // block_align

    return WavInfo(
        format_tag=format_tag,
        channels=channels,
        sample_rate=sample_rate,
        bits=bits,
        frames=frames,
        data_offset=data_offset,
        data_size=data_size,
        cues=sorted(cues),
    )


def read_audio(path: Path, info: WavInfo | None = None) -> tuple[np.ndarray, int]:
    """Return audio as float32 array with shape (frames, channels) and the sample rate."""
    info = info or read_info(path)
    with open(path, "rb") as fh:
        fh.seek(info.data_offset)
        raw = fh.read(info.frames * info.channels * (info.bits // 8))

    ch = info.channels
    if info.format_tag == FORMAT_FLOAT:
        dtype = {32: "<f4", 64: "<f8"}.get(info.bits)
        if dtype is None:
            raise WavError(f"unsupported float width {info.bits}")
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
    elif info.format_tag == FORMAT_PCM:
        if info.bits == 8:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif info.bits == 16:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif info.bits == 24:
            b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
            ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
            data = ints.astype(np.float32) / 8388608.0
        elif info.bits == 32:
            data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        else:
            raise WavError(f"unsupported PCM width {info.bits}")
    else:
        raise WavError(f"unsupported format tag {info.format_tag}")

    usable = (len(data) // ch) * ch
    return data[:usable].reshape(-1, ch), info.sample_rate


def resample(data: np.ndarray, rate_from: int, rate_to: int) -> np.ndarray:
    """Linear interpolation resampling, sufficient for preview files."""
    if rate_from == rate_to or len(data) == 0:
        return data
    n_out = round(len(data) * rate_to / rate_from)
    x_old = np.arange(len(data), dtype=np.float64)
    x_new = np.linspace(0, len(data) - 1, n_out)
    return np.stack([np.interp(x_new, x_old, data[:, c]) for c in range(data.shape[1])], axis=1).astype(np.float32)


def to_stereo(data: np.ndarray) -> np.ndarray:
    if data.shape[1] == 2:
        return data
    if data.shape[1] == 1:
        return np.repeat(data, 2, axis=1)
    return data[:, :2]


def write_pcm24(path: Path, data: np.ndarray, sample_rate: int) -> None:
    """Write float audio with shape (frames, channels) as 24 bit PCM WAV."""
    channels = data.shape[1]
    ints = np.clip(np.round(data * 8388607.0), -8388608, 8388607).astype(np.int32).reshape(-1)
    raw = np.empty((len(ints), 3), dtype=np.uint8)
    raw[:, 0] = ints & 0xFF
    raw[:, 1] = (ints >> 8) & 0xFF
    raw[:, 2] = (ints >> 16) & 0xFF
    payload = raw.tobytes()

    block_align = channels * 3
    fmt = struct.pack("<HHIIHH", FORMAT_PCM, channels, sample_rate, sample_rate * block_align, block_align, 24)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(payload)) + payload
    if len(payload) & 1:
        body += b"\x00"

    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", len(body)) + body)
