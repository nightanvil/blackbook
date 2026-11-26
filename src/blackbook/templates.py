"""patch.xml generation in the structure of the factory patches (session version 1)."""

from __future__ import annotations

from xml.sax.saxutils import quoteattr

XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'

# Pad order of the cells in factory one-shot patches (celldisppos)
ONESHOT_CELL_ORDER = [8, 0, 9, 1, 10, 2, 11, 3, 12, 4, 13, 5, 14, 6, 15, 7]

TRACK_PARAMS = {
    "samtrack": [
        ("selcellpos", "0"),
        ("celldisppos", "0"),
        ("cellname", "Track 1"),
        ("selseqpos", "0"),
        ("trkgain", "0"),
        ("trkpan", "0"),
        ("trkmute", "0"),
        ("trksolo", "0"),
        ("out3gain", "0"),
        ("fx1send", "0"),
        ("fx2send", "0"),
        ("midiinport", "0"),
        ("midiinchan", "0"),
        ("cc1inport", "0"),
        ("cc1inchan", "0"),
        ("cc2inport", "0"),
        ("midioutport", "0"),
        ("midioutchan", "0"),
        ("padrowoffset", "0"),
    ],
    "multisamtrack": [
        ("selcellpos", "0"),
        ("celldisppos", "0"),
        ("cellname", "Track 1"),
        ("selseqpos", "0"),
        ("trkgain", "0"),
        ("trkpan", "0"),
        ("trkmute", "0"),
        ("trksolo", "0"),
        ("out3gain", "0"),
        ("fx1send", "0"),
        ("fx2send", "0"),
        ("outputbus", "0"),
        ("midiinport", "0"),
        ("midiinchan", "0"),
        ("cc1inport", "0"),
        ("cc1inchan", "0"),
        ("cc2inport", "0"),
        ("midioutport", "0"),
        ("midioutchan", "0"),
        ("padrowoffset", "0"),
    ],
}

SAMINST_PARAMS = [
    ("gaindb", "0"),
    ("pitch", "0"),
    ("panpos", "0"),
    ("cellmode", "0"),
    ("samtrigtype", "0"),
    ("loopmodes", "0"),
    ("reverse", "0"),
    ("envattack", "0"),
    ("envdecay", "0"),
    ("envsus", "1000"),
    ("envrel", "200"),
    ("velamount", "0"),
    ("outputbus", "0"),
    ("polymode", "0"),
    ("chokegrp", "0"),
    ("dualfilcutoff", "0"),
    ("res", "500"),
    ("fx1send", "0"),
    ("fx2send", "0"),
    ("overdrive", "0"),
    ("multisammode", "0"),
    ("interpqual", "0"),
    ("loopfadeamt", "0"),
    ("lfowave", "0"),
    ("lforate", "100"),
    ("lfoamount", "1000"),
    ("lfokeytrig", "0"),
    ("lfobeatsync", "0"),
    ("lforatebeatsync", "0"),
    ("legatomode", "0"),
    ("celldisppos", "0"),
]

SAMASST_PARAMS = [
    ("filename", ""),
    ("rootnote", "0"),
    ("keyrangebottom", "0"),
    ("keyrangetop", "0"),
    ("velroot", "0"),
    ("velrangebottom", "0"),
    ("velrangetop", "0"),
    ("samstart", "0"),
    ("samlen", "0"),
    ("loopstart", "0"),
    ("loopend", "0"),
]

NOTESEQ_PARAMS = {
    "samtrack": [
        ("cellname", ""),
        ("notesteplen", "10"),
        ("notestepcount", "16"),
        ("seqstepmode", "1"),
        ("selcellpos", "0"),
        ("seqplayenable", "1"),
        ("quantsizeseq", "0"),
    ],
    "multisamtrack": [
        ("cellname", ""),
        ("notesteplen", "10"),
        ("seqstepmode", "1"),
        ("selcellpos", "0"),
        ("seqplayenable", "1"),
        ("quantsizeseq", "0"),
    ],
}


def params(defaults: list[tuple[str, str]], values: dict[str, object] | None = None) -> str:
    values = values or {}
    unknown = set(values) - {k for k, _ in defaults}
    if unknown:
        raise KeyError(f"unknown parameters: {sorted(unknown)}")
    attrs = " ".join(f"{k}={quoteattr(str(values.get(k, v)))}" for k, v in defaults)
    return f"<params {attrs}/>"


def samasst_cell(values: dict[str, object], indent: str = "            ") -> list[str]:
    return [
        f'{indent}<cell type="samasst">',
        f"{indent}    {params(SAMASST_PARAMS, values)}",
        f"{indent}    <slices/>",
        f"{indent}</cell>",
    ]


def saminst_cell(values: dict[str, object], indent: str = "            ") -> list[str]:
    return [
        f'{indent}<cell type="saminst">',
        f"{indent}    {params(SAMINST_PARAMS, values)}",
        f"{indent}</cell>",
    ]


def noteseq_cell(track_type: str, indent: str = "            ") -> list[str]:
    return [
        f'{indent}<cell type="noteseq">',
        f"{indent}    {params(NOTESEQ_PARAMS[track_type])}",
        f"{indent}    <sequence/>",
        f"{indent}</cell>",
    ]


def document(track_type: str, track_values: dict[str, object], cells: list[str]) -> str:
    lines = [
        "<document>",
        '    <session version="1">',
        f'        <track type="{track_type}">',
        f"            {params(TRACK_PARAMS[track_type], track_values)}",
        *cells,
        *noteseq_cell(track_type),
        "        </track>",
        "    </session>",
        "</document>",
    ]
    return XML_HEADER + "\n".join(lines) + "\n"


def oneshot_patch(track_values: dict[str, object], pads: dict[int, tuple[dict, dict]]) -> str:
    """pads maps celldisppos to (saminst values, samasst values)."""
    cells: list[str] = []
    for slot in ONESHOT_CELL_ORDER:
        inst, asst = pads.get(slot, ({}, {}))
        cells += saminst_cell({**inst, "celldisppos": slot})
        cells += samasst_cell(asst)
    return document("samtrack", track_values, cells)


def multisample_patch(track_values: dict[str, object], inst: dict[str, object], zones: list[dict]) -> str:
    cells = saminst_cell({"samtrigtype": 1, "multisammode": 1, **inst, "celldisppos": 0})
    for zone in zones:
        cells += samasst_cell(zone)
    return document("multisamtrack", track_values, cells)
