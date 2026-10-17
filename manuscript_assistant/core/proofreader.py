"""Offline proofreading: finds typos and errors and proposes corrections.

Everything runs locally. Deterministic checks (spacing, repeated words,
citation/figure/table numbering, abbreviation definitions, term consistency,
journal spelling convention) are combined with a dictionary spell checker
(pyspellchecker) and, optionally, a LanguageTool server that runs on the same
machine. Nothing is sent to an external service.

Each Issue is a proposal. Nothing is changed until the user selects it, and the
corrections are written as tracked changes (see track_changes.py).
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .ooxml import DocxPackage
from .profile import Profile
from .textmodel import OBJ, DocView, Para

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

HIGH, MEDIUM, LOW = "높음", "중간", "낮음"


@dataclass
class Issue:
    para: int
    start: int
    end: int
    original: str
    suggestion: str | None
    category: str
    message: str
    confidence: str
    section: str = ""
    context: str = ""
    fixable: bool = False
    id: str = ""

    @property
    def default_selected(self) -> bool:
        return self.fixable and self.confidence == HIGH


@dataclass
class ProofOptions:
    spelling: bool = True
    spacing: bool = True
    style_spelling: bool = True   # British/American per profile
    consistency: bool = True
    abbreviations: bool = True
    numbering: bool = True        # citations, figures, tables
    units: bool = True
    user_words: set[str] = field(default_factory=set)
    languagetool_url: str = ""    # e.g. http://localhost:8081 ; must be local


SKIP_SPELL_SECTIONS = {"References", "Title page"}
SKIP_STYLE_SECTIONS = {"References"}

# American -> British. Only unambiguous pairs; proper nouns (capitalised mid-sentence) are skipped.
US_UK = {
    "analyze": "analyse", "analyzed": "analysed", "analyzes": "analyses", "analyzing": "analysing",
    "color": "colour", "colors": "colours", "behavior": "behaviour", "behaviors": "behaviours",
    "tumor": "tumour", "tumors": "tumours", "favorable": "favourable", "unfavorable": "unfavourable",
    "center": "centre", "centers": "centres", "fiber": "fibre", "fibers": "fibres", "liter": "litre",
    "liters": "litres", "milliliter": "millilitre", "milliliters": "millilitres",
    "hemoglobin": "haemoglobin", "anemia": "anaemia", "anemic": "anaemic", "edema": "oedema",
    "esophagus": "oesophagus", "esophageal": "oesophageal", "esophagitis": "oesophagitis",
    "diarrhea": "diarrhoea", "hemorrhage": "haemorrhage", "hematology": "haematology",
    "hematologic": "haematological", "pediatric": "paediatric", "pediatrics": "paediatrics",
    "estrogen": "oestrogen", "leukemia": "leukaemia", "celiac": "coeliac", "fetus": "foetus",
    "orthopedic": "orthopaedic", "anesthesia": "anaesthesia", "gynecology": "gynaecology",
    "randomized": "randomised", "randomization": "randomisation", "randomize": "randomise",
    "categorized": "categorised", "characterized": "characterised", "characterize": "characterise",
    "organization": "organisation", "organized": "organised", "recognized": "recognised",
    "standardized": "standardised", "normalized": "normalised", "minimize": "minimise",
    "maximize": "maximise", "optimized": "optimised", "optimize": "optimise", "utilize": "utilise",
    "utilized": "utilised", "hospitalized": "hospitalised", "hospitalization": "hospitalisation",
    "summarized": "summarised", "summarize": "summarise", "dichotomized": "dichotomised",
    "stratified": "stratified", "modeling": "modelling", "labeled": "labelled", "labeling": "labelling",
    "program": "programme", "programs": "programmes", "gray": "grey", "aging": "ageing",
    "multicenter": "multicentre", "fetal": "fetal",
    "judgment": "judgement", "acknowledgment": "acknowledgement", "acknowledgments": "acknowledgements",
}
US_UK = {k: v for k, v in US_UK.items() if k != v}
UK_US = {v: k for k, v in US_UK.items()}

COMPANY_SUFFIX = {"AG", "SA", "NV", "PLC", "LLC", "KG", "GmbH", "Inc", "Ltd", "AB", "AS"}
COMMON_ABBR = {"USA", "UK", "US", "EU", "DNA", "RNA", "SD", "CI", "II", "III", "IV", "MD", "PhD", "OK", "AM", "PM"}
UNITS = r"(?:mg|g|kg|µg|μg|ng|pg|mL|ml|L|dL|µL|μL|mmol|µmol|μmol|nmol|mol|mm|cm|km|min|kDa|Da|Hz|kHz|MHz|IU|mIU)"
URL_RE = re.compile(r"(?:https?://|www\.)\S+|\S+@\S+\.\w+|\bdoi:\S+", re.I)


def _context(text: str, start: int, end: int, width: int = 45) -> str:
    a, b = max(0, start - width), min(len(text), end + width)
    return ("…" if a else "") + text[a:start] + "【" + text[start:end] + "】" + text[end:b] + ("…" if b < len(text) else "")


def _case_like(src: str, word: str) -> str:
    if src.isupper() and len(src) > 1:
        return word.upper()
    if src[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def _masked(text: str) -> str:
    """Replace URLs and e-mail addresses with a neutral symbol so checks ignore them (offsets kept)."""
    return URL_RE.sub(lambda m: "\u25a1" * len(m.group(0)), text)


class Proofreader:
    def __init__(self, view: DocView, profile: Profile | None, opt: ProofOptions):
        self.view = view
        self.profile = profile or Profile.empty()
        self.opt = opt
        self.issues: list[Issue] = []

    def add(self, p: Para, start: int, end: int, suggestion: str | None, category: str, message: str, confidence: str):
        original = p.text[start:end]
        fixable = suggestion is not None and suggestion != original
        if fixable:
            pieces = p.pieces_in(start, end) if end > start else [pc for pc in p.pieces if pc.start <= start <= pc.end]
            fixable = bool(pieces) and not any(pc.locked for pc in pieces) and OBJ not in original
        self.issues.append(Issue(p.index, start, end, original, suggestion, category, message, confidence,
                                 p.section, _context(p.text, start, end), fixable))

    # ---- spacing & punctuation ---------------------------------------------
    def spacing(self, p: Para, text: str):
        for m in re.finditer(r"(?<=\S)( {2,})(?=\S)", text):
            self.add(p, m.start(1), m.end(1), " ", "띄어쓰기", "공백이 두 칸 이상입니다.", HIGH)
        for m in re.finditer(r"(?<=[\w)\]])( +)(?=[,;:)\]]|\.(?:\s|$))", text):
            self.add(p, m.start(1), m.end(1), "", "띄어쓰기", "문장부호 앞에 공백이 있습니다.", HIGH)
        for m in re.finditer(r"(?<=[(\[])( +)(?=\S)", text):
            self.add(p, m.start(1), m.end(1), "", "띄어쓰기", "여는 괄호 뒤에 공백이 있습니다.", MEDIUM)
        for m in re.finditer(r"(?<=[a-z)])([,;])(?=[A-Za-z]{2})", text):
            self.add(p, m.start(1), m.end(1), m.group(1) + " ", "띄어쓰기", "쉼표/세미콜론 뒤에 공백이 없습니다.", MEDIUM)
        if p.section not in SKIP_STYLE_SECTIONS:
            for m in re.finditer(r"(?<=[a-z]{3})\.(?=[A-Z][a-z]{2})", text):
                self.add(p, m.start(), m.end(), ". ", "띄어쓰기", "마침표 뒤에 공백이 없습니다.", MEDIUM)
            for m in re.finditer(r"(?<=[A-Za-z]{3}):(?=[A-Za-z]{2})", text):
                self.add(p, m.start(), m.end(), ": ", "띄어쓰기", "쌍점(:) 뒤에 공백이 없습니다.", MEDIUM)
        for m in re.finditer(r"([,;:])\1+|(?<!\.)\.\.(?!\.)", text):
            self.add(p, m.start(), m.end(), m.group(0)[0], "문장부호", "문장부호가 반복됩니다.", HIGH)
        for m in re.finditer(r"(?<=\w) (-)(?=[A-Za-z]{2})", text):
            self.add(p, m.start(), m.end(), "-", "띄어쓰기", "하이픈 앞에 공백이 있습니다 (복합어라면 붙여 씁니다).", MEDIUM)
        for m in re.finditer(r"\s?\[\d{6,9}\]", text):
            self.add(p, m.start(), m.end(), "", "인용", "인용 관리 프로그램의 임시 인용(PMID 등)이 남아 있습니다.", MEDIUM)
        for m in re.finditer(r"\b([A-Za-z]+)(\s+)\1\b", text, re.I):
            word = m.group(1)
            if word.lower() in ("that", "had", "is") or len(word) < 2:
                conf = LOW
            else:
                conf = HIGH
            self.add(p, m.end(1), m.end(), "", "반복", f"'{word}'가 두 번 연속됩니다.", conf)
        for open_, close in (("(", ")"), ("[", "]")):
            if text.count(open_) != text.count(close):
                idx = text.find(open_) if text.count(open_) > text.count(close) else text.find(close)
                self.add(p, max(idx, 0), max(idx, 0) + 1, None, "괄호", f"'{open_}'와 '{close}'의 개수가 맞지 않습니다.", MEDIUM)

    def units(self, p: Para, text: str):
        for m in re.finditer(rf"(?<![\w.,])(\d+(?:\.\d+)?)({UNITS})(?=[\s,.;:)/]|$)", text):
            self.add(p, m.end(1), m.end(1), " ", "단위 표기", "숫자와 단위 사이에 공백을 넣는 것이 SI 표기입니다 (저널 예시와 다르면 무시).", LOW)

    # ---- spelling --------------------------------------------------------------
    def _spellchecker(self):
        from spellchecker import SpellChecker

        sc = SpellChecker(language="en", distance=2)
        words = set()
        f = DATA_DIR / "medical_words.txt"
        if f.exists():
            words |= {l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}
        user_file = DATA_DIR.parent / "profiles" / "user_dictionary.txt"
        if user_file.exists():
            words |= {l.strip().lower() for l in user_file.read_text(encoding="utf-8").splitlines() if l.strip()}
        words |= {w.lower() for w in self.opt.user_words}
        words |= set(US_UK) | set(US_UK.values())
        # vocabulary of the manuscript itself: names in references, terms used repeatedly
        counts = Counter()
        for p in self.view.paras:
            for tok in re.findall(r"[A-Za-z][A-Za-z']+", _masked(p.text)):
                counts[tok.lower()] += 1
            if p.section in ("References", "Abbreviations", "Title page"):
                words |= {t.lower() for t in re.findall(r"[A-Za-z][A-Za-z']+", p.text)}
        words |= {t for t, c in counts.items() if c >= 3}
        sc.word_frequency.load_words(words)
        return sc

    def spelling(self, paras: list[Para]):
        sc = self._spellchecker()
        candidates: dict[str, list[tuple[Para, int, int]]] = defaultdict(list)
        for p in paras:
            if p.section in SKIP_SPELL_SECTIONS:
                continue
            text = _masked(p.text)
            for m in re.finditer(r"[A-Za-z][A-Za-z'’\-]*", text):
                for part in re.finditer(r"[A-Za-z][a-z]+(?:['’][a-z]+)?", m.group(0)):
                    word = part.group(0)
                    if len(word) < 3 or (part.end() < len(m.group(0)) and m.group(0)[part.end()].isalpha()):
                        continue
                    start = m.start() + part.start()
                    before = text[:start].rstrip()
                    sentence_start = not before or before[-1] in ".!?:\n" or before.endswith(OBJ)
                    if word[0].isupper() and not sentence_start:
                        continue  # proper noun
                    candidates[word.lower().replace("’", "'")].append((p, start, start + len(word)))
        unknown = [u for u in sc.unknown(list(candidates)) if not _derived_from_known(u, sc)]
        for low in sorted(unknown):
            corr = sc.correction(low)
            for p, s, e in candidates[low]:
                word = p.text[s:e]
                if word[:1].isupper():
                    # capitalised unknown words are usually names (e.g. DeLong); never "correct" them
                    self.add(p, s, e, None, "철자", "사전에 없는 단어입니다. 이름·고유명사가 아니라면 철자를 확인하세요.", LOW)
                elif corr and corr != low and len(low) > 3:
                    dist = _edit_distance(low, corr)
                    conf = MEDIUM if dist == 1 else LOW
                    self.add(p, s, e, _case_like(word, corr), "철자", f"사전에 없는 단어입니다. 추천: '{corr}'", conf)
                else:
                    self.add(p, s, e, None, "철자", "사전에 없는 단어입니다 (추천 없음). 의도한 용어라면 사용자 사전에 추가하세요.", LOW)

    def style_spelling(self, paras: list[Para]):
        target = self.profile.get("style.spelling")
        if not target:
            return
        table = US_UK if target == "British" else UK_US
        pat = re.compile(r"\b(" + "|".join(sorted(table, key=len, reverse=True)) + r")\b", re.I)
        for p in paras:
            if p.section in SKIP_STYLE_SECTIONS or p.is_heading and p.section == "Title page":
                continue
            text = _masked(p.text)
            for m in pat.finditer(text):
                word = m.group(1)
                before = text[:m.start()].rstrip()
                sentence_start = not before or before[-1] in ".!?:\n"
                if word[0].isupper() and not sentence_start and not word.isupper():
                    continue  # e.g. "Samsung Medical Center" is a name
                repl = _case_like(word, table[word.lower()])
                self.add(p, m.start(1), m.end(1), repl, "저널 철자 규칙",
                         f"저널 규정은 {'영국식' if target == 'British' else '미국식'} 철자입니다: '{word}' → '{repl}'", MEDIUM)

    # ---- consistency -------------------------------------------------------------
    def consistency(self, paras: list[Para]):
        groups: dict[str, Counter] = defaultdict(Counter)
        where: dict[str, list[tuple[Para, int, int, str]]] = defaultdict(list)
        token = re.compile(r"(?<![\w\-–—])([A-Za-z0-9]+(?:[\-–—/][A-Za-z0-9]+)+)(?![\w])")
        for p in paras:
            if p.section in SKIP_STYLE_SECTIONS:
                continue
            for m in token.finditer(_masked(p.text)):
                raw = m.group(1)
                if not re.search(r"[A-Z]", raw) or not re.search(r"[A-Za-z]", raw):
                    continue
                key = re.sub(r"[\-–—]", "-", raw).lower()
                groups[key][raw] += 1
                where[key].append((p, m.start(1), m.end(1), raw))
        for key, forms in groups.items():
            if len(forms) < 2:
                continue
            distinct_shapes = {f.lower() if f[:1].isupper() and f[1:].islower() else f for f in forms}
            if len({re.sub(r"[\-–—]", "-", f) for f in forms}) == 1 and len({f.lower() for f in forms}) == 1 and \
                    len(distinct_shapes) == 1:
                continue
            majority, _ = forms.most_common(1)[0]
            summary = ", ".join(f"'{f}' {n}회" for f, n in forms.most_common())
            for p, s, e, raw in where[key]:
                if raw != majority:
                    self.add(p, s, e, majority, "표기 일관성", f"같은 용어가 다르게 표기됩니다: {summary}", MEDIUM)

    def abbreviations(self):
        main = [p for p in self.view.paras if p.section in ("Introduction", "Methods", "Results", "Discussion", "Conclusions")
                and not p.is_heading]
        if not main:
            return
        abbr_re = re.compile(r"\b[A-Z][A-Za-z0-9]*[A-Z0-9](?:[-/\u2011–][A-Za-z0-9]*[A-Z0-9])*\b")
        define_re = re.compile(r"\(([A-Z][A-Za-z0-9]*[A-Z0-9](?:[-/\u2011–][A-Za-z0-9]*[A-Z0-9])*)s?[;,)]")
        norm = lambda a: re.sub(r"[\u2011–]", "-", a)
        first_use: dict[str, tuple[Para, int]] = {}
        defined: dict[str, tuple[Para, int]] = {}
        listed = set()
        for p in self.view.by_section.get("Abbreviations", []):
            listed |= set(re.findall(r"\b([A-Z][A-Za-z0-9\-/]*[A-Z0-9])\s*[,:=]", p.text))
        for p in main:
            text = p.text
            for m in define_re.finditer(text):
                defined.setdefault(norm(m.group(1)), (p, m.start(1)))
            for m in abbr_re.finditer(text):
                a = norm(m.group(0))
                if a in COMMON_ABBR or a in COMPANY_SUFFIX or len(a) < 2 or sum(c.isupper() for c in a) < 2:
                    continue
                if re.search(r"/(?:m?L|dL|kg|g|h|min)$", a):
                    continue  # units such as IU/mL
                if re.match(r"\s*,\s*(?:USA|U\.S\.A|United States|Canada|Australia)", text[m.end():m.end() + 20]):
                    continue  # state or province in an address
                first_use.setdefault(a, (p, m.start()))
        for a, (p, pos) in sorted(first_use.items(), key=lambda kv: (kv[1][0].index, kv[1][1])):
            if a in defined:
                dp, dpos = defined[a]
                if (dp.index, dpos) > (p.index, pos + len(a)):
                    self.add(p, pos, pos + len(a), None, "약어",
                             f"'{a}'가 정의(괄호 표기)보다 먼저 사용되었습니다. 첫 사용 위치에서 정의하세요.", MEDIUM)
            else:
                note = " (약어 목록에는 있음)" if a in listed else ""
                self.add(p, pos, pos + len(a), None, "약어", f"본문에서 '{a}'의 정의(풀어쓴 말 + 괄호)를 찾지 못했습니다{note}.", LOW)

    # ---- numbering -----------------------------------------------------------------
    @staticmethod
    def _numbers(text: str) -> list[int]:
        out = []
        for part in re.split(r"[,;]", text):
            part = part.strip()
            m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", part)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 0 < b - a < 200:
                    out.extend(range(a, b + 1))
            elif part.isdigit():
                out.append(int(part))
        return out

    def citations(self):
        refs = [p for p in self.view.by_section.get("References", []) if not p.is_heading and p.text.strip()]
        if not refs:
            return
        numbered = [int(m.group(1)) for p in refs if (m := re.match(r"\s*\[?(\d+)[.)\]\t ]", p.text))]
        n_refs = max(numbered) if numbered else len(refs)
        body_secs = ("Abstract", "Introduction", "Methods", "Results", "Discussion", "Conclusions", "Tables", "Figure legends")
        has_fields = any(pc.field and pc.superscript for p in self.view.paras for pc in p.pieces)
        seq: list[tuple[int, Para, int]] = []
        for p in self.view.paras:
            if p.section not in body_secs or p.is_heading:
                continue
            for s, e, txt in p.superscript_spans():
                if not re.fullmatch(r"\s*\d+(?:\s*[,–-]\s*\d+)*\s*", txt):
                    continue
                if has_fields and not any(pc.field for pc in p.pieces_in(s, e)):
                    continue
                if not has_fields and s > 0 and re.search(r"(?:m|cm|mm|\^)$", p.text[:s]):
                    continue  # e.g. kg/m2
                for n in self._numbers(txt):
                    seq.append((n, p, s))
            for m in re.finditer(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]", p.text):
                for n in self._numbers(m.group(1)):
                    if n < 10000:
                        seq.append((n, p, m.start()))
        if not seq:
            return
        cited = [n for n, _, _ in seq]
        first_order = []
        for n, p, s in seq:
            if n not in first_order:
                if first_order and n < max(first_order) and self.profile.get("refs.order_of_appearance"):
                    self.add(p, s, s, None, "인용 번호",
                             f"참고문헌 {n}번이 {max(first_order)}번보다 나중에 처음 인용됩니다. 등장 순서대로 번호를 매겨야 합니다.", MEDIUM)
                first_order.append(n)
        for n, p, s in seq:
            if n > n_refs:
                self.add(p, s, s, None, "인용 번호", f"인용 {n}번에 해당하는 참고문헌이 없습니다 (목록 {n_refs}개).", HIGH)
        never = sorted(set(range(1, n_refs + 1)) - set(cited))
        if never:
            p = refs[0]
            self.add(p, 0, 0, None, "인용 번호", f"본문에서 인용되지 않은 참고문헌: {', '.join(map(str, never))}", MEDIUM)

    def figures_tables(self):
        cap_re = re.compile(r"^\s*(Table|Figure|Fig\.?)\s*(\d+)\b", re.I)
        captions: dict[str, dict[int, Para]] = {"Table": {}, "Figure": {}}
        caption_paras = set()
        for p in self.view.paras:
            m = cap_re.match(p.text)
            if m and (p.section in ("Tables", "Figure legends") or len(p.text) < 400):
                kind = "Table" if m.group(1).lower().startswith("tab") else "Figure"
                captions[kind].setdefault(int(m.group(2)), p)
                caption_paras.add(p.index)
        mention_re = re.compile(r"\b(Tables?|Figures?|Figs?\.)\s+(\d+[A-Za-z]?(?:\s*(?:,|and|&|–|-|to)\s*\d+[A-Za-z]?)*)")
        first: dict[str, list[tuple[int, Para, int]]] = {"Table": [], "Figure": []}
        for p in self.view.paras:
            if p.index in caption_paras or p.section in ("References", "Tables", "Figure legends"):
                continue
            for m in mention_re.finditer(p.text):
                if re.search(r"(?:Supplementary|Supplemental|Suppl\.?|Online)\s*$", p.text[:m.start()], re.I):
                    continue
                kind = "Table" if m.group(1).lower().startswith("tab") else "Figure"
                nums = self._numbers(re.sub(r"[A-Za-z]|and|&|to", ",", m.group(2)).replace(",,", ","))
                for n in nums:
                    first[kind].append((n, p, m.start()))
        for kind, label in (("Table", "표"), ("Figure", "그림")):
            mentioned = [n for n, _, _ in first[kind]]
            order = []
            for n, p, s in first[kind]:
                if n not in order:
                    if order and n < max(order):
                        self.add(p, s, s, None, f"{label} 번호", f"{kind} {n}이(가) {kind} {max(order)}보다 나중에 처음 언급됩니다. 언급 순서대로 번호를 매기세요.", MEDIUM)
                    order.append(n)
                if captions[kind] and n not in captions[kind]:
                    self.add(p, s, s, None, f"{label} 번호", f"본문의 {kind} {n}에 해당하는 제목/범례가 없습니다.", HIGH)
            for n, p in captions[kind].items():
                if n not in mentioned:
                    self.add(p, 0, 0, None, f"{label} 번호", f"{kind} {n}이(가) 본문에서 언급되지 않습니다.", MEDIUM)

    # ---- optional local LanguageTool -------------------------------------------------
    def languagetool(self, paras: list[Para]):
        url = self.opt.languagetool_url.strip().rstrip("/")
        host = urlparse(url).hostname or ""
        allowed = {"localhost", "127.0.0.1", "::1"} | set(filter(None, os.environ.get("LT_ALLOWED_HOSTS", "").split(",")))
        if host not in allowed:
            raise ValueError(f"LanguageTool 주소 '{host}'는 허용되지 않습니다. 원고가 외부로 나가지 않도록 같은 컴퓨터/기관 내부 서버만 허용합니다 (LT_ALLOWED_HOSTS).")
        import requests

        lang = "en-GB" if self.profile.get("style.spelling") == "British" else "en-US"
        for p in paras:
            if p.section in SKIP_SPELL_SECTIONS or len(p.text.strip()) < 3:
                continue
            resp = requests.post(f"{url}/v2/check", data={"text": p.text, "language": lang,
                                                          "disabledCategories": "TYPOS"}, timeout=30)
            resp.raise_for_status()
            for m in resp.json().get("matches", []):
                s, e = m["offset"], m["offset"] + m["length"]
                repl = m["replacements"][0]["value"] if m.get("replacements") else None
                self.add(p, s, e, repl, "문법 (LanguageTool)", m.get("message", ""), MEDIUM)

    def run(self) -> list[Issue]:
        paras = [p for p in self.view.paras if p.text.strip()]
        for p in paras:
            text = _masked(p.text)
            if self.opt.spacing:
                self.spacing(p, text)
            if self.opt.units and p.section not in SKIP_STYLE_SECTIONS:
                self.units(p, text)
        if self.opt.spelling:
            self.spelling(paras)
        if self.opt.style_spelling:
            self.style_spelling(paras)
        if self.opt.consistency:
            self.consistency(paras)
        if self.opt.abbreviations:
            self.abbreviations()
        if self.opt.numbering:
            self.citations()
            self.figures_tables()
        if self.opt.languagetool_url:
            self.languagetool(paras)
        return finalize(self.issues)


def finalize(issues: list[Issue]) -> list[Issue]:
    """Sort, drop exact duplicates, give stable ids, and make overlapping fixes report-only."""
    seen, out = set(), []
    for i in sorted(issues, key=lambda x: (x.para, x.start, x.end, x.category)):
        key = (i.para, i.start, i.end, i.suggestion, i.category)
        if key in seen:
            continue
        seen.add(key)
        i.id = hashlib.sha1(f"{i.para}:{i.start}:{i.end}:{i.category}:{i.suggestion}".encode()).hexdigest()[:10]
        out.append(i)
    return out


_SUFFIXES = [("ically", "ical"), ("ally", "al"), ("ly", ""), ("ies", "y"), ("es", ""), ("s", ""), ("ed", ""),
             ("ed", "e"), ("ing", ""), ("ing", "e"), ("ered", "er"), ("ers", "er"), ("ity", ""), ("ities", "ity")]
_PREFIXES = ("re", "pre", "post", "non", "multi", "sub", "inter", "intra", "over", "under", "co", "anti", "un")


def _derived_from_known(word: str, sc) -> bool:
    """'resampling', 'pharmacologically', 'specificities': built from a known word, so not a typo."""
    stems = {word}
    for suf, repl in _SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            stems.add(word[: -len(suf)] + repl)
    for st in list(stems):
        for pre in _PREFIXES:
            if st.startswith(pre) and len(st) - len(pre) >= 3:
                stems.add(st[len(pre):].lstrip("-"))
    stems.discard(word)
    return any(not sc.unknown([st]) for st in stems)


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def proofread(data: bytes, profile: Profile | None = None, opt: ProofOptions | None = None) -> list[Issue]:
    view = DocView.load(DocxPackage.from_bytes(data))
    return Proofreader(view, profile, opt or ProofOptions()).run()


def overlapping(selected: list[Issue]) -> list[tuple[Issue, Issue]]:
    pairs = []
    by_para = defaultdict(list)
    for i in selected:
        by_para[i.para].append(i)
    for items in by_para.values():
        items.sort(key=lambda x: (x.start, x.end))
        for a, b in zip(items, items[1:]):
            if b.start < a.end or (a.start == a.end == b.start == b.end):
                pairs.append((a, b))
    return pairs
