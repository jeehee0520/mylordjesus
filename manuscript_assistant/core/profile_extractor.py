"""Rule-based (offline, deterministic) extraction of a Journal Profile from guideline text.

No language model and no network are used. Each extractor looks for explicit
wording ("not exceeding 250 words", "double-spaced", "300 dpi") and records the
sentence it came from. Anything not found stays as default/not specified so the
user can see exactly what was and was not in the guidelines.
"""
from __future__ import annotations

import re
from typing import Callable

from .guideline_loader import GuidelineText
from .profile import FOUND, Profile, Rule

FLAGS = re.I

WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15, "twenty": 20}


def _num(s: str) -> int:
    s = s.lower()
    return WORDNUM[s] if s in WORDNUM else int(s)


class Extractor:
    def __init__(self, g: GuidelineText):
        self.g = g
        self.text = g.text
        self.profile = Profile.empty()
        self.profile.source = g.source_name

    def search(self, patterns: list[str] | str, flags=FLAGS):
        for pat in [patterns] if isinstance(patterns, str) else patterns:
            m = re.search(pat, self.text, flags)
            if m:
                return m
        return None

    def finditer(self, pattern: str, flags=FLAGS):
        return list(re.finditer(pattern, self.text, flags))

    def found(self, key: str, value, m: re.Match, note: str = "") -> None:
        if value in (None, "", []):
            return
        self.profile.rules[key] = Rule(value, FOUND, self.g.sentence_at(m.start()), self.g.location(m.start()), note)

    def negated(self, m: re.Match, window: int = 40) -> bool:
        before = self.text[max(0, m.start() - window):m.start()].lower()
        return bool(re.search(r"\b(no|not|without|don't|do not|need not)\b[^.]*$", before))

    # ---- individual rules -------------------------------------------------
    def journal_name(self):
        m = self.search([r"interest in ([A-Z][^.\n]{3,90}?)\.",
                         r"(?:submit(?:ting)? (?:your (?:manuscript|paper) )?to|welcome to) ([A-Z][^.\n]{3,90}?)[.!]"])
        if m:
            self.found("journal_name", m.group(1).strip(), m)

    def page(self):
        m = self.search(r"\b(A4|US[ -]letter|letter[- ]size(?:d)? paper)\b")
        if m:
            self.found("page.size", "A4" if m.group(1).upper() == "A4" else "Letter", m)
        m = self.search([r"margins?\s+(?:of\s+)?(?:at least\s+)?(\d+(?:\.\d+)?)\s*(cm|mm|inch(?:es)?|in\b|\")",
                         r"(\d+(?:\.\d+)?)\s*(cm|mm|inch(?:es)?|in\b|\")\s*(?:wide\s+)?margins?"])
        if m:
            val, unit = float(m.group(1)), m.group(2).lower()
            cm = val / 10 if unit == "mm" else val if unit == "cm" else val * 2.54
            self.found("page.margin_cm", round(cm, 2), m)

    def text_format(self):
        m = self.search(r"\b(Times New Roman|Arial|Calibri|Helvetica|Cambria|Garamond|Georgia|Verdana|Symbol)\b")
        if m and m.group(1) != "Symbol":
            self.found("text.font", m.group(1), m)
        m = self.search([r"font\s*size:?\s*(?:of\s*)?(\d{1,2})(?:\s*(?:pt|point))?",
                         r"(\d{1,2})[- ]?(?:pt|point)\b(?:\s+(?:font|type))?"])
        if m and 8 <= int(m.group(1)) <= 16:
            self.found("text.size_pt", float(m.group(1)), m)
        m = self.search([r"double[- ]?spac", r"(?:1\.5|one and a half)[- ]?(?:line )?spac", r"single[- ]?spac"])
        if m:
            word = m.group(0).lower()
            value = 2.0 if word.startswith("double") else 1.0 if word.startswith("single") else 1.5
            self.found("text.line_spacing", value, m)
        m = self.search([r"(?:continuous )?line number(?:s|ing|ed)", r"number(?:ed)? (?:all )?lines"])
        if m:
            self.found("text.line_numbers", not self.negated(m), m)
        m = self.search([r"pages? (?:should|must) be numbered", r"number (?:all )?(?:the )?pages",
                         r"(?:include|insert|add) page numbers", r"page numbers? (?:should|must|are required)"])
        if m:
            self.found("text.page_numbers", not self.negated(m), m)

    def length(self):
        m = self.search(r"(?:approximately|about|around|up to)?\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*pages")
        if m:
            self.found("length.pages", f"{m.group(1)}-{m.group(2)}", m)
        m = self.search(r"(\d{3})\s*words per page")
        if m:
            self.found("length.words_per_page", int(m.group(1)), m)
        m = self.search([r"(?:main text|manuscript|article|text)[^.]{0,60}?(?:not exceed|no more than|maximum of|limited to|up to)\s*(\d[\d,]{2,5})\s*words",
                         r"word (?:limit|count)[^.]{0,30}?(\d[\d,]{2,5})\s*words"])
        if m and not re.search(r"abstract|letter|editorial", self.g.sentence_at(m.start()), FLAGS):
            self.found("length.max_words", int(m.group(1).replace(",", "")), m)

    def structure(self):
        m = self.search(r"word count[^.]{0,80}?(?:front|title|first) page|(?:front|title|first) page[^.]{0,60}?word count")
        if m:
            self.found("structure.word_count_on_title_page", True, m)
        m = self.search(r"title should not contain abbreviations|no abbreviations[^.]{0,20}title|title[^.]{0,40}(?:avoid|without) abbreviations")
        if m:
            self.found("structure.title_no_abbreviations", True, m)
        m = self.search(r"maximum of (\w+) affiliations? per author|(\w+) affiliations? per author")
        if m:
            raw = m.group(1) or m.group(2)
            try:
                self.found("structure.max_affiliations", _num(raw), m)
            except (KeyError, ValueError):
                pass
        m = self.search(r"prefix in the title[^.]*?:\s*((?:['‘’\"][^'’\"]+['’\"],?\s*)+)")
        if m:
            self.found("structure.title_prefix", re.sub(r"\s+", " ", m.group(1)).strip(" ,"), m)
        self.section_order()

    ORDER_MAP = [
        ("Title page", r"\btitle\b|full names? of the authors|authors?'? (?:names|institutional)|affiliation"),
        ("Acknowledgments", r"acknowledg"),
        ("Abstract", r"abstract|summary"),
        ("Keywords", r"key ?words"),
        ("Introduction", r"introduction"),
        ("Methods", r"methods"),
        ("Results", r"results"),
        ("Discussion", r"discussion"),
        ("Conclusions", r"conclusion"),
        ("References", r"references"),
        ("Tables", r"\btables?\b"),
        ("Figure legends", r"figure legends?|legends? (?:to|for) figures"),
        ("Appendices", r"appendi"),
        ("Statement of Interests", r"conflicts? of interest|competing interest|statement of interests"),
        ("Funding", r"funding"),
    ]

    def section_order(self):
        m = self.search(r"(?:in|presented in) the following order:?|should be (?:arranged|ordered) as follows:?")
        if not m:
            return
        block = self.text[m.end():m.end() + 1500]
        items = re.split(r"(?:^|\n|\s)(?:(?:[ivx]{1,4})|\d{1,2}|[a-k])[.)]\s+", block)
        items = [i.strip() for i in items if i.strip()]
        order: list[str] = []
        for item in items:
            head = re.split(r";|\.\s+[A-Z]|\n\n", item)[0]
            if len(head) > 400:
                break
            positions = {}
            for name, pat in self.ORDER_MAP:
                hit = re.search(pat, head, FLAGS)
                if hit:
                    positions[name] = hit.start()
            if not positions:
                break
            main = [n for n in ("Introduction", "Methods", "Results", "Discussion", "Conclusions") if n in positions]
            if len(main) >= 2:
                # "Main text - Introduction, Methods, Results, and Discussion"
                matched = main
            elif "Abstract" in positions and "Keywords" in positions and "Title page" not in positions:
                matched = ["Abstract", "Keywords"]
            else:
                # the item is about whatever it names first ("Tables (each table complete with title…)")
                matched = [min(positions, key=positions.get)]
            for name in matched:
                if name not in order:
                    order.append(name)
            if not re.search(r";\s*$|;\s*\w", item) and item.rstrip().endswith("."):
                # an item ending with a full stop is the last one of the list
                if items.index(item) > 2:
                    break
        if len(order) >= 4:
            self.found("structure.order", order, m)

    def abstract(self):
        hits = self.finditer(r"abstract[^.]{0,120}?(?:not exceeding|no more than|not exceed|up to|maximum of|limited to|of up to|max\.?)\s*(\d{2,4})\s*words"
                             r"|(\d{2,4})[- ]word (?:structured )?(?:abstract|summary)")
        values = []
        for m in hits:
            if re.search(r"letter|editorial|lay summary|plain language", self.g.sentence_at(m.start()), FLAGS):
                continue
            values.append((int(m.group(1) or m.group(2)), m))
        if values:
            distinct = sorted({v for v, _ in values})
            note = "" if len(distinct) == 1 else f"규정 안에 서로 다른 값이 있습니다: {distinct}. 논문 유형을 확인하세요."
            self.found("abstract.max_words", values[0][0], values[0][1], note)
        m = self.search([r"(?:provide|include) a structured abstract", r"structured abstract \(", r"structured abstract|abstract[^.]{0,80}structured"])
        if m:
            self.found("abstract.structured", not self.negated(m), m)
        m = self.search(r"(?:head(?:ing)?s?|sub-?headings?|sections?)[:\s]+(?:of\s+)?((?:[A-Z][a-z]+(?:\s(?:and|&)\s[A-Z][a-z]+)?\s*[/,;]\s*(?:and\s+)?){2,}[A-Z][a-z]+)")
        if m:
            heads = [h.strip() for h in re.split(r"[/,;]|\band\b", m.group(1)) if h.strip()]
            self.found("abstract.headings", heads, m)
        m = self.search(r"abstract[^.]{0,250}?(?:no citations?|contain no citation|should not (?:contain|include) (?:any )?(?:citations?|references))"
                        r"|(?:contain|include) no citation to any other published work")
        if m:
            self.found("abstract.no_citations", True, m)
        m = self.search(r"abbreviations?(?: and acronyms)? should be avoided in the abstract|abstract[^.]{0,60}(?:avoid|without|no) abbreviations")
        if m:
            self.found("abstract.avoid_abbreviations", True, m)

    def keywords(self):
        m = self.search([r"(\d+|three|four|five|six)\s*(?:-|–|to)\s*(\d+|five|six|seven|eight|ten)\s*key ?words",
                         r"key ?words?[^.]{0,60}?(\d+|three|four|five|six)\s*(?:-|–|to)\s*(\d+|five|six|seven|eight|ten)"])
        if m:
            self.found("keywords.min", _num(m.group(1)), m)
            self.found("keywords.max", _num(m.group(2)), m)
            return
        m = self.search(r"(?:up to|maximum of|no more than|not more than)\s*(\d+|five|six|seven|eight|ten)\s*key ?words")
        if m:
            self.found("keywords.max", _num(m.group(1)), m)

    def references(self):
        m = self.search([r"\b(AMA)\b(?: Manual of Style| style)?", r"\b(Vancouver)\b", r"\b(APA)\b(?: style| \d)",
                         r"\b(Harvard)\b(?: style| system)", r"\b(ICMJE|NLM)\b[^.]{0,40}(?:style|format)"])
        if m:
            self.found("refs.style", m.group(1).upper() if m.group(1).isupper() else m.group(1), m)
        m = self.search([r"superscript (?:Arabic )?num(?:erals|bers)|Arabic superscript numerals|superscripted? numbers",
                         r"numbers? in square brackets|square brackets",
                         r"author[- ]year|author[- ]date|\(Author,? (?:19|20)\d\d\)"])
        if m:
            word = m.group(0).lower()
            value = "superscript numbers" if "superscript" in word else "numbers in brackets" if "bracket" in word else "author-year"
            self.found("refs.citation", value, m)
        m = self.search(r"numbered consecutively in (?:the )?order (?:of|in which they) (?:appearance|appear)|in order of (?:first )?(?:appearance|citation)")
        if m:
            self.found("refs.order_of_appearance", True, m)
        m = self.search(r"(?:reference examples?(?: follow)?|examples? of (?:the )?references?(?: style)?)[^:\n]{0,30}:")
        if m:
            block = self.text[m.end():m.end() + 900]
            stop = re.search(r"\s(?:Tables?|Figures?|Figure Legends|Supporting Information|Appendi(?:x|ces))\s+(?=[A-Z])", block)
            self.found("refs.examples", (block[:stop.start()] if stop else block).strip(), m)

    def tables(self):
        m = self.search(r"footnote symbols?:?\s*((?:[†‡§¶‖#*]+[\s,]*)+)")
        if m:
            symbols = re.findall(r"[†‡§¶‖#]", m.group(1))
            self.found("tables.footnote_symbols", symbols, m)
            after = self.text[m.end():m.end() + 120]
            p = re.search(r"((?:\*+[\s,]*)+)\s*should be reserved for P-?values", after, FLAGS)
            if p:
                self.found("tables.p_value_symbols", re.findall(r"\*+", p.group(1)), m)
        m = self.search(r"editable files?,? not (?:pasted )?as images|tables?[^.]{0,60}editable")
        if m:
            self.found("tables.editable", True, m)

    def figures(self):
        m = self.search([r"figures?[^.]{0,80}?(?:should|must) be (?:supplied|submitted|uploaded|provided) (?:as|in) separate files",
                         r"figures?[^.]{0,80}?(?:supplied|submitted|uploaded|provided) (?:as|in) separate files"])
        if m:
            self.found("figures.separate_files", True, m)
        kinds = [("figures.dpi_line", r"line ?art|line drawings?|monochrome|black and white|bitmap"),
                 ("figures.dpi_combination", r"combination|mixed|line/tone|halftone and line"),
                 ("figures.dpi_halftone", r"halftone|photo\w*|colou?r|grayscale|greyscale|tone")]
        for m in self.finditer(r"(\d{3,4})\s*(?:dpi|ppi|pixels per inch|dots per inch)"):
            before = self.text[max(0, m.start() - 120):m.start()].lower()
            after = self.text[m.end():m.end() + 60].lower()
            # the image type named closest *before* the number wins ("photographs 300 dpi, line art 1200 dpi")
            best, best_pos = None, -1
            for key, pat in kinds:
                for hit in re.finditer(pat, before):
                    if hit.end() > best_pos:
                        best, best_pos = key, hit.end()
            if best is None:
                best = next((key for key, pat in kinds if re.search(pat, after)), "figures.dpi_halftone")
            if self.profile.rules[best].status != FOUND:
                self.found(best, int(m.group(1)), m)
        formats = []
        first = None
        for m in self.finditer(r"[^.]*\b(?:figure|artwork|image)s?\b[^.]*\bformats?\b[^.]*\.|[^.]*\bformats?\b[^.]*\b(?:figure|artwork|image)s?\b[^.]*\."):
            for f in re.findall(r"\b(TIFF?|EPS|PDF|JPE?G|PNG|SVG|PSD)\b", m.group(0)):
                f = {"TIF": "TIFF", "JPG": "JPEG"}.get(f.upper(), f.upper())
                if f not in formats:
                    formats.append(f)
                    first = first or m
        if formats:
            self.found("figures.formats", formats, first)
        for m in self.finditer(r"(\d{2,3}(?:\.\d+)?)\s*mm[^.]{0,40}?(single|one|1|double|two|2|full)[- ]column"
                               r"|(single|one|1|double|two|2|full)[- ]column[^.]{0,40}?(\d{2,3}(?:\.\d+)?)\s*mm"):
            mm = float(m.group(1) or m.group(4))
            kind = (m.group(2) or m.group(3)).lower()
            key = "figures.width_single_mm" if kind in ("single", "one", "1") else "figures.width_double_mm"
            if self.profile.rules[key].status != FOUND:
                self.found(key, mm, m)
        m = self.search(r"\b(CMYK|RGB)\b")
        if m:
            self.found("figures.color_mode", m.group(1).upper(), m)

    STATEMENTS = {
        "statements.acknowledgments": r"acknowledg(?:e)?ments? section|in an acknowledg|\backnowledg(?:e)?ments?;",
        "statements.data_availability": r"data availability statement|data sharing statement|data accessibility statement",
        "statements.funding": r"funding statement|funding sources?|declaration of funding|sources? of financial support",
        "statements.conflict_of_interest": r"statement of interests|conflict of interest (?:statement|disclosure)|competing interests? statement|disclose any potential sources of conflict",
        "statements.ethics": r"ethics approval statement|ethics committee that approved|approved by (?:the|an) (?:institutional|ethics)",
        "statements.patient_consent": r"patient consent statement|informed consent prior|gave their informed consent",
        "statements.trial_registration": r"clinical trial registration|trial registration number|registered with a clinical trials? registry",
        "statements.authorship": r"authorship statement|author contributions|CRediT",
        "statements.ai_disclosure": r"\b(?:AIGC|artificial intelligence|(?-i:AI))\b[^.]{0,200}?(?:must be described|disclos|declar)|use must be described",
        "statements.orcid": r"\bORCID\b",
    }

    def statements(self):
        for key, pat in self.STATEMENTS.items():
            m = self.search(pat)
            if m:
                self.found(key, True, m)
        m = self.search(r"under (?:a|the) heading\s*['‘\"]([^'’\"]*(?:Interest|Conflict)[^'’\"]*)['’\"]")
        if m:
            self.found("statements.coi_heading", m.group(1).strip(), m)
        m = self.search(r"section (?:entitled|titled|headed)\s*['‘\"]((?:Authorship|Author)[^'’\"]{3,60})['’\"]")
        if m:
            self.found("statements.authorship_heading", m.group(1).strip(), m)
        m = self.search(r"graphical abstract[^.]{0,120}")
        if m:
            sentence = self.g.sentence_at(m.start())
            when = "수정본(revision) 제출 시" if re.search(r"revis", sentence, FLAGS) else "필요"
            self.found("statements.graphical_abstract", when, m)

    def style(self):
        m = self.search([r"journal uses (British|American|UK|US) (?:spelling|English)",
                         r"\b(British|American|UK|US) (?:spelling|English) (?:should|must|is)",
                         r"\b(British|American|UK|US) (?:spelling|English)"])
        if m:
            word = m.group(1).upper()
            value = "British" if word in ("BRITISH", "UK") else "American"
            note = ""
            if len({w.lower() for w in re.findall(r"\b(British|American) spelling", self.text, FLAGS)}) > 1:
                note = "규정에 영국식·미국식 철자가 모두 언급됩니다(예: 약물명 예외). 원문을 확인하세요."
            self.found("style.spelling", value, m, note)
        m = self.search(r"numbers (?:under|below|less than) (\d+|ten) (?:are|should be) spelled out")
        if m:
            self.found("style.numbers_spelled_below", _num(m.group(1)), m)
        m = self.search(r"\bSI(?:[- ]derived)? units\b")
        if m:
            self.found("style.si_units", True, m)
        m = self.search(r"trade names should not be used|referred to by (?:the|their) generic names?")
        if m:
            self.found("style.generic_drug_names", True, m)

    def run(self) -> Profile:
        steps: list[Callable] = [self.journal_name, self.page, self.text_format, self.length, self.structure,
                                 self.abstract, self.keywords, self.references, self.tables, self.figures,
                                 self.statements, self.style]
        for step in steps:
            step()
        return self.profile


def extract_profile(g: GuidelineText) -> Profile:
    return Extractor(g).run()
