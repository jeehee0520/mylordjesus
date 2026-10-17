"""Paragraph text model of document.xml with offsets mapped back to w:t elements.

The text of a paragraph is what a reader sees with all tracked changes accepted.
Each character maps to a Piece; a piece that may not be edited automatically
(field results such as EndNote citations, hyperlinks, tabs, images) is `locked`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .ooxml import DocxPackage, w

OBJ = "￼"  # stands in for an image so words on either side are not joined


@dataclass
class Piece:
    start: int
    end: int
    text: str
    t: object | None
    locked: bool
    superscript: bool = False
    bold: bool = False
    field: bool = False  # inside a field result (e.g. an EndNote citation)


@dataclass
class Para:
    index: int
    element: object
    text: str
    pieces: list[Piece]
    style: str
    in_table: bool
    section: str = ""
    is_heading: bool = False

    def pieces_in(self, start: int, end: int) -> list[Piece]:
        return [p for p in self.pieces if p.end > start and p.start < end]

    def superscript_spans(self) -> list[tuple[int, int, str]]:
        spans, cur = [], None
        for p in self.pieces:
            if p.superscript and p.text:
                if cur and cur[1] == p.start:
                    cur = (cur[0], p.end, cur[2] + p.text)
                else:
                    if cur:
                        spans.append(cur)
                    cur = (p.start, p.end, p.text)
            elif cur:
                spans.append(cur)
                cur = None
        if cur:
            spans.append(cur)
        return spans


def style_names(pkg: DocxPackage) -> dict[str, str]:
    if "word/styles.xml" not in pkg.files:
        return {}
    root = pkg.xml("word/styles.xml")
    out = {}
    for st in root.iter(w("style")):
        name = st.find(w("name"))
        out[st.get(w("styleId"))] = name.get(w("val")) if name is not None else st.get(w("styleId"))
    return out


def _flag(rpr, tag: str) -> bool:
    if rpr is None:
        return False
    el = rpr.find(w(tag))
    if el is None:
        return False
    return el.get(w("val"), "true") not in ("0", "false", "off")


def _run_props(run):
    rpr = run.find(w("rPr")) if run is not None else None
    sup = False
    if rpr is not None:
        va = rpr.find(w("vertAlign"))
        sup = va is not None and va.get(w("val")) == "superscript"
    return sup, _flag(rpr, "b")


def _editable_run(run, p) -> bool:
    parent = run.getparent()
    if parent is p:
        return True
    return parent is not None and parent.tag == w("ins") and parent.getparent() is p


def build_paragraph(index: int, p, styles: dict[str, str]) -> Para:
    pieces: list[Piece] = []
    pos = 0
    field_stack: list[str] = []  # "instr" or "result"

    def add(text, t, locked, run, in_field):
        nonlocal pos
        sup, bold = _run_props(run)
        pieces.append(Piece(pos, pos + len(text), text, t, locked, sup, bold, in_field))
        pos += len(text)

    for el in p.iter():
        if el is p or not isinstance(el.tag, str):
            continue
        # skip content of nested paragraphs (text boxes); they are their own Para
        owner = next(el.iterancestors(w("p")), None)
        if owner is not p:
            continue
        tag = el.tag
        if tag == w("fldChar"):
            kind = el.get(w("fldCharType"))
            if kind == "begin":
                field_stack.append("instr")
            elif kind == "separate" and field_stack:
                field_stack[-1] = "result"
            elif kind == "end" and field_stack:
                field_stack.pop()
            continue
        deleted = any(a.tag in (w("del"), w("moveFrom")) for a in el.iterancestors())
        if deleted:
            continue
        run = next(el.iterancestors(w("r")), None)
        in_field = bool(field_stack) or any(a.tag == w("fldSimple") for a in el.iterancestors())
        if field_stack and field_stack[-1] == "instr":
            continue
        if tag == w("t"):
            locked = in_field or run is None or not _editable_run(run, p)
            add(el.text or "", el, locked, run, in_field)
        elif tag == w("tab"):
            if el.getparent() is not None and el.getparent().tag == w("tabs"):
                continue
            add("\t", None, True, run, in_field)
        elif tag in (w("br"), w("cr")):
            add("\n", None, True, run, in_field)
        elif tag == w("noBreakHyphen"):
            add("‑", None, True, run, in_field)
        elif tag in (w("drawing"), w("pict"), w("object")):
            add(OBJ, None, True, run, in_field)

    text = "".join(pc.text for pc in pieces)
    ppr = p.find(w("pPr"))
    style_id = None
    if ppr is not None and ppr.find(w("pStyle")) is not None:
        style_id = ppr.find(w("pStyle")).get(w("val"))
    style = styles.get(style_id, style_id or "Normal")
    in_table = any(a.tag == w("tc") for a in p.iterancestors())
    return Para(index, p, text, pieces, style, in_table)


def body_paragraphs(pkg: DocxPackage) -> list[Para]:
    root = pkg.xml("word/document.xml")
    body = root.find(w("body"))
    styles = style_names(pkg)
    paras = [build_paragraph(i, p, styles) for i, p in enumerate(body.iter(w("p")))]
    assign_sections(paras)
    return paras


_HEADING_STYLE = re.compile(r"^(heading|title|제목)", re.I)


def looks_like_heading(p: Para) -> bool:
    if _HEADING_STYLE.match(p.style or ""):
        return bool(p.text.strip())
    text = p.text.strip()
    if not text or p.in_table or len(text) > 80 or len(text.split()) > 8:
        return False
    if text.endswith((".", ",", ";")):
        return False
    visible = [pc for pc in p.pieces if pc.text.strip()]
    return bool(visible) and all(pc.bold for pc in visible)


def assign_sections(paras: list[Para]) -> None:
    """Canonical headings (Abstract, Methods …) start a section; other subheadings stay inside it."""
    current = ""
    for p in paras:
        if looks_like_heading(p):
            p.is_heading = True
            canon = canonical_section(p.text)
            top_level = re.match(r"^(heading 1|title)$", p.style or "", re.I) is not None
            if canon:
                current = canon
            elif top_level or not current:
                current = p.text.strip()
        p.section = current


SECTION_ALIASES = [
    ("Title page", r"title page|^title$"),
    ("Abstract", r"^(structured )?abstract|^summary$"),
    ("Keywords", r"^key ?words"),
    ("Abbreviations", r"^abbreviations"),
    ("Introduction", r"^(\d+\.?\s*)?introduction|^background$"),
    ("Methods", r"^(\d+\.?\s*)?(materials? and methods|methods|patients and methods|methodology)"),
    ("Results", r"^(\d+\.?\s*)?results"),
    ("Discussion", r"^(\d+\.?\s*)?discussion"),
    ("Conclusions", r"^(\d+\.?\s*)?conclusions?$"),
    ("Acknowledgments", r"^acknowledge?ments?"),
    ("Statement of Interests", r"statement of interests?|conflicts? of interests?|competing interests?|declaration of interests?"),
    ("Authorship Statement", r"authorship statement|author contributions?"),
    ("Funding", r"^funding|financial support"),
    ("Data Availability", r"data (availability|sharing|accessibility)"),
    ("Ethics", r"ethic|institutional review board|irb"),
    ("References", r"^references?$|^bibliography|^literature cited"),
    ("Tables", r"^tables?$"),
    ("Figure legends", r"^figure legends?|^figures?$|^legends? (to|for) figures?"),
    ("Appendices", r"^appendi(x|ces)"),
    ("Supporting Information", r"supporting information|supplementary"),
]


def canonical_section(text: str) -> str:
    t = text.strip().lower().rstrip(":")
    for name, pat in SECTION_ALIASES:
        if re.search(pat, t):
            return name
    return ""


@dataclass
class DocView:
    paras: list[Para]
    by_section: dict[str, list[Para]] = field(default_factory=dict)

    @classmethod
    def load(cls, pkg: DocxPackage) -> "DocView":
        paras = body_paragraphs(pkg)
        by = {}
        for p in paras:
            by.setdefault(p.section, []).append(p)
        return cls(paras, by)

    def section_text(self, name: str) -> str:
        return "\n".join(p.text for p in self.by_section.get(name, []) if not p.is_heading)
