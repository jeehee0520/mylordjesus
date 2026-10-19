"""Re-labels table footnote markers with the journal's symbols, in the journal's order.

Example (AP&T): general footnotes use † ‡ § ¶ in that order and *, **, *** are reserved for
P values. A table whose notes are marked 1, 2 becomes †, ‡; a table that used * for a general
note and † for a P value gets the two swapped.

Only markers that are *defined* by a footnote under the table are touched: a superscript
in a cell is changed only if a note below the table starts with the same marker. The changes
are proposals (Issue objects) that track_changes.apply_corrections writes as Word tracked
changes, so nothing is altered without review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .profile import Profile
from .proofreader import HIGH, Issue, finalize
from .textmodel import DocView, Para

SYMBOL_CHARS = "*†‡§¶‖#"
P_VALUE = re.compile(r"\bP[\s-]?values?\b|\bp\s*[<≤=>]|\bP\s*[<≤=>]|\bsignifican", re.I)
CAPTION = re.compile(r"^\s*Table\s+(\d+)\b", re.I)


@dataclass
class Footnote:
    marker: str
    kind: str  # "p" or "note"
    para: Para
    start: int
    end: int
    text: str


@dataclass
class TablePlan:
    number: str
    mapping: dict[str, str] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)
    occurrences: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _symbols(base: list[str], n: int) -> list[str]:
    """†, ‡, §, ¶, then ††, ‡‡, §§, ¶¶ … as AMA style continues the series."""
    out = []
    k = 1
    while len(out) < n:
        out += [s * k for s in base]
        k += 1
    return out[:n]


def _leading_marker(p: Para) -> tuple[str, int, int] | None:
    text = p.text
    lead = len(text) - len(text.lstrip())
    for s, e, t in p.superscript_spans():
        if s == lead and t.strip():
            core = t.strip().rstrip(",;.)")
            if core and len(core) <= 4:
                return core, s, s + len(core)
        if s > lead:
            break
    m = re.match(rf"[{re.escape(SYMBOL_CHARS)}]+", text[lead:])
    if m:
        return m.group(0), lead, lead + len(m.group(0))
    return None


def _blocks(view: DocView) -> list[tuple[str, list[Para]]]:
    """Caption paragraph 'Table N' … table cells … notes, until the next caption or heading."""
    blocks, current, number = [], None, None
    for p in view.paras:
        m = CAPTION.match(p.text) if not p.in_table else None
        if m:
            if current:
                blocks.append((number, current))
            current, number = [p], m.group(1)
            continue
        if current is None:
            continue
        if p.is_heading or (not p.in_table and re.match(r"^\s*(Figure|Fig\.)\s*\d+", p.text)):
            blocks.append((number, current))
            current = None
            continue
        current.append(p)
    if current:
        blocks.append((number, current))
    return blocks


def _occurrences(cells: list[Para], marker: str):
    """(para, start, end) of a marker inside table cells."""
    out = []
    is_symbol = all(c in SYMBOL_CHARS for c in marker)
    for p in cells:
        found = set()
        for s, e, t in p.superscript_spans():
            for m in re.finditer(r"[^,;\s]+", t):
                tok = m.group(0).strip("()")
                if tok == marker:
                    off = t.index(tok, m.start())
                    found.add((s + off, s + off + len(tok)))
        if is_symbol:
            ch = re.escape(marker[0])
            for m in re.finditer(rf"(?<!{ch}){re.escape(marker)}(?!{ch})", p.text):
                found.add((m.start(), m.end()))
        out += [(p, s, e) for s, e in sorted(found)]
    return out


def plan_table_footnotes(view: DocView, profile: Profile) -> tuple[list[Issue], list[TablePlan]]:
    note_symbols = profile.get("tables.footnote_symbols")
    p_symbols = profile.get("tables.p_value_symbols")
    if not note_symbols:
        return [], []
    issues: list[Issue] = []
    plans: list[TablePlan] = []
    for number, paras in _blocks(view):
        cells = [p for p in paras if p.in_table]
        notes_paras = [p for p in paras[1:] if not p.in_table]
        defs: list[Footnote] = []
        for p in notes_paras:
            lm = _leading_marker(p)
            if lm:
                marker, s, e = lm
                rest = p.text[e:]
                kind = "p" if p_symbols and P_VALUE.search(rest) else "note"
                defs.append(Footnote(marker, kind, p, s, e, rest.strip()))
        if not defs:
            continue
        plan = TablePlan(number)
        # order of first use in the table body, then notes that are never referenced
        first_use = []
        for d in defs:
            occ = _occurrences(cells, d.marker)
            pos = (occ[0][0].index, occ[0][1]) if occ else (10 ** 9, d.para.index)
            first_use.append((pos, d, occ))
            if not occ:
                plan.notes.append(f"각주 '{d.marker}'가 표 안에서 쓰이지 않습니다.")
        first_use.sort(key=lambda x: x[0])
        notes_in_order = [d for _, d, _ in first_use if d.kind == "note"]
        ps_in_order = [d for _, d, _ in first_use if d.kind == "p"]
        new_note = _symbols(note_symbols, len(notes_in_order))
        new_p = (p_symbols + [p_symbols[-1] + "*" * k for k in range(1, 10)])[:len(ps_in_order)] if p_symbols else []
        for d, sym in list(zip(notes_in_order, new_note)) + list(zip(ps_in_order, new_p)):
            plan.mapping[d.marker] = sym
            plan.kinds[d.marker] = "P값" if d.kind == "p" else "일반 각주"
        for _, d, occ in first_use:
            new = plan.mapping[d.marker]
            plan.occurrences[d.marker] = len(occ) + 1
            if new == d.marker:
                continue
            what = f"Table {number} 각주 기호 '{d.marker}' → '{new}' ({plan.kinds[d.marker]})"
            for p, s, e in [(d.para, d.start, d.end)] + occ:
                issues.append(Issue(p.index, s, e, p.text[s:e], new, "표 각주 기호", what, HIGH, p.section,
                                    _ctx(p, s, e), _editable(p, s, e)))
        plans.append(plan)
    return finalize(issues), plans


def _editable(p: Para, s: int, e: int) -> bool:
    pieces = p.pieces_in(s, e)
    return bool(pieces) and not any(pc.locked for pc in pieces)


def _ctx(p: Para, s: int, e: int, width: int = 40) -> str:
    a, b = max(0, s - width), min(len(p.text), e + width)
    return ("…" if a else "") + p.text[a:s] + "【" + p.text[s:e] + "】" + p.text[e:b] + ("…" if b < len(p.text) else "")
