"""Builds a Word manuscript template and a submission checklist from a Journal Profile.

Placeholders are grey italic text in the character style "Placeholder" so they are
easy to find (Word: Home › Styles › Select all instances) and delete. Guidance
notes are written only for rules that came from the guidelines or the user;
defaults are applied as formatting but never presented as journal requirements.
"""
from __future__ import annotations

import io

import docx
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .profile import DEFAULT, FIELDS, FOUND, STATUS_LABEL, USER, Profile, format_value

PAGE_SIZES_CM = {"A4": (21.0, 29.7), "Letter": (21.59, 27.94)}
PLACEHOLDER = "Placeholder"


def _cite(profile: Profile, key: str) -> str:
    rule = profile.rules.get(key)
    if rule and rule.status == FOUND and rule.location:
        return f" (Guidelines {rule.location})"
    return ""


def _is_rule(profile: Profile, key: str) -> bool:
    rule = profile.rules.get(key)
    return bool(rule and rule.status in (FOUND, USER) and rule.active and rule.value is not False)


def set_line_numbers(section, on: bool = True) -> None:
    sect_pr = section._sectPr
    existing = sect_pr.find(qn("w:lnNumType"))
    if existing is not None:
        sect_pr.remove(existing)
    if on:
        from .ooxml import SECTPR_ORDER, get_or_add
        el = get_or_add(sect_pr, "lnNumType", SECTPR_ORDER)
        el.set(qn("w:countBy"), "1")
        el.set(qn("w:restart"), "continuous")


def add_page_number(paragraph) -> None:
    run = paragraph.add_run()
    for kind, text in (("begin", None), (None, " PAGE "), ("separate", None), (None, "1"), ("end", None)):
        if kind:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            run._r.append(fld)
        elif text == " PAGE ":
            instr = OxmlElement("w:instrText")
            instr.set(qn("xml:space"), "preserve")
            instr.text = text
            run._r.append(instr)
        else:
            t = OxmlElement("w:t")
            t.text = text
            run._r.append(t)


def apply_base_format(document, profile: Profile) -> None:
    font = profile.get("text.font", "Times New Roman")
    size = Pt(profile.get("text.size_pt", 12.0))
    spacing = profile.get("text.line_spacing", 2.0)
    width, height = PAGE_SIZES_CM.get(profile.get("page.size", "A4"), PAGE_SIZES_CM["A4"])
    margin = Cm(profile.get("page.margin_cm", 2.54))
    for section in document.sections:
        section.page_width, section.page_height = Cm(width), Cm(height)
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = margin
        set_line_numbers(section, bool(profile.get("text.line_numbers", False)))
        if profile.get("text.page_numbers", False):
            para = section.footer.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_page_number(para)

    styles = document.styles
    normal = styles["Normal"]
    normal.font.name, normal.font.size = font, size
    normal.element.rPr.rFonts.set(qn("w:cs"), font)
    normal.paragraph_format.line_spacing = spacing
    normal.paragraph_format.space_after = Pt(0)
    for name, bold_size in (("Title", size), ("Heading 1", size), ("Heading 2", size), ("Heading 3", size)):
        st = styles[name]
        st.font.name, st.font.size, st.font.bold = font, bold_size, True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.font.italic = name == "Heading 3"
        rfonts = st.element.rPr.rFonts
        for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
            rfonts.attrib.pop(qn(attr), None)
        rfonts.set(qn("w:cs"), font)
        st.paragraph_format.line_spacing = spacing
        st.paragraph_format.space_before = Pt(12 if name != "Title" else 0)
        st.paragraph_format.space_after = Pt(0)
    if PLACEHOLDER not in [s.name for s in styles]:
        ph = styles.add_style(PLACEHOLDER, WD_STYLE_TYPE.CHARACTER)
        ph.font.italic = True
        ph.font.color.rgb = RGBColor(0x80, 0x80, 0x80)


class _Writer:
    def __init__(self, document, profile: Profile):
        self.d = document
        self.p = profile

    def heading(self, text: str, level: int = 1):
        return self.d.add_heading(text, level=level)

    def placeholder(self, text: str, label: str | None = None):
        para = self.d.add_paragraph()
        if label:
            para.add_run(label).bold = True
        para.add_run(f"[{text}]", style=PLACEHOLDER)
        return para

    # ---- sections -----------------------------------------------------------
    def title_page(self):
        p = self.p
        self.heading("Title page")
        if _is_rule(p, "structure.title_prefix"):
            self.placeholder(f"Title prefix for some article types: {p.get('structure.title_prefix')}"
                             f"{_cite(p, 'structure.title_prefix')}")
        note = "short, informative, containing the major key words"
        if _is_rule(p, "structure.title_no_abbreviations"):
            note += "; no abbreviations" + _cite(p, "structure.title_no_abbreviations")
        self.placeholder(note, "Title: ")
        self.placeholder("Full names of all authors", "Authors: ")
        aff = "Institutional affiliations where the work was conducted"
        if _is_rule(p, "structure.max_affiliations"):
            aff += f"; maximum {p.get('structure.max_affiliations')} per author{_cite(p, 'structure.max_affiliations')}"
        self.placeholder(aff, "Affiliations: ")
        if _is_rule(p, "statements.orcid"):
            self.placeholder("ORCID iD of each author" + _cite(p, "statements.orcid"), "ORCID: ")
        self.placeholder("Name, postal address, e-mail", "Corresponding author: ")
        if _is_rule(p, "structure.word_count_on_title_page"):
            self.placeholder("Total word count excluding the abstract" + _cite(p, "structure.word_count_on_title_page"),
                             "Word count: ")

    def acknowledgments(self):
        p = self.p
        self.heading("Acknowledgments")
        self.placeholder("Contributors who do not meet authorship criteria (with their permission); financial and material support")
        if _is_rule(p, "statements.authorship"):
            title = p.get("statements.authorship_heading") or "Author contributions"
            self.heading(title, 2)
            if "authorship statement" in title.lower():
                self.placeholder("Name of the author acting as guarantor", "Guarantor of the article: ")
                self.placeholder("Contribution of each author (CRediT roles)", "Specific author contributions: ")
                self.placeholder("Statement that all authors approved the final version of the article, including the authorship list")
            else:
                self.placeholder("Contribution of each author (CRediT roles)" + _cite(p, "statements.authorship"))
        if _is_rule(p, "statements.ai_disclosure"):
            self.placeholder("Describe any use of AI tools in detail (Methods or Acknowledgments)" + _cite(p, "statements.ai_disclosure"))

    def abstract(self):
        p = self.p
        self.heading("Abstract")
        notes = []
        if _is_rule(p, "abstract.structured"):
            notes.append("structured")
        if _is_rule(p, "abstract.max_words"):
            notes.append(f"max {p.get('abstract.max_words')} words")
        if _is_rule(p, "abstract.no_citations"):
            notes.append("no citations")
        if _is_rule(p, "abstract.avoid_abbreviations"):
            notes.append("avoid abbreviations")
        if notes:
            self.placeholder("; ".join(notes) + _cite(p, "abstract.max_words") + " — delete this note")
        headings = p.get("abstract.headings") if _is_rule(p, "abstract.headings") else None
        if headings:
            for h in headings:
                self.placeholder("text", f"{h}: ")
        else:
            self.placeholder("Abstract text")
        if _is_rule(p, "statements.trial_registration"):
            self.placeholder("Clinical trial register and registration number, at the end of the abstract (if applicable)")

    def keywords(self):
        p = self.p
        lo, hi = p.get("keywords.min"), p.get("keywords.max")
        count = f"{lo}–{hi} keywords" if lo and hi else f"up to {hi} keywords" if hi else "keywords"
        self.placeholder(f"{count}, separated by semicolons{_cite(self.p, 'keywords.max')}", "Keywords: ")

    def main(self, name: str):
        texts = {
            "Introduction": "Background, rationale and aim of the study",
            "Methods": "Study design, participants, procedures, statistical analysis",
            "Results": "Findings; cite every table and figure in numerical order",
            "Discussion": "Principal findings, comparison with previous work, strengths and limitations",
            "Conclusions": "Conclusions",
        }
        title = "Materials and Methods" if name == "Methods" else name
        self.heading(title)
        self.placeholder(texts.get(name, name))
        if name == "Methods":
            p = self.p
            if _is_rule(p, "statements.ethics"):
                self.placeholder("Name of the ethics committee that approved the study; conformity with the Declaration of Helsinki"
                                 + _cite(p, "statements.ethics"))
            if _is_rule(p, "statements.patient_consent"):
                self.placeholder("Statement that all participants gave informed consent" + _cite(p, "statements.patient_consent"))
            if _is_rule(p, "statements.trial_registration"):
                self.placeholder("Trial registry and registration number, near the ethics statement (clinical trials)")

    def references(self):
        p = self.p
        self.heading("References")
        notes = []
        if _is_rule(p, "refs.style"):
            notes.append(f"{p.get('refs.style')} style")
        if _is_rule(p, "refs.order_of_appearance"):
            notes.append("numbered consecutively in order of appearance")
        if _is_rule(p, "refs.citation"):
            notes.append(f"in-text citations as {p.get('refs.citation')}")
        if notes:
            self.placeholder("; ".join(notes) + _cite(p, "refs.style"))
        if _is_rule(p, "refs.examples"):
            self.placeholder("Examples from the guidelines (delete before submission):")
            for line in str(p.get("refs.examples")).split("\n"):
                if line.strip():
                    para = self.d.add_paragraph()
                    para.add_run(line.strip(), style=PLACEHOLDER)
        else:
            self.placeholder("1. Reference")

    def tables(self):
        p = self.p
        self.heading("Tables")
        self.placeholder("Title of table 1", "Table 1. ")
        table = self.d.add_table(rows=3, cols=3)
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        notes = []
        if _is_rule(p, "tables.footnote_symbols"):
            notes.append("footnote symbols in this order: " + ", ".join(p.get("tables.footnote_symbols")))
        if _is_rule(p, "tables.p_value_symbols"):
            notes.append(", ".join(p.get("tables.p_value_symbols")) + " reserved for P values")
        notes.append("define all abbreviations in footnotes")
        if _is_rule(p, "tables.editable"):
            notes.append("editable table, not an image")
        self.placeholder("; ".join(notes) + _cite(p, "tables.footnote_symbols"), "Footnotes: ")

    def figure_legends(self):
        p = self.p
        self.heading("Figure legends")
        self.placeholder("Legend: understandable without the text; define symbols, abbreviations and units", "Figure 1. ")
        if _is_rule(p, "figures.separate_files"):
            self.placeholder("Figures are supplied as separate files, not embedded here" + _cite(p, "figures.separate_files"))

    def appendices(self):
        self.heading("Appendices")
        self.placeholder("Appendices, if relevant")

    def statements_block(self, placed: set[str]):
        p = self.p
        coi = p.get("statements.coi_heading") or "Conflict of interest"
        if _is_rule(p, "statements.conflict_of_interest") and "Statement of Interests" not in placed:
            self.heading(coi)
            self.placeholder("Authors' declaration of personal interests (or a statement that there are none)" + _cite(p, "statements.coi_heading"))
            if _is_rule(p, "statements.funding"):
                self.placeholder("Declaration of funding interests: funder and grant number" + _cite(p, "statements.funding"))
        elif _is_rule(p, "statements.funding") and "Funding" not in placed:
            self.heading("Funding")
            self.placeholder("Funder and grant number" + _cite(p, "statements.funding"))
        if _is_rule(p, "statements.data_availability") and "Data Availability" not in placed:
            self.heading("Data availability statement")
            self.placeholder("Where the data can be accessed, or why they are not shared" + _cite(p, "statements.data_availability"))
        if _is_rule(p, "statements.authorship") and "Acknowledgments" not in placed:
            self.heading(p.get("statements.authorship_heading") or "Author contributions")
            self.placeholder("Contribution of each author (CRediT roles)")


def build_template(profile: Profile) -> bytes:
    document = docx.Document()
    apply_base_format(document, profile)
    wr = _Writer(document, profile)
    order = profile.get("structure.order") or []
    placed = set()
    dispatch = {
        "Title page": wr.title_page,
        "Acknowledgments": wr.acknowledgments,
        "Abstract": wr.abstract,
        "Keywords": wr.keywords,
        "References": wr.references,
        "Tables": wr.tables,
        "Figure legends": wr.figure_legends,
        "Appendices": wr.appendices,
    }
    for name in order:
        if name in placed:
            continue
        if name in dispatch:
            dispatch[name]()
        elif name in ("Introduction", "Methods", "Results", "Discussion", "Conclusions"):
            wr.main(name)
        else:
            wr.heading(name)
            wr.placeholder(name)
        placed.add(name)
    wr.statements_block(placed)
    core = document.core_properties
    core.title = f"Manuscript template – {profile.name}"
    core.author = ""
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


def checklist_rows(profile: Profile) -> list[dict]:
    rows = []
    for spec in FIELDS:
        rule = profile.rules.get(spec.key)
        if not rule or not rule.active or rule.value is False or spec.key == "journal_name":
            continue
        if rule.status == DEFAULT and spec.category not in ("기본 서식", "Figure"):
            continue
        rows.append({"분류": spec.category, "항목": spec.label, "요구사항": format_value(rule.value),
                     "근거": rule.location or STATUS_LABEL[rule.status], "상태": STATUS_LABEL[rule.status]})
    return rows


def build_checklist(profile: Profile) -> bytes:
    document = docx.Document()
    styles = document.styles
    styles["Normal"].font.name = "Malgun Gothic"
    styles["Normal"].element.rPr.rFonts.set(qn("w:eastAsia"), "Malgun Gothic")
    styles["Normal"].font.size = Pt(10)
    document.add_heading(f"투고 체크리스트 – {profile.name}", level=1)
    document.add_paragraph(f"규정 출처: {profile.source or '-'}. '규정에 없음 · 기본값' 항목은 저널 요구사항이 아니라 프로그램 기본값입니다.")
    rows = checklist_rows(profile)
    table = document.add_table(rows=1, cols=5)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ["확인", "분류", "항목", "요구사항", "근거"]):
        cell.text = text
        cell.paragraphs[0].runs[0].bold = True
    for row in rows:
        cells = table.add_row().cells
        cells[0].text = "☐"
        cells[1].text, cells[2].text = row["분류"], row["항목"]
        cells[3].text = row["요구사항"][:400]
        cells[4].text = row["근거"]
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()
