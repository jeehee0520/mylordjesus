"""Writes user-approved corrections into a copy of the manuscript as Word tracked changes.

Each correction becomes <w:del> (old text) + <w:ins> (new text) by the author
"Manuscript Assistant", so every change can be reviewed and accepted or rejected
in Word. Existing tracked changes, comments and citation fields are preserved.

Two automatic proofs run before any file is returned:
  1. rejecting all of our changes gives back exactly the original content;
  2. accepting all of our changes gives the original text with only the
     approved corrections applied.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree

from . import content_guard
from .ooxml import DocxPackage, w
from .proofreader import Issue
from .textmodel import DocView, build_paragraph, style_names

AUTHOR = "Manuscript Assistant"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"


@dataclass
class ApplyResult:
    ok: bool
    tracked: bytes | None = None
    clean: bytes | None = None
    applied: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)


class _Ids:
    def __init__(self, pkg: DocxPackage):
        top = 0
        for name in pkg.content_parts():
            for el in pkg.xml(name).iter():
                v = el.get(w("id")) if isinstance(el.tag, str) else None
                if v and v.lstrip("-").isdigit():
                    top = max(top, int(v))
        self.next = top + 1

    def take(self) -> str:
        self.next += 1
        return str(self.next - 1)


def _run_of(t):
    return t.getparent()


def _normalize_run(run) -> dict:
    """Split a run so each content child (w:t, w:tab, …) has its own run. Returns {old child: new run}."""
    rpr = run.find(w("rPr"))
    content = [c for c in run if c.tag != w("rPr")]
    if len(content) <= 1:
        return {c: run for c in content}
    parent = run.getparent()
    idx = parent.index(run)
    mapping = {}
    for i, child in enumerate(content):
        new = etree.Element(w("r"), attrib=dict(run.attrib))
        if rpr is not None:
            new.append(copy.deepcopy(rpr))
        new.append(child)
        parent.insert(idx + i, new)
        mapping[child] = new
    parent.remove(run)
    return mapping


def _split_run(run, offset: int):
    """Split a single-w:t run at `offset`; return (left_run, right_run)."""
    t = run.find(w("t"))
    text = t.text or ""
    if offset <= 0 or offset >= len(text):
        raise ValueError("split offset outside text")
    right = copy.deepcopy(run)
    t.text = text[:offset]
    right.find(w("t")).text = text[offset:]
    for el in (t, right.find(w("t"))):
        el.set(XML_SPACE, "preserve")
    run.addnext(right)
    return run, right


def _wrap(el, tag: str, ids: _Ids, date: str):
    wrapper = etree.Element(w(tag))
    wrapper.set(w("id"), ids.take())
    wrapper.set(w("author"), AUTHOR)
    wrapper.set(w("date"), date)
    el.addprevious(wrapper)
    wrapper.append(el)
    return wrapper


def _new_run(text: str, reference_run):
    run = etree.Element(w("r"))
    rpr = reference_run.find(w("rPr")) if reference_run is not None else None
    if rpr is not None:
        rpr = copy.deepcopy(rpr)
        for change in rpr.findall(w("rPrChange")):
            rpr.remove(change)
        run.append(rpr)
    t = etree.SubElement(run, w("t"))
    t.text = text
    t.set(XML_SPACE, "preserve")
    return run


def _place_after(anchor, new_el, ids: _Ids):
    """Insert new_el right after anchor at paragraph level, splitting a foreign <w:ins> if needed."""
    parent = anchor.getparent()
    if parent.tag == w("ins"):
        following = list(anchor.itersiblings())
        if following:
            tail = etree.Element(w("ins"), attrib=dict(parent.attrib))
            tail.set(w("id"), ids.take())
            for sib in following:
                tail.append(sib)
            parent.addnext(tail)
        parent.addnext(new_el)
    else:
        anchor.addnext(new_el)


def _place_before(anchor, new_el, ids: _Ids):
    parent = anchor.getparent()
    if parent.tag == w("ins"):
        preceding = list(anchor.itersiblings(preceding=True))
        if preceding:
            head = etree.Element(w("ins"), attrib=dict(parent.attrib))
            head.set(w("id"), ids.take())
            for sib in reversed(preceding):
                head.append(sib)
            parent.addprevious(head)
        parent.addprevious(new_el)
    else:
        anchor.addprevious(new_el)


def _apply_one(p_el, index: int, styles, issue: Issue, ids: _Ids, date: str) -> str | None:
    para = build_paragraph(index, p_el, styles)
    a, b = issue.start, issue.end
    if para.text[a:b] != issue.original:
        return "원고 내용이 점검 시점과 달라 적용하지 않았습니다."
    suggestion = issue.suggestion or ""
    if a == b:  # pure insertion
        anchor_pc = next((pc for pc in para.pieces if pc.start < a <= pc.end and pc.t is not None), None)
        before_pc = None if anchor_pc else next((pc for pc in para.pieces if pc.start == a and pc.t is not None), None)
        target_pc = anchor_pc or before_pc
        if target_pc is None or target_pc.locked:
            return "삽입 위치가 인용 필드/하이퍼링크 등 보호된 영역입니다."
        run = _normalize_run(_run_of(target_pc.t))[target_pc.t]
        if anchor_pc is not None:
            if a < anchor_pc.end:
                run, _ = _split_run(run, a - anchor_pc.start)
            ins = _wrap(_new_run(suggestion, run), "ins", ids, date)
            ins.getparent().remove(ins)
            _place_after(run, ins, ids)
        else:
            ins = _wrap(_new_run(suggestion, run), "ins", ids, date)
            ins.getparent().remove(ins)
            _place_before(run, ins, ids)
        return None

    pieces = para.pieces_in(a, b)
    if not pieces or any(pc.locked or pc.t is None for pc in pieces):
        return "수정 범위에 인용 필드/하이퍼링크/탭 등 보호된 요소가 있어 자동 수정하지 않았습니다."
    runs = []
    for pc in pieces:
        runs.append(_normalize_run(_run_of(pc.t))[pc.t])
    first, last = pieces[0], pieces[-1]
    # split the end first so the first piece's run reference stays valid
    if b < last.end:
        left, _ = _split_run(runs[-1], b - last.start)
        runs[-1] = left
    if a > first.start:
        _, right = _split_run(runs[0], a - first.start)
        runs[0] = right
    reference = runs[0]
    dels = []
    for run in runs:
        for t in run.findall(w("t")):
            t.tag = w("delText")
            t.set(XML_SPACE, "preserve")
        dels.append(_wrap(run, "del", ids, date))
    if suggestion:
        new = _new_run(suggestion, reference)
        ins = etree.Element(w("ins"))
        ins.set(w("id"), ids.take())
        ins.set(w("author"), AUTHOR)
        ins.set(w("date"), date)
        ins.append(new)
        _place_after(dels[-1], ins, ids)
    return None


def _ours(el) -> bool:
    return el.get(w("author")) == AUTHOR


def accept_ours(pkg: DocxPackage) -> None:
    root = pkg.xml("word/document.xml")
    for d in [el for el in root.iter(w("del")) if _ours(el)]:
        d.getparent().remove(d)
    for i in [el for el in root.iter(w("ins")) if _ours(el)]:
        parent = i.getparent()
        idx = parent.index(i)
        for child in list(i):
            parent.insert(idx, child)
            idx += 1
        parent.remove(i)


def reject_ours(pkg: DocxPackage) -> None:
    root = pkg.xml("word/document.xml")
    for i in [el for el in root.iter(w("ins")) if _ours(el)]:
        i.getparent().remove(i)
    for d in [el for el in root.iter(w("del")) if _ours(el)]:
        for t in d.iter(w("delText")):
            t.tag = w("t")
        parent = d.getparent()
        idx = parent.index(d)
        for child in list(d):
            parent.insert(idx, child)
            idx += 1
        parent.remove(d)


def apply_corrections(data: bytes, issues: list[Issue]) -> ApplyResult:
    original = DocxPackage.from_bytes(data)
    original_sig = content_guard.document_signature(original)
    original_view = DocView.load(original)

    pkg = DocxPackage.from_bytes(data)
    root = pkg.xml("word/document.xml")
    paragraphs = list(root.find(w("body")).iter(w("p")))
    styles = style_names(pkg)
    ids = _Ids(pkg)
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result = ApplyResult(ok=False)
    expected = {p.index: p.text for p in original_view.paras}
    by_para: dict[int, list[Issue]] = {}
    for issue in issues:
        if issue.suggestion is None:
            result.skipped.append((issue.id, "수정안이 없는 항목(보고 전용)입니다."))
            continue
        by_para.setdefault(issue.para, []).append(issue)
    for index, items in by_para.items():
        items.sort(key=lambda i: (i.start, i.end), reverse=True)
        floor = None
        for issue in items:
            if floor is not None and issue.end > floor:
                result.skipped.append((issue.id, "다른 선택 항목과 범위가 겹칩니다."))
                continue
            if index >= len(paragraphs):
                result.skipped.append((issue.id, "문단을 찾을 수 없습니다."))
                continue
            reason = _apply_one(paragraphs[index], index, styles, issue, ids, date)
            if reason:
                result.skipped.append((issue.id, reason))
                continue
            text = expected[index]
            expected[index] = text[:issue.start] + (issue.suggestion or "") + text[issue.end:]
            result.applied.append(issue.id)
            floor = issue.start

    tracked = pkg.to_bytes()

    # proof 1: rejecting our changes restores the original content exactly
    rejected = DocxPackage.from_bytes(tracked)
    reject_ours(rejected)
    guard = content_guard.compare(original_sig, content_guard.document_signature(DocxPackage.from_bytes(rejected.to_bytes())))
    if not guard.ok:
        result.checks.append("검증 실패: 변경 내용을 모두 거부했을 때 원본과 다릅니다. " + "; ".join(guard.details[:3]))
        return result
    result.checks.append("검증 1 통과: 변경 내용을 모두 '거부'하면 원본과 완전히 같습니다.")

    # proof 2: accepting our changes gives exactly the approved edits
    accepted = DocxPackage.from_bytes(tracked)
    accept_ours(accepted)
    clean = accepted.to_bytes()
    clean_view = DocView.load(DocxPackage.from_bytes(clean))
    mismatched = [p.index for p in clean_view.paras if expected.get(p.index) != p.text]
    if len(clean_view.paras) != len(original_view.paras) or mismatched:
        result.checks.append(f"검증 실패: 변경 내용을 모두 수락한 결과가 예상과 다릅니다 (문단 {mismatched[:5]}).")
        return result
    result.checks.append(f"검증 2 통과: 변경 내용을 모두 '수락'하면 승인한 {len(result.applied)}개 항목만 바뀝니다.")
    result.ok, result.tracked, result.clean = True, tracked, clean
    return result
