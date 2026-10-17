"""Low-level helpers for reading and writing WordprocessingML (.docx) parts."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W_NS, "r": R_NS, "m": M_NS}


def w(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def r(tag: str) -> str:
    return f"{{{R_NS}}}{tag}"


# Parts that carry manuscript content and must survive formatting untouched.
CONTENT_PART_PREFIXES = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
    "word/comments.xml",
    "word/header",
    "word/footer",
)


def is_content_part(name: str) -> bool:
    return name.endswith(".xml") and name.startswith(CONTENT_PART_PREFIXES)


@dataclass
class DocxPackage:
    """A .docx kept as raw zip members so untouched parts are written back byte-for-byte."""

    files: dict[str, bytes]
    order: list[str] = field(default_factory=list)
    _trees: dict[str, etree._Element] = field(default_factory=dict)

    @classmethod
    def from_bytes(cls, data: bytes) -> "DocxPackage":
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            order = zf.namelist()
            files = {n: zf.read(n) for n in order}
        if "word/document.xml" not in files:
            raise ValueError("Word 문서(.docx)가 아닙니다: word/document.xml 이 없습니다.")
        return cls(files=files, order=order)

    def xml(self, name: str) -> etree._Element:
        if name not in self._trees:
            parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
            self._trees[name] = etree.fromstring(self.files[name], parser)
        return self._trees[name]

    def mark_dirty(self, name: str) -> None:
        tree = self._trees[name]
        self.files[name] = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)

    def to_bytes(self) -> bytes:
        for name in list(self._trees):
            self.mark_dirty(name)
        buf = io.BytesIO()
        names = self.order + [n for n in self.files if n not in self.order]
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for n in names:
                if n in self.files:
                    zf.writestr(n, self.files[n])
        return buf.getvalue()

    def rels(self, part: str) -> dict[str, str]:
        """Relationship id -> target for a part (e.g. word/document.xml)."""
        folder, _, base = part.rpartition("/")
        rel_name = f"{folder}/_rels/{base}.rels"
        if rel_name not in self.files:
            return {}
        root = etree.fromstring(self.files[rel_name])
        out = {}
        for rel in root.findall(f"{{{REL_NS}}}Relationship"):
            target = rel.get("Target", "")
            if rel.get("TargetMode") != "External" and not target.startswith("/"):
                target = f"{folder}/{target}"
            out[rel.get("Id")] = target.lstrip("/")
        return out

    def content_parts(self) -> list[str]:
        return sorted(n for n in self.files if is_content_part(n))


# Schema-defined child order of w:sectPr, w:pPr and w:rPr. New children must be
# inserted in this order or Word reports the file as corrupt.
SECTPR_ORDER = [
    "headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz", "pgMar",
    "paperSrc", "pgBorders", "lnNumType", "pgNumType", "cols", "formProt", "vAlign", "noEndnote",
    "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid", "printerSettings", "sectPrChange",
]
PPR_ORDER = [
    "pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
    "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
    "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
    "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
    "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
    "sectPr", "pPrChange",
]
RPR_ORDER = [
    "rStyle", "rFonts", "b", "bCs", "i", "iCs", "caps", "smallCaps", "strike", "dstrike", "outline",
    "shadow", "emboss", "imprint", "noProof", "snapToGrid", "vanish", "webHidden", "color", "spacing",
    "w", "kern", "position", "sz", "szCs", "highlight", "u", "effect", "bdr", "shd", "fitText",
    "vertAlign", "rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath", "rPrChange",
]


def get_or_add(parent: etree._Element, local: str, order: list[str]) -> etree._Element:
    """Return child w:<local>, creating it at the schema-correct position."""
    existing = parent.find(w(local))
    if existing is not None:
        return existing
    child = etree.Element(w(local))
    idx = order.index(local)
    later = {w(t) for t in order[idx + 1:]}
    for i, c in enumerate(parent):
        if c.tag in later:
            parent.insert(i, child)
            return child
    parent.append(child)
    return child


def get_or_add_first(parent: etree._Element, local: str) -> etree._Element:
    """For w:pPr in w:p and w:rPr in w:r, which must be the first child."""
    existing = parent.find(w(local))
    if existing is not None:
        return existing
    child = etree.Element(w(local))
    parent.insert(0, child)
    return child
