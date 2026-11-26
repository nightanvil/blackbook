"""Per-pad parameters of one-shot patches: XML name, range and display.

XML values are integers. Numeric parameters are shown as xml / scale in the given unit. Ranges follow
the device manual (blackbox 2 firmware 1.1, one-shot track). Parameters marked unverified have choice
values whose XML encoding is assumed from the order in the manual and not yet confirmed on the device.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .templates import SAMINST_PARAMS

LFO_SHAPES = ["Rev Saw", "Saw", "Triangle", "Pos Tri", "Sine", "Pos Sine", "Square", "Pos Square", "Random"]
LFO_SYNC_RATES = [
    "8 bars", "4 bars", "2 bars", "1 bar", "1/2", "1/2T", "1/4", "1/4T",
    "1/8", "1/8T", "1/16", "1/16T", "1/32", "1/32T", "1/64",
]


@dataclass
class Param:
    key: str
    label: str
    group: str
    kind: str  # number, choice, toggle
    min: float = 0
    max: float = 100
    scale: float = 10
    step: float = 0.1
    unit: str = "%"
    options: list[str] = field(default_factory=list)
    verified: bool = True
    # Shown only when another parameter has a given XML value: (key, value)
    when: tuple[str, int] | None = None

    def xml_range(self) -> tuple[int, int]:
        if self.kind == "toggle":
            return 0, 1
        if self.kind == "choice":
            return 0, len(self.options) - 1
        return round(self.min * self.scale), round(self.max * self.scale)


PARAMS: list[Param] = [
    Param("gaindb", "Level", "Sound", "number", -96, 12, 1000, 0.1, "dB"),
    Param("pitch", "Pitch", "Sound", "number", -24, 24, 1000, 0.01, "st"),
    Param("dualfilcutoff", "Filter", "Sound", "number", -100, 100),
    Param("res", "Res", "Sound", "number"),
    Param("panpos", "Pan", "Sound", "number", -100, 100, unit="% L/R"),
    Param("overdrive", "Overdrive", "Sound", "number"),
    Param("fx1send", "Delay", "Sound", "number", verified=False),
    Param("fx2send", "Reverb", "Sound", "number", verified=False),
    Param("reverse", "Reverse", "Setup", "toggle"),
    Param("samtrigtype", "Launch", "Setup", "choice", options=["Trigger", "Gate", "Toggle"], verified=False),
    Param(
        "polymode", "Poly", "Setup", "choice",
        options=["Mono", "Poly 2", "Poly 4", "Poly 6", "Poly 8", "Poly X"], verified=False,
    ),
    Param("chokegrp", "Choke Grp", "Setup", "choice", options=["None", "A", "B", "C", "D"], verified=False),
    Param("interpqual", "Interp", "Setup", "choice", options=["Normal", "HighQ"], verified=False),
    Param("envattack", "Attack", "Env/LFO", "number"),
    Param("envdecay", "Decay", "Env/LFO", "number"),
    Param("envsus", "Sustain", "Env/LFO", "number"),
    Param("envrel", "Release", "Env/LFO", "number"),
    Param("velamount", "Velocity", "Env/LFO", "number"),
    Param("lfowave", "LFO Shape", "Env/LFO", "choice", options=LFO_SHAPES, verified=False),
    Param("lfoamount", "LFO Depth", "Env/LFO", "number"),
    Param("lfobeatsync", "Beat Sync", "Env/LFO", "toggle", verified=False),
    Param("lforate", "LFO Rate", "Env/LFO", "number", when=("lfobeatsync", 0)),
    Param(
        "lforatebeatsync", "LFO Rate", "Env/LFO", "choice",
        options=LFO_SYNC_RATES, verified=False, when=("lfobeatsync", 1),
    ),
    Param("lfokeytrig", "Restart", "Env/LFO", "toggle", verified=False),
]

BY_KEY = {p.key: p for p in PARAMS}
DEFAULTS = {key: int(value) for key, value in SAMINST_PARAMS if key in BY_KEY}


def describe() -> list[dict]:
    """Parameter table for the frontend, with the XML default of a new pad."""
    return [asdict(p) | {"default": DEFAULTS.get(p.key, 0)} for p in PARAMS]


def validate(values: dict[str, int], label: str) -> list[str]:
    errors = []
    for key, value in values.items():
        param = BY_KEY.get(key)
        if param is None:
            errors.append(f"{label}: unknown parameter {key}")
            continue
        low, high = param.xml_range()
        if not low <= value <= high:
            errors.append(f"{label}: {param.label} out of range ({value}, allowed {low} to {high})")
    return errors


def read(attrs: dict[str, str]) -> dict[str, int]:
    """Known parameters of a saminst cell; values that are not integers are left out."""
    result = {}
    for key in BY_KEY:
        try:
            result[key] = int(attrs[key])
        except (KeyError, ValueError):
            continue
    return result
