"""투고 양식 도우미 — Streamlit UI.

Run:  streamlit run app.py
All processing happens on this machine. No manuscript text is sent to any external API.
"""
from __future__ import annotations

import io
import os
import re
import threading
import zipfile

import pandas as pd
import streamlit as st

from core import guideline_loader
from core.figure_processor import FigureOptions, images_from_docx, parse_pages, process
from core.manuscript_formatter import FormatOptions, format_manuscript
from core.profile import CATEGORIES, FIELDS, NOT_SPECIFIED, SPEC, STATUS_LABEL, Profile, format_value, parse_value
from core.profile_extractor import extract_profile
from core.proofreader import HIGH, LOW, MEDIUM, ProofOptions, overlapping, proofread
from core.template_builder import build_checklist, build_template, checklist_rows
from core.table_footnotes import plan_table_footnotes
from core.textmodel import DocView
from core.ooxml import DocxPackage
from core.track_changes import apply_corrections

st.set_page_config(page_title="투고 양식 도우미", page_icon="📄", layout="wide")

STATUS_ICON = {"found": "🟢", "user": "🔵", "default": "🟡", "not_specified": "⚪"}
LEVEL_ICON = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}

ss = st.session_state
ss.setdefault("profile", None)
ss.setdefault("manuscript", None)  # (name, bytes)
ss.setdefault("issues", None)
ss.setdefault("editor_version", 0)


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\-]+", "_", text).strip("_")[:60] or "journal"


def stem(name: str) -> str:
    return re.sub(r"\.[^.]+$", "", name)


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("📄 투고 양식 도우미")
    st.caption("투고 규정 → 원고 템플릿 · Figure 변환 · 원고 서식 변환 · 오류 점검")
    st.info("🔒 모든 처리는 이 컴퓨터(서버) 안에서만 이루어집니다. 원고와 규정은 외부 API로 전송되지 않습니다.")
    profile: Profile | None = ss.profile
    if profile:
        st.subheader(profile.name)
        counts = {k: sum(1 for r in profile.rules.values() if r.status == k) for k in STATUS_ICON}
        st.write(" · ".join(f"{STATUS_ICON[k]} {STATUS_LABEL[k]} {v}" for k, v in counts.items()))
        st.write("✔️ 규정 확정됨" if profile.confirmed else "⏳ 규정 확인 후 ①에서 '확정'을 눌러 주세요")
        st.download_button("규정 프로필 저장 (.json)", profile.to_json().encode("utf-8"),
                           file_name=f"{safe_name(profile.name)}_profile.json", mime="application/json")
    if ss.manuscript:
        st.caption(f"현재 원고: {ss.manuscript[0]}")
    st.divider()
    st.caption("상태 표시: 🟢 규정 근거 있음 · 🔵 사용자 지정 · 🟡 규정에 없음(기본값) · ⚪ 적용 안 함")
    if os.environ.get("MA_DESKTOP"):
        st.divider()
        if st.button("⏻ 프로그램 종료", width="stretch"):
            st.success("프로그램을 종료했습니다. 이 탭을 닫아도 됩니다.")
            threading.Timer(0.5, os._exit, args=(0,)).start()


def require_profile(confirmed: bool = True) -> Profile | None:
    profile = ss.profile
    if profile is None:
        st.warning("먼저 ① 투고 규정 탭에서 규정을 분석하거나 저장된 프로필을 불러오세요.")
        return None
    if confirmed and not profile.confirmed:
        st.warning("① 투고 규정 탭에서 추출된 규정을 확인한 뒤 '확정'을 눌러 주세요.")
        return None
    return profile


def manuscript_input(key: str):
    up = st.file_uploader("원고 업로드 (.docx)", type=["docx"], key=f"ms_{key}")
    if up is not None and (ss.manuscript is None or ss.manuscript[0] != up.name or ss.manuscript[1] != up.getvalue()):
        ss.manuscript = (up.name, up.getvalue())
        ss.issues = None
    if ss.manuscript:
        st.caption(f"사용 중인 원고: **{ss.manuscript[0]}** (원본 파일은 변경되지 않습니다)")
    return ss.manuscript


tabs = st.tabs(["① 투고 규정", "② 원고 템플릿", "③ Figure 변환", "④ 원고 서식 변환", "⑤ 오타·오류 점검"])

# ---------------------------------------------------------------- ① guidelines
with tabs[0]:
    st.header("① 투고 규정 입력")
    st.write("규정 텍스트를 붙여넣거나 파일(PDF, Word, TXT, HTML)을 올리세요. 여러 개를 함께 분석할 수 있습니다.")
    st.caption("웹사이트는 브라우저에서 Ctrl+P → 'PDF로 저장'(접힌 섹션은 모두 펼친 뒤) 하거나, 내용을 복사해 아래에 붙여넣으세요.")
    col1, col2 = st.columns(2)
    with col1:
        pasted = st.text_area("투고 규정 텍스트 붙여넣기", height=220, placeholder="Author Guidelines 내용을 붙여넣으세요")
    with col2:
        files = st.file_uploader("규정 파일 업로드", type=["pdf", "docx", "txt", "html", "htm", "md"], accept_multiple_files=True)
        saved = st.file_uploader("또는 저장해 둔 규정 프로필(.json) 불러오기", type=["json"])
    c1, c2 = st.columns([1, 3])
    if c1.button("🔍 규정 분석", type="primary", width="stretch"):
        texts, errors = [], []
        if pasted.strip():
            texts.append(guideline_loader.from_text(pasted))
        for f in files or []:
            try:
                texts.append(guideline_loader.load(f.getvalue(), f.name))
            except Exception as exc:
                errors.append(f"{f.name}: {exc}")
        for e in errors:
            st.error(e)
        if texts:
            ss.profile = extract_profile(guideline_loader.combine(texts))
            ss.editor_version += 1
            st.rerun()
        elif not errors:
            st.warning("규정 텍스트나 파일을 입력하세요.")
    if saved is not None and c2.button("프로필 불러오기"):
        ss.profile = Profile.from_json(saved.getvalue().decode("utf-8"))
        ss.editor_version += 1
        st.rerun()

    profile = ss.profile
    if profile:
        st.subheader(f"추출 결과 — {profile.name}")
        st.caption(f"출처: {profile.source}. 값을 확인·수정한 뒤 맨 아래 '확정'을 누르세요. "
                   "🟡 항목은 규정에 없어 프로그램 기본값을 쓰는 것이며, 저널 요구사항이 아닙니다.")
        with st.form(f"profile_form_{ss.editor_version}"):
            edited = {}
            for cat in CATEGORIES:
                specs = [f for f in FIELDS if f.category == cat]
                n_found = sum(1 for f in specs if profile.rule(f.key).status in ("found", "user"))
                with st.expander(f"{cat}  ({n_found}/{len(specs)} 규정 근거)", expanded=cat in ("기본 서식", "초록·키워드")):
                    for spec in specs:
                        rule = profile.rule(spec.key)
                        a, b, c = st.columns([2.2, 3, 4])
                        a.markdown(f"{STATUS_ICON[rule.status]} **{spec.label}**")
                        key = f"f_{spec.key}_{ss.editor_version}"
                        current = format_value(rule.value) if rule.status != NOT_SPECIFIED else ""
                        if spec.kind == "bool":
                            opts = ["", "예", "아니오"]
                            edited[spec.key] = b.selectbox(spec.label, opts, index=opts.index(current) if current in opts else 0,
                                                           key=key, label_visibility="collapsed")
                        elif spec.kind == "choice":
                            opts = [""] + (spec.choices or [])
                            edited[spec.key] = b.selectbox(spec.label, opts, index=opts.index(current) if current in opts else 0,
                                                           key=key, label_visibility="collapsed")
                        elif spec.key == "refs.examples":
                            edited[spec.key] = b.text_area(spec.label, current, key=key, height=120, label_visibility="collapsed")
                        else:
                            edited[spec.key] = b.text_input(spec.label, current, key=key, label_visibility="collapsed",
                                                            help=spec.help or None)
                        if rule.quote:
                            c.caption(f"📌 {rule.location} — “{rule.quote[:260]}{'…' if len(rule.quote) > 260 else ''}”")
                        else:
                            c.caption(STATUS_LABEL[rule.status])
                        if rule.note:
                            c.warning(rule.note)
            confirm = st.form_submit_button("✔️ 확인했습니다 — 변경 저장 및 확정", type="primary")
        if confirm:
            problems = []
            for k, raw in edited.items():
                spec = SPEC[k]
                try:
                    if spec.kind == "bool":
                        value = None if raw == "" else raw == "예"
                    else:
                        value = parse_value(spec, raw)
                except ValueError:
                    problems.append(f"{spec.label}: '{raw}'을(를) 해석할 수 없습니다.")
                    continue
                old = profile.rule(k).value if profile.rule(k).status != NOT_SPECIFIED else None
                if value != old:
                    profile.set_user(k, value)
            if problems:
                for p in problems:
                    st.error(p)
            else:
                profile.confirmed = True
                st.success("규정을 확정했습니다. ②~⑤ 탭을 사용할 수 있습니다.")
                st.rerun()

# ---------------------------------------------------------------- ② template
with tabs[1]:
    st.header("② 원고 템플릿 (Word)")
    profile = require_profile()
    if profile:
        st.write("확정된 규정으로 서식(용지·여백·글꼴·줄 간격·줄 번호·페이지 번호)과 섹션 순서를 갖춘 Word 템플릿을 만듭니다. "
                 "회색 기울임 글자는 안내 문구이며, Word에서 '스타일 › Placeholder › 모든 인스턴스 선택'으로 한 번에 지울 수 있습니다.")
        order = profile.get("structure.order") or []
        st.caption("섹션 순서: " + " → ".join(order))
        col1, col2 = st.columns(2)
        col1.download_button("⬇️ 원고 템플릿 (.docx)", build_template(profile),
                             file_name=f"{safe_name(profile.name)}_manuscript_template.docx",
                             mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             type="primary", width="stretch")
        col2.download_button("⬇️ 투고 체크리스트 (.docx)", build_checklist(profile),
                             file_name=f"{safe_name(profile.name)}_submission_checklist.docx",
                             mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                             width="stretch")
        st.subheader("투고 체크리스트")
        st.dataframe(pd.DataFrame(checklist_rows(profile)), hide_index=True, width="stretch")

# ---------------------------------------------------------------- ③ figures
with tabs[2]:
    st.header("③ Figure 해상도·형식 변환")
    profile = ss.profile or Profile.empty()
    if ss.profile is None:
        st.caption("규정을 분석하지 않아 일반적인 기본값(사진 300 dpi, 혼합 600 dpi, 선화 1000 dpi, 1단 80 mm, 2단 170 mm)을 씁니다.")
    src = st.radio("그림 가져오기", ["그림 파일 업로드", "원고(.docx)에 삽입된 그림 추출"], horizontal=True)
    inputs: list[tuple[str, bytes]] = []
    if src == "그림 파일 업로드":
        figs = st.file_uploader("PNG, JPG, TIFF, BMP, PDF, PowerPoint(PPTX), EPS, SVG", accept_multiple_files=True,
                                type=["png", "jpg", "jpeg", "tif", "tiff", "bmp", "gif", "webp", "pdf", "pptx", "eps", "svg"])
        if any(f.name.lower().endswith(".pptx") for f in figs or []):
            st.caption("PowerPoint 파일은 슬라이드 하나가 그림 하나가 됩니다. 변환에는 이 컴퓨터의 Microsoft PowerPoint(Windows) 또는 "
                       "LibreOffice를 사용합니다. 둘 다 없으면 PowerPoint에서 'PDF로 저장'한 파일을 올려 주세요.")
        inputs = [(f.name, f.getvalue()) for f in figs or []]
    else:
        ms = manuscript_input("fig")
        if ms:
            inputs = [(f"Figure{i + 1}_{n}", d) for i, (n, d) in enumerate(images_from_docx(ms[1]))]
            st.caption(f"원고에서 그림 {len(inputs)}개를 찾았습니다. Word는 삽입 시 그림을 압축하므로, 원본 그림 파일이 있으면 그것을 쓰는 것이 좋습니다.")

    kinds = {
        f"사진/컬러 (halftone, {profile.get('figures.dpi_halftone', 300)} dpi)": profile.get("figures.dpi_halftone", 300),
        f"혼합 (그래프+사진, {profile.get('figures.dpi_combination', 600)} dpi)": profile.get("figures.dpi_combination", 600),
        f"선화 (line art, {profile.get('figures.dpi_line', 1000)} dpi)": profile.get("figures.dpi_line", 1000),
        "직접 입력": None,
    }
    for key in ("figures.dpi_halftone", "figures.dpi_combination", "figures.dpi_line"):
        if profile.rule(key).status == "default":
            st.caption(f"🟡 {SPEC[key].label}: 규정에 명시가 없어 일반적인 기본값을 표시합니다.")
            break
    c1, c2, c3 = st.columns(3)
    kind = c1.selectbox("그림 종류 → 해상도", list(kinds))
    dpi = kinds[kind] or c1.number_input("dpi", 72, 2400, 300, step=50)
    single, double = profile.get("figures.width_single_mm", 80.0), profile.get("figures.width_double_mm", 170.0)
    widths = {f"1단 ({single:g} mm)": single, f"2단 ({double:g} mm)": double, "원본 크기 유지": None, "직접 입력 (mm)": -1}
    wchoice = c2.selectbox("인쇄 폭", list(widths))
    width = widths[wchoice]
    if width == -1:
        width = c2.number_input("폭 (mm)", 20.0, 500.0, 120.0)
    formats = c3.multiselect("출력 형식", ["PNG", "PDF"], default=["PNG", "PDF"])
    modes = ["RGB", "Grayscale", "CMYK"]
    mode = c3.selectbox("컬러 모드", modes, index=modes.index(profile.get("figures.color_mode", "RGB")))
    d1, d2 = st.columns(2)
    trim = d1.checkbox("그림 주변 흰 여백 자르기 (슬라이드에 권장)", value=True)
    pages_text = d2.text_input("PDF·PPTX에서 변환할 페이지/슬라이드 (비우면 전체)", placeholder="예: 1, 3-5")
    allow_up = st.checkbox("2배를 넘는 업스케일도 허용 (권장하지 않음: 원본에 없는 세부는 생기지 않습니다)")
    try:
        pages = parse_pages(pages_text)
    except ValueError as exc:
        st.error(str(exc))
        pages = None
    if st.button("🖼️ 변환", type="primary", disabled=not inputs or not formats):
        opt = FigureOptions(dpi=int(dpi), width_mm=width, formats=tuple(formats), color_mode=mode, allow_large_upscale=allow_up,
                            trim_whitespace=trim, pages=pages)
        results = [process(n, d, opt) for n, d in inputs]
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
            for r in results:
                for o in r.outputs:
                    zf.writestr(o.filename, o.data)
        ss.fig_results = (results, zbuf.getvalue())
    if ss.get("fig_results"):
        results, zdata = ss.fig_results
        n_out = sum(len(r.outputs) for r in results)
        st.download_button(f"⬇️ 변환된 파일 모두 받기 (ZIP, {n_out}개)", zdata, file_name="figures.zip",
                           mime="application/zip", type="primary", disabled=n_out == 0)
        for r in results:
            icon = "❌" if r.error else ("⚠️" if r.warnings else "✅")
            with st.expander(f"{icon} {r.source}", expanded=bool(r.error or r.warnings)):
                if r.source_info:
                    st.caption("원본: " + ", ".join(f"{k} {v}" for k, v in r.source_info.items()))
                if r.error:
                    st.error(r.error)
                for wmsg in r.warnings:
                    st.warning(wmsg)
                if r.outputs:
                    st.dataframe(pd.DataFrame([{"파일": o.filename, **o.measured} for o in r.outputs]),
                                 hide_index=True, width="stretch")
                    cols = st.columns(len(r.outputs) + 1)
                    for col, o in zip(cols, r.outputs):
                        col.download_button(o.filename, o.data, file_name=o.filename, key=f"dl_{r.source}_{o.filename}")
                    png = next((o for o in r.outputs if o.filename.endswith(".png")), None)
                    if png:
                        cols[-1].image(png.data, caption="미리보기", width="stretch")

# ---------------------------------------------------------------- ④ format manuscript
with tabs[3]:
    st.header("④ 원고 서식 변환 (내용은 절대 수정하지 않음)")
    profile = require_profile()
    if profile:
        st.write("용지·여백·글꼴·글자 크기·줄 간격·줄 번호만 규정에 맞게 바꿉니다. 글자, 문장, 변경 추적, 메모, EndNote 인용, 그림은 그대로 둡니다. "
                 "변환 후 원본과 내용을 자동 비교해, 하나라도 다르면 파일을 만들지 않습니다.")
        ms = manuscript_input("fmt")
        with st.expander("변환 옵션", expanded=False):
            o1, o2, o3 = st.columns(3)
            opt = FormatOptions(
                page=o1.checkbox("용지 크기", True), margins=o1.checkbox("여백", True),
                line_numbers=o1.checkbox("줄 번호", True), font=o2.checkbox("글꼴", True),
                font_size=o2.checkbox("글자 크기", True), line_spacing=o2.checkbox("줄 간격", True),
                tables_font=o3.checkbox("표에도 글꼴 적용", True),
                tables_size_spacing=o3.checkbox("표에도 글자 크기·줄 간격 적용", False),
            )
        if ms and st.button("🛠️ 서식 변환", type="primary"):
            with st.spinner("변환하고 원본과 비교하는 중…"):
                ss.fmt_result = (ms[0], format_manuscript(ms[1], profile, opt))
        if ss.get("fmt_result") and ms and ss.fmt_result[0] == ms[0]:
            name, res = ss.fmt_result
            if res.guard.ok:
                st.success("🔒 " + res.guard.message)
                st.download_button("⬇️ 서식 변환된 원고 (.docx)", res.data, file_name=f"{stem(name)}_formatted.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary")
            else:
                st.error(res.guard.message)
                for d in res.guard.details:
                    st.code(d)
            st.markdown("**적용한 서식**\n" + "\n".join(f"- {a}" for a in res.applied))
            if res.guard.ok and profile.get("tables.footnote_symbols"):
                fn_issues, fn_plans = plan_table_footnotes(DocView.load(DocxPackage.from_bytes(res.data)), profile)
                st.subheader("표 각주 기호")
                rule = " ".join(profile.get("tables.footnote_symbols"))
                p_rule = " ".join(profile.get("tables.p_value_symbols") or [])
                st.caption(f"규정: 일반 각주 {rule} (이 순서){f' · P값 {p_rule}' if p_rule else ''}. "
                           "각주 문장에 P value가 언급되면 P값 각주로 봅니다. 기호는 표 안에 처음 나오는 순서대로 붙입니다.")
                rows = [{"표": f"Table {pl.number}", "기존": m, "변경": new, "종류": pl.kinds[m],
                         "위치 수": pl.occurrences.get(m, 0), "": "변경 없음" if m == new else "변경"}
                        for pl in fn_plans for m, new in pl.mapping.items()]
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
                for pl in fn_plans:
                    for note in pl.notes:
                        st.warning(f"Table {pl.number}: {note}")
                locked = [i for i in fn_issues if not i.fixable]
                if locked:
                    st.warning(f"{len(locked)}곳은 인용 필드 등 보호된 영역이라 직접 고쳐야 합니다.")
                todo = [i for i in fn_issues if i.fixable]
                if not todo:
                    st.success("표 각주 기호가 이미 규정과 맞습니다." if rows else "각주가 달린 표를 찾지 못했습니다.")
                elif st.button(f"✍️ 표 각주 기호 {len(todo)}곳 수정 (변경 내용 추적)"):
                    ss.fn_result = (name, apply_corrections(res.data, todo))
                if ss.get("fn_result") and ss.fn_result[0] == name:
                    fres = ss.fn_result[1]
                    for c in fres.checks:
                        (st.success if "통과" in c else st.error)(c)
                    if fres.ok:
                        st.download_button("⬇️ 서식 변환 + 표 각주 수정본 (변경 내용 추적, .docx)", fres.tracked,
                                           file_name=f"{stem(name)}_formatted_footnotes_tracked.docx",
                                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                           type="primary")
            cols = st.columns(len(res.stats) or 1)
            for col, (k, v) in zip(cols, res.stats.items()):
                col.metric(k, v)
            st.subheader("규정 준수 점검 (자동 수정하지 않은 항목)")
            st.caption("아래 항목은 글자를 바꿔야 하므로 자동으로 고치지 않았습니다. 직접 수정하거나 ⑤ 탭을 이용하세요.")
            df = pd.DataFrame([{"": LEVEL_ICON[f.level], "항목": f.item, "내용": f.detail} for f in res.findings])
            st.dataframe(df, hide_index=True, width="stretch")
            report = "\n".join(f"[{f.level}] {f.item}: {f.detail}" for f in res.findings)
            st.download_button("⬇️ 점검 보고서 (.txt)", report.encode("utf-8"), file_name=f"{stem(name)}_compliance.txt")

# ---------------------------------------------------------------- ⑤ proofreading
with tabs[4]:
    st.header("⑤ 오타·오류 점검")
    profile = ss.profile
    st.write("오타·띄어쓰기·반복어·표기 불일치·약어 정의·인용/그림/표 번호·저널 철자 규칙을 점검합니다. "
             "선택한 항목만 Word **변경 내용 추적**으로 고친 새 파일을 만듭니다 (원본은 그대로).")
    ms = manuscript_input("proof")
    with st.expander("점검 옵션"):
        a, b = st.columns(2)
        popt = ProofOptions(
            spelling=a.checkbox("철자 (오프라인 사전)", True), spacing=a.checkbox("띄어쓰기·문장부호·반복어", True),
            style_spelling=a.checkbox("저널 철자 규칙 (영국식/미국식)", True), consistency=a.checkbox("용어 표기 일관성", True),
            abbreviations=b.checkbox("약어 정의", True), numbering=b.checkbox("인용·그림·표 번호", True),
            units=b.checkbox("숫자-단위 띄어쓰기", True),
        )
        words = st.text_area("사용자 사전 (오타가 아닌 전문 용어, 줄바꿈이나 쉼표로 구분)", height=80)
        popt.user_words = {w.strip() for w in re.split(r"[\n,;]", words) if w.strip()}
        lt = st.text_input("LanguageTool 서버 (선택, 이 컴퓨터/기관 내부 서버만 허용)", placeholder="http://localhost:8081")
        popt.languagetool_url = lt.strip()
    if ms and st.button("🔎 점검 실행", type="primary"):
        try:
            with st.spinner("점검 중…"):
                ss.issues = (ms[0], proofread(ms[1], profile, popt))
                ss.editor_version += 1
        except ValueError as exc:
            st.error(str(exc))
    if ss.get("issues") and ms and ss.issues[0] == ms[0]:
        issues = ss.issues[1]
        fixable = [i for i in issues if i.fixable]
        report_only = [i for i in issues if not i.fixable]
        st.write(f"발견 {len(issues)}건 — 자동 수정 가능 **{len(fixable)}**건, 확인 필요(보고 전용) **{len(report_only)}**건")
        cats = sorted({i.category for i in issues})
        f1, f2 = st.columns(2)
        show_cats = f1.multiselect("범주", cats, default=cats)
        show_conf = f2.multiselect("신뢰도", [HIGH, MEDIUM, LOW], default=[HIGH, MEDIUM, LOW])
        b1, b2, b3, _ = st.columns([1, 1, 1, 3])
        if b1.button("신뢰도 '높음' 선택"):
            ss.sel_mode = "high"; ss.editor_version += 1
        if b2.button("모두 선택"):
            ss.sel_mode = "all"; ss.editor_version += 1
        if b3.button("모두 해제"):
            ss.sel_mode = "none"; ss.editor_version += 1
        mode = ss.get("sel_mode", "high")

        def selected_default(i):
            return {"high": i.default_selected, "all": True, "none": False}[mode]

        rows = [i for i in fixable if i.category in show_cats and i.confidence in show_conf]
        st.subheader("자동 수정 가능 항목")
        st.caption("'적용'을 체크한 항목만 고칩니다. '수정안'은 직접 고칠 수 있습니다. 신뢰도 '높음'이 기본 선택됩니다.")
        df = pd.DataFrame([{
            "적용": selected_default(i), "범주": i.category, "신뢰도": i.confidence, "위치": f"{i.section or '-'} · 문단 {i.para + 1}",
            "원문 (【】 부분)": i.context, "수정안": i.suggestion, "설명": i.message, "id": i.id,
        } for i in rows])
        edited = None
        if not df.empty:
            edited = st.data_editor(
                df, hide_index=True, width="stretch", key=f"editor_{ss.editor_version}",
                disabled=["범주", "신뢰도", "위치", "원문 (【】 부분)", "설명", "id"],
                column_config={"적용": st.column_config.CheckboxColumn(width="small"),
                               "원문 (【】 부분)": st.column_config.TextColumn(width="large"),
                               "id": None},
            )
        rep = [i for i in report_only if i.category in show_cats and i.confidence in show_conf]
        with st.expander(f"확인 필요 항목 (자동 수정 안 함) — {len(rep)}건", expanded=False):
            st.dataframe(pd.DataFrame([{"범주": i.category, "신뢰도": i.confidence, "위치": f"{i.section or '-'} · 문단 {i.para + 1}",
                                        "원문 (【】 부분)": i.context, "설명": i.message} for i in rep]),
                         hide_index=True, width="stretch")
        all_rows = pd.DataFrame([{"id": i.id, "범주": i.category, "신뢰도": i.confidence, "섹션": i.section, "문단": i.para + 1,
                                  "원문": i.original, "수정안": i.suggestion, "맥락": i.context, "설명": i.message,
                                  "자동수정가능": i.fixable} for i in issues])
        st.download_button("⬇️ 점검 결과 (.csv)", all_rows.to_csv(index=False).encode("utf-8-sig"),
                           file_name=f"{stem(ms[0])}_issues.csv", mime="text/csv")

        if edited is not None:
            chosen_ids = {r["id"]: r["수정안"] for _, r in edited.iterrows() if r["적용"]}
            by_id = {i.id: i for i in fixable}
            chosen = []
            for iid, sugg in chosen_ids.items():
                issue = by_id[iid]
                if sugg != issue.suggestion:
                    issue = type(issue)(**{**issue.__dict__, "suggestion": sugg if sugg is not None else ""})
                chosen.append(issue)
            clashes = overlapping(chosen)
            if clashes:
                st.warning(f"선택한 항목 중 {len(clashes)}쌍이 같은 위치를 고칩니다. 겹치는 항목은 하나만 적용됩니다.")
            st.write(f"선택: **{len(chosen)}**건")
            if st.button("✍️ 선택한 항목으로 수정 파일 만들기", type="primary", disabled=not chosen):
                with st.spinner("변경 추적으로 수정하고 검증하는 중…"):
                    ss.apply_result = (ms[0], apply_corrections(ms[1], chosen))
        if ss.get("apply_result") and ss.apply_result[0] == ms[0]:
            name, res = ss.apply_result
            for c in res.checks:
                (st.success if "통과" in c else st.error)(c)
            if res.ok:
                c1, c2 = st.columns(2)
                c1.download_button("⬇️ 수정본 – 변경 내용 추적 (.docx)", res.tracked, file_name=f"{stem(name)}_corrected_tracked.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", type="primary",
                                   width="stretch")
                c2.download_button("⬇️ 수정본 – 변경 반영본 (.docx)", res.clean, file_name=f"{stem(name)}_corrected_clean.docx",
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   width="stretch")
                st.caption("변경 반영본은 이 도구의 수정만 반영한 것이며, 원고에 원래 있던 변경 추적·메모는 그대로 남아 있습니다.")
            if res.skipped:
                with st.expander(f"적용하지 않은 항목 {len(res.skipped)}건"):
                    for iid, why in res.skipped:
                        st.write(f"- {iid}: {why}")
