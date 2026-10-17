"""Applies a Journal Profile's *formatting* to an uploaded manuscript.

Only formatting properties are touched: page size and margins, line numbering,
font family and size, line spacing. Text, tracked changes, comments, citation
fields, images and section order are never modified. The result is verified with
content_guard; if anything other than formatting changed, no file is produced.

Requirements that would need text changes (missing sections, abstract too long,
reference style, keyword count …) are reported in a compliance report instead.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import content_guard
from .ooxml import PPR_ORDER, RPR_ORDER, SECTPR_ORDER, DocxPackage, get_or_add, get_or_add_first, w
from .profile import Profile
from .textmodel import DocView, Para

PAGE_TWIPS = {"A4": (11906, 16838), "Letter": (12240, 15840)}


@dataclass
class FormatOptions:
    page: bool = True
    margins: bool = True
    line_numbers: bool = True
    font: bool = True
    font_size: bool = True
    line_spacing: bool = True
    tables_font: bool = True       # font family inside tables
    tables_size_spacing: bool = False  # tables are usually allowed to stay compact


@dataclass
class Finding:
    level: str  # ok | warn | fail | info
    item: str
    detail: str


@dataclass
class FormatResult:
    data: bytes | None
    applied: list[str] = field(default_factory=list)
    guard: content_guard.GuardResult | None = None
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _twips_from_cm(cm: float) -> int:
    return round(cm / 2.54 * 1440)


def _set_run_font(rpr, font: str | None, half_points: int | None) -> None:
    if font:
        rfonts = get_or_add(rpr, "rFonts", RPR_ORDER)
        for attr in ("asciiTheme", "hAnsiTheme", "cstheme"):
            rfonts.attrib.pop(w(attr), None)
        rfonts.set(w("ascii"), font)
        rfonts.set(w("hAnsi"), font)
        rfonts.set(w("cs"), font)
        # w:eastAsia is left alone so Korean/CJK text keeps its own font
    if half_points:
        get_or_add(rpr, "sz", RPR_ORDER).set(w("val"), str(half_points))
        get_or_add(rpr, "szCs", RPR_ORDER).set(w("val"), str(half_points))


def _set_spacing(ppr, multiple: float) -> None:
    spacing = get_or_add(ppr, "spacing", PPR_ORDER)
    spacing.set(w("line"), str(round(240 * multiple)))
    spacing.set(w("lineRule"), "auto")


def _in_table(el) -> bool:
    return any(a.tag == w("tc") for a in el.iterancestors())


def apply_formatting(pkg: DocxPackage, profile: Profile, opt: FormatOptions) -> list[str]:
    applied = []
    doc = pkg.xml("word/document.xml")
    body = doc.find(w("body"))
    font = profile.get("text.font") if opt.font else None
    size = profile.get("text.size_pt") if opt.font_size else None
    half = round(size * 2) if size else None
    spacing = profile.get("text.line_spacing") if opt.line_spacing else None

    # --- sections: page size, margins, line numbering
    sect_prs = list(body.iter(w("sectPr")))
    size_name = profile.get("page.size")
    margin = profile.get("page.margin_cm")
    for sp in sect_prs:
        if opt.page and size_name in PAGE_TWIPS:
            pg = get_or_add(sp, "pgSz", SECTPR_ORDER)
            wd, ht = PAGE_TWIPS[size_name]
            if pg.get(w("orient")) == "landscape":
                wd, ht = ht, wd
            pg.set(w("w"), str(wd))
            pg.set(w("h"), str(ht))
        if opt.margins and margin:
            mar = get_or_add(sp, "pgMar", SECTPR_ORDER)
            tw = str(_twips_from_cm(margin))
            for side in ("top", "bottom", "left", "right"):
                mar.set(w(side), tw)
            for attr, default in (("header", "708"), ("footer", "708"), ("gutter", "0")):
                if mar.get(w(attr)) is None:
                    mar.set(w(attr), default)
        if opt.line_numbers and profile.get("text.line_numbers") is not None:
            existing = sp.find(w("lnNumType"))
            if profile.get("text.line_numbers"):
                el = existing if existing is not None else get_or_add(sp, "lnNumType", SECTPR_ORDER)
                el.set(w("countBy"), "1")
                el.set(w("restart"), "continuous")
            elif existing is not None:
                sp.remove(existing)
    if opt.page and size_name:
        applied.append(f"용지: {size_name} ({len(sect_prs)}개 구역)")
    if opt.margins and margin:
        applied.append(f"여백: 상하좌우 {margin} cm")
    if opt.line_numbers and profile.get("text.line_numbers") is not None:
        applied.append("줄 번호: " + ("연속 번호 켜기" if profile.get("text.line_numbers") else "끄기"))

    # --- styles and document defaults
    if "word/styles.xml" in pkg.files and (font or half or spacing):
        styles = pkg.xml("word/styles.xml")
        defaults = styles.find(w("docDefaults"))
        targets = []
        if defaults is not None:
            rpr_def = defaults.find(w("rPrDefault"))
            if rpr_def is not None:
                targets.append(get_or_add_first(rpr_def, "rPr"))
        for st in styles.iter(w("style")):
            if st.get(w("type")) in ("paragraph", "character") and st.find(w("rPr")) is not None:
                targets.append(st.find(w("rPr")))
        for rpr in targets:
            style = rpr.getparent()
            is_table_style = style.tag == w("style") and style.get(w("type")) == "table"
            if is_table_style:
                continue
            _set_run_font(rpr, font, None)
        for st in styles.iter(w("style")):
            name_el = st.find(w("name"))
            name = (name_el.get(w("val")) if name_el is not None else "").lower()
            if st.get(w("type")) == "paragraph" and (name == "normal" or name.startswith("heading")):
                rpr = st.find(w("rPr"))
                if rpr is None:
                    rpr = etree_sub(st, "rPr")
                _set_run_font(rpr, font, half)
                if spacing:
                    ppr = st.find(w("pPr"))
                    if ppr is None:
                        ppr = etree_sub(st, "pPr", before="rPr")
                    _set_spacing(ppr, spacing)

    # --- direct formatting in the body (runs and paragraph marks)
    n_runs = n_paras = 0
    for p in body.iter(w("p")):
        table = _in_table(p)
        if spacing and (not table or opt.tables_size_spacing):
            ppr = get_or_add_first(p, "pPr")
            _set_spacing(ppr, spacing)
            n_paras += 1
        f = font if (not table or opt.tables_font) else None
        hp = half if (not table or opt.tables_size_spacing) else None
        if not (f or hp):
            continue
        ppr = p.find(w("pPr"))
        if ppr is not None and ppr.find(w("rPr")) is not None:
            _set_run_font(ppr.find(w("rPr")), f, hp)
        for run in p.iter(w("r")):
            if next(run.iterancestors(w("p")), None) is not p:
                continue
            rpr = get_or_add_first(run, "rPr")
            _set_run_font(rpr, f, hp)
            n_runs += 1
    if font:
        applied.append(f"글꼴: {font} (영문·숫자; 한글 글꼴은 유지)" + ("" if opt.tables_font else ", 표 제외"))
    if half:
        applied.append(f"글자 크기: {size:g} pt" + ("" if opt.tables_size_spacing else " (표는 원래 크기 유지)"))
    if spacing:
        applied.append(f"줄 간격: {spacing:g}배 ({n_paras}개 문단" + ("" if opt.tables_size_spacing else ", 표 제외") + ")")
    return applied


def etree_sub(parent, local: str, before: str | None = None):
    from lxml import etree

    el = etree.Element(w(local))
    if before is not None and parent.find(w(before)) is not None:
        parent.find(w(before)).addprevious(el)
    else:
        parent.append(el)
    return el


# ---------------------------------------------------------------------------
# Compliance report (read-only)
# ---------------------------------------------------------------------------
ABBR_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*[A-Z0-9](?:[-/][A-Za-z0-9]*[A-Z0-9])*\b")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'’./][A-Za-z0-9]+)*")


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def _paras(view: DocView, section: str) -> list[Para]:
    return [p for p in view.by_section.get(section, []) if not p.is_heading and p.text.strip()]


def compliance(view: DocView, profile: Profile, pkg: DocxPackage) -> tuple[list[Finding], dict]:
    out: list[Finding] = []
    stats: dict = {}
    headings = [p for p in view.paras if p.is_heading]
    present = [p.section for p in headings]

    # Abstract
    abstract_paras = [p for p in _paras(view, "Abstract") if not re.match(r"\s*key ?words?", p.text, re.I)]
    abstract_text = "\n".join(p.text for p in abstract_paras)
    words = count_words(abstract_text)
    stats["초록 단어 수"] = words
    limit = profile.get("abstract.max_words")
    if limit and abstract_paras:
        out.append(Finding("ok" if words <= limit else "fail", "초록 길이",
                           f"{words}단어 / 제한 {limit}단어" + ("" if words <= limit else f" ({words - limit}단어 초과)")))
    heads = profile.get("abstract.headings")
    if heads and abstract_paras:
        labels = []
        for p in abstract_paras:
            m = re.match(r"\s*([A-Za-z][A-Za-z &/]{2,40}):", p.text)
            if m:
                labels.append(m.group(1).strip())
        missing = [h for h in heads if not any(re.fullmatch(rf"{h}", part.strip(), re.I)
                                               for l in labels for part in re.split(r"\band\b|/|&", l))]
        found = ", ".join(labels) or "없음"
        out.append(Finding("ok" if not missing else "warn", "초록 소제목",
                           f"규정: {' / '.join(heads)} · 원고: {found}" + (f" · 일치하지 않음: {', '.join(missing)}" if missing else "")))
    if profile.get("abstract.no_citations") and abstract_paras:
        cites = [s for p in abstract_paras for s in p.superscript_spans() if re.search(r"\d", s[2])]
        cites += [m.group(0) for m in re.finditer(r"\[\d+(?:[,–-]\d+)*\]", abstract_text)]
        if cites:
            out.append(Finding("fail", "초록 인용", f"초록에 인용으로 보이는 표시가 {len(cites)}개 있습니다 (규정: 인용 금지)."))
    if profile.get("abstract.avoid_abbreviations") and abstract_text:
        unlabeled = "\n".join(re.sub(r"^\s*[A-Za-z][A-Za-z &/]{2,40}:", "", p.text) for p in abstract_paras)
        abbrs = sorted(set(ABBR_RE.findall(unlabeled)) - {"II", "III", "IV"})
        if abbrs:
            out.append(Finding("warn", "초록 약어", f"{len(abbrs)}종: {', '.join(abbrs[:20])} (규정: 초록에서 약어 지양)"))

    # Keywords
    kw_para = next((p for p in view.paras if re.match(r"\s*key ?words?\s*:", p.text, re.I)), None)
    lo, hi = profile.get("keywords.min"), profile.get("keywords.max")
    if kw_para is not None:
        body = kw_para.text.split(":", 1)[1]
        items = [k.strip() for k in re.split(r"[;,]", body) if k.strip()]
        seps = set(re.findall(r"[;,]", body))
        stats["키워드 수"] = len(items)
        if lo or hi:
            ok = (not lo or len(items) >= lo) and (not hi or len(items) <= hi)
            out.append(Finding("ok" if ok else "fail", "키워드 개수", f"{len(items)}개 / 규정 {lo or 0}–{hi or '∞'}개"))
        if len(seps) > 1:
            out.append(Finding("warn", "키워드 구분자", "세미콜론(;)과 쉼표(,)가 섞여 있습니다."))
    elif lo or hi:
        out.append(Finding("fail", "키워드", "'Keywords:' 문단을 찾지 못했습니다."))

    # Title
    title_para = next((p for p in view.by_section.get("Title page", []) if re.match(r"\s*title\s*:", p.text, re.I)), None)
    if title_para is None:
        tp = [p for p in view.by_section.get("Title page", []) if not p.is_heading and p.text.strip()]
        title_para = tp[0] if tp else None
    if title_para is not None and profile.get("structure.title_no_abbreviations"):
        title = re.sub(r"^\s*title\s*:\s*", "", title_para.text, flags=re.I)
        abbrs = sorted(set(ABBR_RE.findall(title)))
        out.append(Finding("ok" if not abbrs else "fail", "제목 약어",
                           "약어 없음" if not abbrs else f"제목에 약어: {', '.join(abbrs)} (규정: 제목에 약어 금지)"))

    # Main text words and length
    main_secs = ["Introduction", "Methods", "Results", "Discussion", "Conclusions"]
    main_words = sum(count_words(p.text) for s in main_secs for p in _paras(view, s))
    ref_paras = _paras(view, "References")
    stats["본문 단어 수 (Introduction~Discussion)"] = main_words
    stats["참고문헌 수"] = len(ref_paras)
    max_words = profile.get("length.max_words")
    if max_words:
        out.append(Finding("ok" if main_words <= max_words else "fail", "본문 길이", f"{main_words}단어 / 제한 {max_words}단어"))
    pages = profile.get("length.pages")
    wpp = profile.get("length.words_per_page")
    if pages and wpp and re.match(r"\d+-\d+", str(pages)):
        lo_p, hi_p = (int(x) for x in str(pages).split("-"))
        total = main_words + sum(count_words(p.text) for p in ref_paras)
        est = total / wpp
        level = "ok" if lo_p <= est <= hi_p else "warn"
        out.append(Finding(level, "분량", f"본문+참고문헌 {total}단어 ≈ {est:.1f}쪽 (규정: 약 {pages}쪽, 쪽당 {wpp}단어 기준)"))
    if profile.get("structure.word_count_on_title_page"):
        has = re.search(r"word count", "\n".join(p.text for p in view.paras[:60]), re.I)
        out.append(Finding("ok" if has else "fail", "제목 페이지 단어 수",
                           ("'Word count' 항목 있음" if has else "제목 페이지에 총 단어 수 항목이 없습니다")
                           + f" · 계산값(초록 제외 본문): {main_words}단어"))

    # Required sections / statements
    checks = [
        ("statements.acknowledgments", "Acknowledgments", ["Acknowledgments"]),
        ("statements.conflict_of_interest", profile.get("statements.coi_heading") or "Conflict of interest", ["Statement of Interests"]),
        ("statements.funding", "Funding", ["Funding", "Statement of Interests"]),
        ("statements.data_availability", "Data availability statement", ["Data Availability"]),
        ("statements.ethics", "Ethics approval", ["Ethics"]),
        ("statements.authorship", profile.get("statements.authorship_heading") or "Author contributions", ["Authorship Statement"]),
    ]
    all_text = "\n".join(p.text for p in view.paras).lower()
    for key, label, secs in checks:
        if not profile.get(key):
            continue
        hit = any(s in present for s in secs)
        if not hit and key == "statements.ethics":
            hit = bool(re.search(r"ethics committee|institutional review board|irb", all_text))
        exact = True
        if key == "statements.conflict_of_interest" and profile.get("statements.coi_heading"):
            exact = any(re.search(re.escape(profile.get("statements.coi_heading")), p.text, re.I) for p in headings)
        if key == "statements.authorship" and profile.get("statements.authorship_heading"):
            exact = any(re.search(re.escape(profile.get("statements.authorship_heading")), p.text, re.I) for p in view.paras)
        if hit and exact:
            out.append(Finding("ok", label, "있음"))
        elif hit:
            out.append(Finding("warn", label, f"비슷한 섹션은 있으나 규정의 제목('{label}')과 다릅니다."))
        else:
            out.append(Finding("fail", label, "찾지 못했습니다."))
    if profile.get("statements.authorship_heading", "").lower().startswith("authorship statement"):
        if not re.search(r"guarantor", all_text):
            out.append(Finding("warn", "Guarantor of article", "Authorship Statement에 보증 저자(guarantor) 표기가 없습니다."))

    # Section order
    order = profile.get("structure.order") or []
    seen = [s for s in present if s in order]
    dedup = [s for i, s in enumerate(seen) if s not in seen[:i]]
    expected = [s for s in order if s in dedup]
    if dedup and dedup != expected:
        out.append(Finding("warn", "섹션 순서", f"원고: {' → '.join(dedup)}\n규정: {' → '.join(expected)}"))
    elif dedup:
        out.append(Finding("ok", "섹션 순서", "규정 순서와 일치"))
    missing_secs = [s for s in order if s not in present and s not in ("Keywords", "Appendices", "Conclusions", "Title page")]
    if missing_secs:
        out.append(Finding("warn", "없는 섹션", ", ".join(missing_secs)))

    # Figures embedded
    n_images = sum(1 for p in view.paras for pc in p.pieces if pc.text == "￼")
    stats["원고 내 그림 수"] = n_images
    if profile.get("figures.separate_files") and n_images:
        out.append(Finding("warn", "그림 별도 제출", f"원고에 그림 {n_images}개가 삽입되어 있습니다. 규정은 별도 파일 제출입니다 ('Figure 변환' 탭에서 원고의 그림을 추출할 수 있습니다)."))

    # Citations format
    cit = profile.get("refs.citation")
    body_paras = [p for s in main_secs for p in _paras(view, s)]
    sup = sum(1 for p in body_paras for s in p.superscript_spans() if re.fullmatch(r"[\d,–\-\s]+", s[2]))
    brackets = sum(len(re.findall(r"\[\d+(?:[,–-]\s?\d+)*\]", p.text)) for p in body_paras)
    if cit == "superscript numbers" and brackets:
        out.append(Finding("warn", "인용 형식", f"대괄호 숫자 인용 {brackets}개 (규정: 위첨자 번호). 위첨자 인용 {sup}개."))
    elif cit == "numbers in brackets" and sup:
        out.append(Finding("warn", "인용 형식", f"위첨자 인용 {sup}개 (규정: 대괄호 번호)."))
    elif cit and (sup or brackets):
        out.append(Finding("ok", "인용 형식", f"위첨자 {sup}개, 대괄호 {brackets}개"))

    # Table footnote symbols
    symbols = profile.get("tables.footnote_symbols")
    if symbols:
        bad = []
        for p in _paras(view, "Tables"):
            for start, end, text in p.superscript_spans():
                if start <= 1 and re.fullmatch(r"[0-9a-z]+", text.strip()):
                    bad.append(text.strip())
        if bad:
            out.append(Finding("warn", "표 각주 기호", f"숫자/문자 각주 표시 {len(bad)}개 ({', '.join(bad[:8])}). 규정: {' '.join(symbols)} 순서"))

    # Trade names
    if profile.get("style.generic_drug_names"):
        tm = sorted(set(m.group(0) for p in view.paras for m in re.finditer(r"\b[\w\-]+[®™]", p.text)))
        if tm:
            out.append(Finding("info", "상품명", f"{', '.join(tm)} — 규정: 일반명 사용, 상품명은 제조사와 함께 괄호 안에"))

    # Page numbers
    if profile.get("text.page_numbers"):
        has_page = any(b"PAGE" in pkg.files[n] for n in pkg.files if re.match(r"word/(header|footer)\d*\.xml", n))
        out.append(Finding("ok" if has_page else "warn", "페이지 번호",
                           "머리글/바닥글에 페이지 번호 있음" if has_page else "페이지 번호 필드가 없습니다 (Word: 삽입 › 페이지 번호)."))
    return out, stats


def format_manuscript(data: bytes, profile: Profile, opt: FormatOptions | None = None) -> FormatResult:
    opt = opt or FormatOptions()
    original = DocxPackage.from_bytes(data)
    before = content_guard.document_signature(original)
    view = DocView.load(original)
    findings, stats = compliance(view, profile, original)

    pkg = DocxPackage.from_bytes(data)
    applied = apply_formatting(pkg, profile, opt)
    out = pkg.to_bytes()

    check = DocxPackage.from_bytes(out)
    guard = content_guard.compare(before, content_guard.document_signature(check))
    return FormatResult(out if guard.ok else None, applied, guard, findings, stats)
