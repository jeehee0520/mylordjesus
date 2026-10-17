"""Journal Profile: the formatting rules of one journal, each with its evidence.

Every rule has a status:
  found          – read from the guidelines; `quote`/`location` show the source text
  default        – the guidelines say nothing; a common default is used and shown as such
  user           – set or confirmed by the user
  not_specified  – nothing found and no sensible default (the rule is not applied)
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

FOUND, DEFAULT, USER, NOT_SPECIFIED = "found", "default", "user", "not_specified"
STATUS_LABEL = {
    FOUND: "규정 근거 있음",
    DEFAULT: "규정에 없음 · 기본값",
    USER: "사용자 지정",
    NOT_SPECIFIED: "규정에 없음 · 적용 안 함",
}


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str  # bool | int | float | str | choice | list
    category: str
    default: Any = None
    choices: list[str] | None = None
    help: str = ""


CATEGORIES = ["기본 서식", "원고 구성", "초록·키워드", "참고문헌", "표·그림 범례", "Figure", "필수 항목", "문체"]

FIELDS: list[FieldSpec] = [
    FieldSpec("journal_name", "저널 이름", "str", "기본 서식"),
    FieldSpec("page.size", "용지 크기", "choice", "기본 서식", "A4", ["A4", "Letter"]),
    FieldSpec("page.margin_cm", "여백 (cm, 상하좌우)", "float", "기본 서식", 2.54),
    FieldSpec("text.font", "글꼴", "str", "기본 서식", "Times New Roman"),
    FieldSpec("text.size_pt", "글자 크기 (pt)", "float", "기본 서식", 12.0),
    FieldSpec("text.line_spacing", "줄 간격 (배수)", "float", "기본 서식", 2.0, help="2.0 = double spacing"),
    FieldSpec("text.line_numbers", "줄 번호", "bool", "기본 서식", True),
    FieldSpec("text.page_numbers", "페이지 번호", "bool", "기본 서식", True),
    FieldSpec("length.pages", "본문 분량 (페이지)", "str", "원고 구성", None,
              help="예: 12-20 (Introduction~References, double-spaced)"),
    FieldSpec("length.words_per_page", "페이지당 단어 수 (분량 환산용)", "int", "원고 구성", None),
    FieldSpec("length.max_words", "본문 최대 단어 수", "int", "원고 구성", None),
    FieldSpec("structure.order", "원고 구성 순서", "list", "원고 구성",
              ["Title page", "Abstract", "Keywords", "Introduction", "Methods", "Results", "Discussion",
               "Acknowledgments", "References", "Tables", "Figure legends"]),
    FieldSpec("structure.word_count_on_title_page", "제목 페이지에 총 단어 수 기재", "bool", "원고 구성", None),
    FieldSpec("structure.title_no_abbreviations", "제목에 약어 금지", "bool", "원고 구성", None),
    FieldSpec("structure.max_affiliations", "저자당 최대 소속 수", "int", "원고 구성", None),
    FieldSpec("structure.title_prefix", "논문 유형별 제목 접두어", "str", "원고 구성", None),
    FieldSpec("abstract.max_words", "초록 최대 단어 수", "int", "초록·키워드", None),
    FieldSpec("abstract.structured", "구조화 초록", "bool", "초록·키워드", None),
    FieldSpec("abstract.headings", "초록 소제목", "list", "초록·키워드", None),
    FieldSpec("abstract.no_citations", "초록에 인용 금지", "bool", "초록·키워드", None),
    FieldSpec("abstract.avoid_abbreviations", "초록에 약어 지양", "bool", "초록·키워드", None),
    FieldSpec("keywords.min", "키워드 최소 개수", "int", "초록·키워드", None),
    FieldSpec("keywords.max", "키워드 최대 개수", "int", "초록·키워드", None),
    FieldSpec("refs.style", "참고문헌 스타일", "str", "참고문헌", None),
    FieldSpec("refs.citation", "본문 인용 방식", "choice", "참고문헌", None,
              ["superscript numbers", "numbers in brackets", "author-year"]),
    FieldSpec("refs.order_of_appearance", "등장 순서대로 번호", "bool", "참고문헌", None),
    FieldSpec("refs.examples", "참고문헌 예시", "str", "참고문헌", None),
    FieldSpec("tables.footnote_symbols", "표 각주 기호 (순서)", "list", "표·그림 범례", None),
    FieldSpec("tables.p_value_symbols", "P값 전용 기호", "list", "표·그림 범례", None),
    FieldSpec("tables.editable", "표는 편집 가능한 형식 (이미지 금지)", "bool", "표·그림 범례", None),
    FieldSpec("figures.separate_files", "그림은 별도 파일로 제출", "bool", "Figure", None),
    FieldSpec("figures.dpi_halftone", "사진(halftone) 최소 dpi", "int", "Figure", 300),
    FieldSpec("figures.dpi_combination", "혼합(combination) 최소 dpi", "int", "Figure", 600),
    FieldSpec("figures.dpi_line", "선화(line art) 최소 dpi", "int", "Figure", 1000),
    FieldSpec("figures.formats", "허용 파일 형식", "list", "Figure", ["PNG", "PDF"]),
    FieldSpec("figures.width_single_mm", "1단 폭 (mm)", "float", "Figure", 80.0),
    FieldSpec("figures.width_double_mm", "2단 폭 (mm)", "float", "Figure", 170.0),
    FieldSpec("figures.color_mode", "컬러 모드", "choice", "Figure", "RGB", ["RGB", "CMYK", "Grayscale"]),
    FieldSpec("statements.acknowledgments", "Acknowledgments", "bool", "필수 항목", None),
    FieldSpec("statements.data_availability", "Data availability statement", "bool", "필수 항목", None),
    FieldSpec("statements.funding", "Funding statement", "bool", "필수 항목", None),
    FieldSpec("statements.conflict_of_interest", "Conflict of interest / Statement of Interests", "bool", "필수 항목", None),
    FieldSpec("statements.coi_heading", "이해관계 섹션 제목", "str", "필수 항목", None),
    FieldSpec("statements.authorship_heading", "저자 기여 섹션 제목", "str", "필수 항목", None),
    FieldSpec("statements.ethics", "Ethics approval statement", "bool", "필수 항목", None),
    FieldSpec("statements.patient_consent", "Patient consent statement", "bool", "필수 항목", None),
    FieldSpec("statements.trial_registration", "Clinical trial registration", "bool", "필수 항목", None),
    FieldSpec("statements.authorship", "Authorship statement / Author contributions", "bool", "필수 항목", None),
    FieldSpec("statements.ai_disclosure", "AI 사용 공개", "bool", "필수 항목", None),
    FieldSpec("statements.graphical_abstract", "Graphical abstract", "str", "필수 항목", None),
    FieldSpec("statements.orcid", "ORCID", "bool", "필수 항목", None),
    FieldSpec("style.spelling", "철자", "choice", "문체", None, ["British", "American"]),
    FieldSpec("style.numbers_spelled_below", "이 수 미만은 영어로 표기", "int", "문체", None),
    FieldSpec("style.si_units", "SI 단위 사용", "bool", "문체", None),
    FieldSpec("style.generic_drug_names", "상품명 대신 일반명", "bool", "문체", None),
]
SPEC = {f.key: f for f in FIELDS}


@dataclass
class Rule:
    value: Any = None
    status: str = NOT_SPECIFIED
    quote: str = ""
    location: str = ""
    note: str = ""

    @property
    def active(self) -> bool:
        return self.status != NOT_SPECIFIED and self.value not in (None, "", [])


@dataclass
class Profile:
    rules: dict[str, Rule] = field(default_factory=dict)
    source: str = ""
    confirmed: bool = False

    @classmethod
    def empty(cls) -> "Profile":
        p = cls()
        for spec in FIELDS:
            if spec.default is not None:
                p.rules[spec.key] = Rule(spec.default, DEFAULT)
            else:
                p.rules[spec.key] = Rule()
        return p

    def get(self, key: str, fallback: Any = None) -> Any:
        rule = self.rules.get(key)
        if rule is None or not rule.active:
            return fallback
        return rule.value

    def rule(self, key: str) -> Rule:
        return self.rules.setdefault(key, Rule())

    def set_user(self, key: str, value: Any) -> None:
        rule = self.rule(key)
        if value in (None, "", []):
            rule.value, rule.status = None, NOT_SPECIFIED
        elif value != rule.value or rule.status in (DEFAULT, NOT_SPECIFIED):
            rule.value, rule.status = value, USER

    def to_json(self) -> str:
        data = {"source": self.source, "confirmed": self.confirmed,
                "rules": {k: asdict(v) for k, v in self.rules.items()}}
        return json.dumps(data, ensure_ascii=False, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "Profile":
        data = json.loads(text)
        p = cls.empty()
        p.source = data.get("source", "")
        p.confirmed = data.get("confirmed", False)
        for k, v in data.get("rules", {}).items():
            p.rules[k] = Rule(**{f: v.get(f, getattr(Rule(), f)) for f in ("value", "status", "quote", "location", "note")})
        return p

    @property
    def name(self) -> str:
        return self.get("journal_name", "") or "journal"


def parse_value(spec: FieldSpec, raw: str) -> Any:
    """Parse a value typed in the UI."""
    raw = (raw or "").strip()
    if raw == "":
        return None
    if spec.kind == "bool":
        return raw.lower() in ("true", "yes", "y", "1", "예", "o", "필수")
    if spec.kind == "int":
        return int(float(raw))
    if spec.kind == "float":
        return float(raw)
    if spec.kind == "list":
        sep = "/" if "/" in raw and ";" not in raw and "," not in raw else None
        items = raw.split(sep) if sep else [x for chunk in raw.split(";") for x in chunk.split(",")]
        return [x.strip() for x in items if x.strip()]
    return raw


def format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return str(value)
