"""Turns author guidelines (pasted text, PDF, Word, TXT, HTML) into one searchable string.

Line breaks from narrow PDF columns are joined so that a rule spread over several
lines ("not exceeding 250\\nwords") is matched as one sentence. Every character
offset can be traced back to its page (PDF) or paragraph/line (other formats) so
that each extracted rule can cite where it came from. Nothing leaves the machine.
"""
from __future__ import annotations

import bisect
import io
import re
from dataclasses import dataclass, field

_BULLETS = "•●○◆◇▪■□–-*"


@dataclass
class GuidelineText:
    text: str
    source_name: str
    marks: list[tuple[int, str]] = field(default_factory=list)  # (offset, location label)

    def location(self, offset: int) -> str:
        if not self.marks:
            return ""
        offsets = [m[0] for m in self.marks]
        i = bisect.bisect_right(offsets, offset) - 1
        return self.marks[max(i, 0)][1]

    def sentence_at(self, offset: int, max_len: int = 700) -> str:
        """The sentence around `offset`, for showing the rule's source."""
        start = offset
        while start > 0 and offset - start < max_len // 2:
            if self.text[start - 1] in ".!?\n" and (start >= len(self.text) or self.text[start] == " " or self.text[start - 1] == "\n"):
                break
            start -= 1
        end = offset
        while end < len(self.text) and end - offset < max_len // 2:
            if self.text[end] in ".!?\n" and (end + 1 >= len(self.text) or self.text[end + 1] in " \n"):
                end += 1
                break
            end += 1
        return self.text[start:end].strip()


def _join_lines(lines: list[str]) -> str:
    """Join wrapped lines, keeping list items and headings on their own lines."""
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            if out and not out.endswith("\n"):
                out += "\n"
            continue
        if not out or out.endswith("\n"):
            out += line
        elif line[0] in _BULLETS or re.match(r"^([ivx]+|\d+|[a-z])[.)]\s", line):
            out += "\n" + line
        elif out.endswith(("/", "-")) and not out.endswith((" -", " /")):
            out += line  # URL or hyphenated word broken across lines
        else:
            out += " " + line
    return out


def from_text(text: str, source_name: str = "붙여넣은 텍스트") -> GuidelineText:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    # Pasted web text keeps one paragraph per line; only join when lines look wrapped.
    avg = sum(len(l) for l in lines) / max(len(lines), 1)
    if avg < 60:
        body = _join_lines(lines)
    else:
        body = "\n".join(l.strip() for l in lines)
    marks, pos = [], 0
    for i, chunk in enumerate(body.split("\n")):
        marks.append((pos, f"{i + 1}번째 줄"))
        pos += len(chunk) + 1
    return GuidelineText(body, source_name, marks)


def from_pdf(data: bytes, source_name: str) -> GuidelineText:
    import pdfplumber

    text, marks = "", []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for no, page in enumerate(pdf.pages, start=1):
            lines = (page.extract_text() or "").split("\n")
            # Browsers repeat the list bullet at the top of a page when an item continues there.
            if lines and len(lines[0].strip()) == 1 and lines[0].strip() in _BULLETS + "◆○●":
                lines = lines[1:]
            part = _join_lines(lines)
            # Join pages like lines so a sentence continuing on the next page stays whole.
            if text and part:
                first = part[:1]
                if text.endswith(("/", "-")):
                    sep = ""
                elif first in _BULLETS or (not first.islower() and text.rstrip()[-1:] in ".:;!?"):
                    sep = "\n"
                else:
                    sep = " "
                text += sep
            marks.append((len(text), f"p. {no}"))
            text += part
    if not text.strip():
        raise ValueError("PDF에서 텍스트를 찾을 수 없습니다. 스캔 이미지 PDF라면 OCR 후 다시 올리거나 텍스트를 붙여넣어 주세요.")
    return GuidelineText(text, source_name, marks)


def from_docx(data: bytes, source_name: str) -> GuidelineText:
    import docx

    document = docx.Document(io.BytesIO(data))
    body = document.element.body
    chunks, marks, pos, n = [], [], 0, 0
    for el in body.iterchildren():
        tag = el.tag.split("}")[1]
        texts = []
        if tag == "p":
            texts = ["".join(t.text or "" for t in el.iter("{*}t"))]
        elif tag == "tbl":
            for row in el.iter("{*}tr"):
                texts.append(" | ".join("".join(t.text or "" for t in c.iter("{*}t")) for c in row.iter("{*}tc")))
        for t in texts:
            n += 1
            if t.strip():
                marks.append((pos, f"{n}번째 문단"))
                chunks.append(t.strip())
                pos += len(t.strip()) + 1
    return GuidelineText("\n".join(chunks), source_name, marks)


def from_html(data: bytes, source_name: str) -> GuidelineText:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    lines = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    return from_text("\n".join(l for l in lines if l), source_name)


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp949", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def load(data: bytes, filename: str) -> GuidelineText:
    name = filename.lower()
    if name.endswith(".pdf"):
        return from_pdf(data, filename)
    if name.endswith(".docx"):
        return from_docx(data, filename)
    if name.endswith((".html", ".htm")):
        return from_html(data, filename)
    if name.endswith((".txt", ".md")):
        return from_text(_decode(data), filename)
    if name.endswith(".doc"):
        raise ValueError(".doc(구버전 Word) 파일은 지원하지 않습니다. Word에서 .docx로 다시 저장해 주세요.")
    raise ValueError(f"지원하지 않는 파일 형식입니다: {filename} (PDF, DOCX, TXT, HTML 가능)")


def combine(texts: list[GuidelineText]) -> GuidelineText:
    """Several sources (e.g. PDF + pasted figure requirements) analysed together."""
    if len(texts) == 1:
        return texts[0]
    text, marks = "", []
    for g in texts:
        base = len(text)
        marks.extend((base + o, f"{g.source_name} {label}".strip()) for o, label in (g.marks or [(0, "")]))
        text += g.text + "\n\n"
    return GuidelineText(text, " + ".join(g.source_name for g in texts), marks)
