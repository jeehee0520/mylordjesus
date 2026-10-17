"""Proves that a formatting pass did not change manuscript content.

A document's *content signature* is the ordered list of everything a reader or
reviewer could see or that carries meaning: text (with its tracked-change state),
field instructions (EndNote/Zotero citations), symbols, images, footnote and
comment anchors, hyperlinks, table structure and paragraph boundaries.
Formatting (fonts, sizes, spacing, margins, styles) is deliberately excluded.

Text is merged per paragraph, so splitting a run into two runs with identical
text does not change the signature.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .ooxml import M_NS, NS, R_NS, W_NS, DocxPackage, w

_REVISION_TAGS = {w("ins"): "ins", w("del"): "del", w("moveFrom"): "moveFrom", w("moveTo"): "moveTo"}
_TEXT_CHARS = {w("tab"): "\t", w("cr"): "\n", w("noBreakHyphen"): "‑", w("softHyphen"): "­"}


@dataclass
class GuardResult:
    ok: bool
    message: str
    details: list[str]


def _revision_state(el) -> tuple:
    state = []
    for anc in el.iterancestors():
        kind = _REVISION_TAGS.get(anc.tag)
        if kind:
            state.append((kind, anc.get(w("author"), ""), anc.get(w("date"), "")))
    return tuple(reversed(state))


def part_signature(pkg: DocxPackage, part: str) -> list[tuple]:
    root = pkg.xml(part)
    rels = pkg.rels(part)
    tokens: list[tuple] = []
    buf: list[str] = []
    buf_key: tuple | None = None

    def flush():
        nonlocal buf, buf_key
        if buf:
            tokens.append(("T", buf_key, "".join(buf)))
        buf, buf_key = [], None

    def add_text(kind: str, el, text: str):
        nonlocal buf_key
        key = (kind, _revision_state(el))
        if key != buf_key:
            flush()
            buf_key = key
        buf.append(text)

    def media_hash(rid: str) -> str:
        target = rels.get(rid, rid)
        data = pkg.files.get(target)
        return hashlib.sha256(data).hexdigest()[:16] if data is not None else f"ext:{target}"

    for el in root.iter():
        tag = el.tag
        if not isinstance(tag, str):
            continue
        if tag == w("t"):
            add_text("text", el, el.text or "")
        elif tag == w("delText"):
            add_text("text", el, el.text or "")
        elif tag == w("instrText"):
            add_text("instr", el, el.text or "")
        elif tag in _TEXT_CHARS:
            add_text("text", el, _TEXT_CHARS[tag])
        elif tag == w("br"):
            add_text("text", el, {"page": "\f", "column": "\v"}.get(el.get(w("type")), "\n"))
        elif tag == f"{{{M_NS}}}t":
            add_text("math", el, el.text or "")
        else:
            token = None
            if tag == w("p"):
                token = ("P",)
            elif tag == w("tbl"):
                token = ("TBL",)
            elif tag == w("tr"):
                token = ("TR",)
            elif tag == w("tc"):
                token = ("TC",)
            elif tag == w("sym"):
                token = ("SYM", el.get(w("font")), el.get(w("char")))
            elif tag == w("fldChar"):
                token = ("FLD", el.get(w("fldCharType")))
            elif tag == w("fldSimple"):
                token = ("FLDS", el.get(w("instr")))
            elif tag in (w("footnoteReference"), w("endnoteReference")):
                token = ("NOTE", tag.split("}")[1], el.get(w("id")))
            elif tag in (w("commentRangeStart"), w("commentRangeEnd"), w("commentReference")):
                token = ("CMT", tag.split("}")[1], el.get(w("id")))
            elif tag == w("hyperlink"):
                rid = el.get(f"{{{R_NS}}}id")
                token = ("LINK", rels.get(rid, rid) if rid else None, el.get(w("anchor")))
            elif tag in (w("drawing"), w("pict"), w("object")):
                ids = [v for e in el.iter() for k, v in e.attrib.items()
                       if k in (f"{{{R_NS}}}embed", f"{{{R_NS}}}id", f"{{{R_NS}}}link")]
                token = ("IMG", tuple(media_hash(i) for i in ids))
            if token is not None:
                flush()
                tokens.append(token)
    flush()
    return tokens


def document_signature(pkg: DocxPackage) -> dict[str, list[tuple]]:
    sig = {part: part_signature(pkg, part) for part in pkg.content_parts()}
    media = {n: hashlib.sha256(d).hexdigest() for n, d in pkg.files.items() if n.startswith("word/media/")}
    sig["__media__"] = sorted(media.items())
    return sig


def _describe(tok: tuple | None) -> str:
    if tok is None:
        return "(없음)"
    if tok[0] == "T":
        text = tok[2]
        return f"텍스트 '{text[:80]}{'…' if len(text) > 80 else ''}'"
    return " ".join(str(t) for t in tok)


def compare(before: dict, after: dict, allowed_new_parts: set[str] | None = None) -> GuardResult:
    allowed_new_parts = allowed_new_parts or set()
    details = []
    for part, toks in before.items():
        if part not in after:
            details.append(f"{part}: 부분이 사라졌습니다.")
            continue
        other = after[part]
        if toks != other:
            for i, (a, b) in enumerate(zip(toks, other)):
                if a != b:
                    details.append(f"{part} #{i}: 변경 전 {_describe(a)} → 변경 후 {_describe(b)}")
                    break
            else:
                details.append(f"{part}: 길이 다름 ({len(toks)} → {len(other)})")
    for part in after:
        if part not in before and part not in allowed_new_parts:
            details.append(f"{part}: 허용되지 않은 새 부분이 추가되었습니다.")
    if details:
        return GuardResult(False, "내용이 변경되었습니다. 결과 파일을 저장하지 않았습니다.", details)
    return GuardResult(True, "내용 불변 검증 통과: 텍스트·변경 추적·인용 필드·그림·각주·메모가 원본과 동일합니다.", [])


def visible_text(pkg: DocxPackage, part: str = "word/document.xml") -> list[str]:
    """Paragraph texts as they would read with every tracked change accepted."""
    root = pkg.xml(part)
    out = []
    for p in root.iter(w("p")):
        chunks = []
        for el in p.iter(w("t"), w("tab"), w("br")):
            if el.getparent() is not None and _inside_own_paragraph(el, p) and not _is_deleted(el):
                chunks.append(el.text or "" if el.tag == w("t") else ("\t" if el.tag == w("tab") else "\n"))
        out.append("".join(chunks))
    return out


def _inside_own_paragraph(el, p) -> bool:
    for anc in el.iterancestors(w("p")):
        return anc is p
    return False


def _is_deleted(el) -> bool:
    return any(a.tag in (w("del"), w("moveFrom")) for a in el.iterancestors())


__all__ = ["GuardResult", "document_signature", "compare", "visible_text", "NS", "W_NS"]
