"""Resizes figures to a print width and resolution and writes PNG and/or PDF.

Rules:
* pixels = width (inch) × dpi; the aspect ratio is always kept.
* Upscaling cannot add detail that is not in the source, so it is reported and,
  above 2×, refused unless the caller explicitly allows it.
* Vector PDF input stays vector in PDF output (only the page is scaled);
  PNG output from a PDF is rendered at the target dpi.
* Raster PDF output embeds the pixels losslessly (Flate) at the exact physical size.
* Every output is re-opened and measured; the measurements are what is reported.
"""
from __future__ import annotations

import io
import re
import shutil
import subprocess
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = 400_000_000
MM_PER_INCH = 25.4
MAX_UPSCALE_WITHOUT_CONSENT = 2.0


@dataclass
class FigureOptions:
    dpi: int = 300
    width_mm: float | None = None  # None keeps the source's physical width
    formats: tuple[str, ...] = ("PNG", "PDF")
    color_mode: str = "RGB"  # RGB | Grayscale | CMYK
    allow_large_upscale: bool = False
    flatten_transparency: bool = True
    assumed_source_dpi: int = 72  # when a raster has no dpi metadata and width_mm is None
    trim_whitespace: bool = False  # cut the white margin around the figure (useful for slides)
    pages: list[int] | None = None  # 1-based pages/slides to convert; None = all


@dataclass
class FigureOutput:
    filename: str
    data: bytes
    measured: dict


@dataclass
class FigureResult:
    source: str
    outputs: list[FigureOutput] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str = ""
    source_info: dict = field(default_factory=dict)


def _stem(name: str) -> str:
    stem = re.sub(r"\.[^.]+$", "", name.rsplit("/", 1)[-1])
    return re.sub(r"[^\w\-]+", "_", stem).strip("_") or "figure"


def _to_mode(img: Image.Image, mode: str, flatten: bool) -> Image.Image:
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        if flatten or mode != "RGB":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
    if mode == "Grayscale":
        return img.convert("L")
    if mode == "CMYK":
        rgb = img.convert("RGB") if img.mode != "CMYK" else img
        if rgb.mode == "CMYK":
            return rgb
        # Without an output (press) ICC profile the conversion is a naive one; this is reported.
        return rgb.convert("CMYK")
    if img.mode in ("RGB", "RGBA"):
        return img
    return img.convert("RGB")


def raster_pdf(img: Image.Image, dpi: int) -> bytes:
    """Minimal PDF with one losslessly (Flate) compressed image filling a page of the exact size."""
    if img.mode == "1":
        img = img.convert("L")
    space = {"L": "/DeviceGray", "RGB": "/DeviceRGB", "CMYK": "/DeviceCMYK"}[img.mode]
    w_px, h_px = img.size
    w_pt, h_pt = w_px / dpi * 72, h_px / dpi * 72
    stream = zlib.compress(img.tobytes(), 9)
    content = f"q {w_pt:.4f} 0 0 {h_pt:.4f} 0 0 cm /Im0 Do Q".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w_pt:.4f} {h_pt:.4f}] "
        f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>".encode(),
        f"<< /Type /XObject /Subtype /Image /Width {w_px} /Height {h_px} /ColorSpace {space} "
        f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(stream)}".encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def measure_png(data: bytes) -> dict:
    with Image.open(io.BytesIO(data)) as im:
        dpi = im.info.get("dpi", (None, None))[0]
        w, h = im.size
        return {"형식": "PNG", "픽셀": f"{w}×{h}", "dpi": round(dpi) if dpi else None,
                "폭(mm)": round(w / dpi * MM_PER_INCH, 1) if dpi else None,
                "높이(mm)": round(h / dpi * MM_PER_INCH, 1) if dpi else None, "컬러": im.mode}


def measure_pdf(data: bytes) -> dict:
    from pypdf import PdfReader

    page = PdfReader(io.BytesIO(data)).pages[0]
    w_pt, h_pt = float(page.mediabox.width), float(page.mediabox.height)
    info = {"형식": "PDF", "폭(mm)": round(w_pt / 72 * MM_PER_INCH, 1), "높이(mm)": round(h_pt / 72 * MM_PER_INCH, 1)}
    images = []
    try:
        xobjects = page["/Resources"].get("/XObject") or {}
        for ref in xobjects.values():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image":
                images.append((int(obj["/Width"]), int(obj["/Height"]), str(obj.get("/ColorSpace"))))
    except Exception:
        pass
    if images and len(images) == 1:
        iw, ih, cs = images[0]
        info.update({"픽셀": f"{iw}×{ih}", "dpi": round(iw / (w_pt / 72)), "컬러": cs.strip("/")})
    else:
        info.update({"픽셀": "벡터" if not images else f"이미지 {len(images)}개", "dpi": None, "컬러": "-"})
    return info


def _source_dpi(img: Image.Image) -> float | None:
    dpi = img.info.get("dpi")
    if dpi and dpi[0] and dpi[0] > 1:
        return float(dpi[0])
    return None


def process_raster(name: str, data: bytes, opt: FigureOptions) -> FigureResult:
    res = FigureResult(name)
    img = Image.open(io.BytesIO(data))
    img.load()
    src_dpi = _source_dpi(img)
    w_px, h_px = img.size
    res.source_info = {"픽셀": f"{w_px}×{h_px}", "dpi": round(src_dpi) if src_dpi else None, "컬러": img.mode}
    if opt.trim_whitespace:
        box = _content_box(_to_mode(img, "RGB", True))
        if box is None:
            res.error = "그림이 비어 있습니다(전부 흰색)."
            return res
        if box != (0, 0, w_px, h_px):
            img = img.crop(box)
            res.warnings.append(f"흰 여백을 잘라 {w_px}×{h_px} → {img.size[0]}×{img.size[1]} 픽셀이 되었습니다.")
            w_px, h_px = img.size
    if opt.width_mm:
        width_mm = opt.width_mm
    else:
        basis = src_dpi or opt.assumed_source_dpi
        if not src_dpi:
            res.warnings.append(f"원본에 dpi 정보가 없어 {opt.assumed_source_dpi} dpi로 가정해 실제 크기를 계산했습니다. 목표 폭(mm)을 지정하는 것이 정확합니다.")
        width_mm = w_px / basis * MM_PER_INCH
    target_w = max(1, round(width_mm / MM_PER_INCH * opt.dpi))
    target_h = max(1, round(h_px * target_w / w_px))
    scale = target_w / w_px
    if scale > 1.02:  # ignore rounding-level differences
        effective = w_px / (width_mm / MM_PER_INCH)
        msg = (f"업스케일 {scale:.2f}배: 원본은 이 크기({width_mm:.0f} mm)에서 실제 {effective:.0f} dpi입니다. "
               "dpi 숫자를 올려도 원본에 없는 세부는 생기지 않습니다. 가능하면 원본 프로그램에서 고해상도(또는 벡터)로 다시 내보내세요.")
        if scale > MAX_UPSCALE_WITHOUT_CONSENT and not opt.allow_large_upscale:
            res.error = msg + f" ({MAX_UPSCALE_WITHOUT_CONSENT:.0f}배 초과 업스케일은 '허용'을 선택해야 진행합니다.)"
            return res
        res.warnings.append(msg)
    work = _to_mode(img, opt.color_mode, opt.flatten_transparency)
    if (target_w, target_h) != work.size:
        resample = Image.LANCZOS
        if work.mode == "1":
            work = work.convert("L")
        work = work.resize((target_w, target_h), resample)
    stem = _stem(name)
    if "PNG" in opt.formats:
        png_img = work
        if work.mode == "CMYK":
            res.warnings.append("PNG는 CMYK를 지원하지 않아 PNG는 RGB로 저장했습니다 (PDF는 CMYK).")
            png_img = work.convert("RGB")
        buf = io.BytesIO()
        png_img.save(buf, "PNG", dpi=(opt.dpi, opt.dpi), optimize=True)
        res.outputs.append(FigureOutput(f"{stem}.png", buf.getvalue(), measure_png(buf.getvalue())))
    if "PDF" in opt.formats:
        pdf_img = work.convert("RGB") if work.mode not in ("L", "RGB", "CMYK") else work
        data_pdf = raster_pdf(pdf_img, opt.dpi)
        res.outputs.append(FigureOutput(f"{stem}.pdf", data_pdf, measure_pdf(data_pdf)))
    if opt.color_mode == "CMYK":
        res.warnings.append("CMYK 변환은 인쇄용 ICC 프로파일 없이 기본 변환으로 수행되어 색이 달라 보일 수 있습니다. 저널이 CMYK를 요구할 때만 사용하세요.")
    return res


def _content_box(img: Image.Image, pad: int = 4, threshold: int = 250):
    """Pixel box of everything that is not (near-)white, with a small margin; None if blank."""
    gray = img.convert("L").point(lambda v: 255 if v < threshold else 0)
    box = gray.getbbox()
    if box is None:
        return None
    x0, y0, x1, y1 = box
    return (max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad))


def process_pdf(name: str, data: bytes, opt: FigureOptions, label: str = "p") -> FigureResult:
    """Each page (or slide) becomes one figure. Vector content stays vector in the PDF output."""
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, RectangleObject

    res = FigureResult(name)
    reader = PdfReader(io.BytesIO(data))
    doc = pdfium.PdfDocument(data)
    n_pages = len(reader.pages)
    wanted = [p for p in (opt.pages or range(1, n_pages + 1)) if 1 <= p <= n_pages]
    missing = [p for p in (opt.pages or []) if not 1 <= p <= n_pages]
    if missing:
        res.warnings.append(f"없는 번호는 건너뛰었습니다: {', '.join(map(str, missing))} (전체 {n_pages}개)")
    if not wanted:
        res.error = "변환할 페이지가 없습니다."
        return res
    stem = _stem(name)
    first = reader.pages[0].cropbox
    res.source_info = {"페이지" if label == "p" else "슬라이드": n_pages,
                       "폭(mm)": round(float(first.width) / 72 * MM_PER_INCH, 1),
                       "높이(mm)": round(float(first.height) / 72 * MM_PER_INCH, 1)}
    for no in wanted:
        i = no - 1
        page = reader.pages[i]
        base = page.cropbox  # pdfium renders this box
        bw, bh = float(base.width), float(base.height)
        # crop amounts from each edge, in points (left, bottom, right, top)
        crop = (0.0, 0.0, 0.0, 0.0)
        if opt.trim_whitespace:
            s_preview = 2.0
            preview = doc[i].render(scale=s_preview).to_pil()
            box = _content_box(preview, pad=6)
            if box is None:
                res.warnings.append(f"{no}번은 비어 있어 건너뛰었습니다.")
                continue
            x0, y0, x1, y1 = (v / s_preview for v in box)
            crop = (x0, bh - y1, bw - x1, y0)
        cw = bw - crop[0] - crop[2]
        suffix = f"_{label}{no}" if n_pages > 1 or opt.pages else ""
        width_mm = opt.width_mm or cw / 72 * MM_PER_INCH
        factor = (width_mm / MM_PER_INCH * 72) / cw
        if "PDF" in opt.formats:
            writer = PdfWriter()
            writer.add_page(page)
            out_page = writer.pages[0]
            box = RectangleObject([float(base.left) + crop[0], float(base.bottom) + crop[1],
                                   float(base.right) - crop[2], float(base.top) - crop[3]])
            for key in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
                if key in out_page:
                    del out_page[key]
            out_page[NameObject("/MediaBox")] = box
            if abs(factor - 1) > 1e-6:
                out_page.scale_by(factor)
            buf = io.BytesIO()
            writer.write(buf)
            res.outputs.append(FigureOutput(f"{stem}{suffix}.pdf", buf.getvalue(), measure_pdf(buf.getvalue())))
        if "PNG" in opt.formats:
            scale = opt.dpi / 72 * factor
            img = doc[i].render(scale=scale, crop=crop).to_pil()
            img = _to_mode(img, "RGB" if opt.color_mode == "CMYK" else opt.color_mode, True)
            buf = io.BytesIO()
            img.save(buf, "PNG", dpi=(opt.dpi, opt.dpi), optimize=True)
            res.outputs.append(FigureOutput(f"{stem}{suffix}.png", buf.getvalue(), measure_png(buf.getvalue())))
        area = (float(base.left) + crop[0], float(base.bottom) + crop[1], float(base.right) - crop[2], float(base.top) - crop[3])
        _warn_embedded_raster(doc[i], area, factor, opt.dpi, res, f"{no}번" if label == "p" else f"슬라이드 {no}")
    doc.close()
    if "PDF" in opt.formats and opt.color_mode != "RGB":
        res.warnings.append("PDF(벡터) 출력은 원본 색 공간을 그대로 유지합니다. 컬러 모드 변환은 PNG에만 적용됩니다.")
    return res


# ---------------------------------------------------------------------------
# PowerPoint slides
# ---------------------------------------------------------------------------
_PPT_SCRIPT = r"""
param([string]$src, [string]$dst)
$ErrorActionPreference = 'Stop'
$pp = New-Object -ComObject PowerPoint.Application
$before = $pp.Presentations.Count
try {
  # ReadOnly, not Untitled, no window
  $pres = $pp.Presentations.Open($src, -1, 0, 0)
  $pres.SaveAs($dst, 32)   # ppSaveAsPDF
  $pres.Close()
} finally {
  # only close PowerPoint if we started it, never the user's open presentations
  if ($before -eq 0 -and $pp.Presentations.Count -eq 0) { $pp.Quit() }
}
"""


def _find_soffice() -> str | None:
    for cmd in ("soffice", "libreoffice"):
        found = shutil.which(cmd)
        if found:
            return found
    candidates = [
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    return next((c for c in candidates if Path(c).exists()), None)


def pptx_to_pdf(data: bytes) -> tuple[bytes, str]:
    """Convert slides to a vector PDF with PowerPoint (Windows) or LibreOffice, both on this computer."""
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "slides.pptx"
        src.write_bytes(data)
        out = Path(tmp) / "slides.pdf"
        if sys.platform == "win32":
            script = Path(tmp) / "export.ps1"
            script.write_text(_PPT_SCRIPT, encoding="utf-8-sig")
            try:
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-File", str(script), str(src), str(out)],
                               capture_output=True, timeout=300, check=True,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if out.exists():
                    return out.read_bytes(), "Microsoft PowerPoint"
            except (subprocess.SubprocessError, OSError) as exc:
                errors.append(f"PowerPoint: {exc}")
        soffice = _find_soffice()
        if soffice:
            profile = (Path(tmp) / "lo_profile").as_uri()
            try:
                subprocess.run([soffice, "--headless", "--norestore", f"-env:UserInstallation={profile}",
                                "--convert-to", "pdf", "--outdir", tmp, str(src)],
                               capture_output=True, timeout=300, check=True)
                if out.exists():
                    return out.read_bytes(), "LibreOffice"
            except (subprocess.SubprocessError, OSError) as exc:
                errors.append(f"LibreOffice: {exc}")
    raise RuntimeError(
        "슬라이드를 변환하려면 이 컴퓨터에 Microsoft PowerPoint(Windows) 또는 LibreOffice가 필요합니다. "
        "또는 PowerPoint에서 '파일 › 다른 이름으로 저장 › PDF'로 저장한 PDF를 올려 주세요 (그림이 벡터로 유지됩니다)."
        + (f" [{'; '.join(errors)}]" if errors else ""))


def process_pptx(name: str, data: bytes, opt: FigureOptions) -> FigureResult:
    try:
        pdf, engine = pptx_to_pdf(data)
    except RuntimeError as exc:
        return FigureResult(name, error=str(exc))
    res = process_pdf(name, pdf, opt, label="slide")
    note = f"{engine}로 슬라이드를 PDF로 바꾼 뒤 변환했습니다."
    if engine == "LibreOffice":
        note += " 슬라이드의 글꼴이 이 컴퓨터에 없으면 다른 글꼴로 보일 수 있으니 미리보기를 확인하세요."
    res.warnings.insert(0, note)
    return res


def parse_pages(text: str) -> list[int] | None:
    """'1, 3-5' -> [1, 3, 4, 5]; empty -> None (all)."""
    pages: list[int] = []
    for part in re.split(r"[,\s]+", (text or "").strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[-–~]\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            pages.extend(range(min(a, b), max(a, b) + 1))
        elif part.isdigit():
            pages.append(int(part))
        else:
            raise ValueError(f"페이지 번호를 이해할 수 없습니다: '{part}' (예: 1, 3-5)")
    return sorted(set(pages)) or None


def _warn_embedded_raster(pdf_page, area: tuple[float, float, float, float], factor: float, dpi: int,
                          res: FigureResult, label: str) -> None:
    """A 'vector' PDF can still contain bitmaps (photos, or shapes rasterised by the exporter).

    Reports the lowest effective resolution of bitmaps that are visible at a meaningful size
    in the final figure; wrapping a bitmap in a PDF does not raise its resolution.
    """
    import pypdfium2.raw as pdfium_c

    left, bottom, right, top = area
    worst = None
    try:
        for obj in pdf_page.get_objects(filter=[pdfium_c.FPDF_PAGEOBJ_IMAGE], max_depth=8):
            x0, y0, x1, y1 = obj.get_bounds()
            if x1 <= left or x0 >= right or y1 <= bottom or y0 >= top:
                continue
            shown_in = (x1 - x0) * factor / 72
            if shown_in <= 0 or (x1 - x0) < 0.1 * (right - left):
                continue
            eff = obj.get_px_size()[0] / shown_in
            worst = eff if worst is None else min(worst, eff)
    except Exception:
        return
    if worst is not None and worst < dpi * 0.95:
        res.warnings.append(f"{label}: 안에 비트맵 그림이 있으며 최종 크기에서 약 {worst:.0f} dpi입니다(목표 {dpi} dpi). "
                            "이 부분은 해상도가 올라가지 않습니다. 사진은 원본 고해상도 파일로 바꿔 넣고, "
                            "도형·그래프는 가능하면 PowerPoint에서 직접 PDF로 저장하세요.")


RASTER_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")


def process(name: str, data: bytes, opt: FigureOptions) -> FigureResult:
    lower = name.lower()
    try:
        if lower.endswith(".pdf"):
            return process_pdf(name, data, opt)
        if lower.endswith((".pptx", ".ppt")):
            return process_pptx(name, data, opt)
        if lower.endswith(".eps"):
            try:
                img = Image.open(io.BytesIO(data))
                img.load(scale=4)
            except Exception:
                return FigureResult(name, error="EPS를 열려면 Ghostscript가 필요합니다. 그림 프로그램에서 PDF로 내보내 올려 주세요.")
            buf = io.BytesIO()
            img.save(buf, "PNG", dpi=(288, 288))
            return process_raster(name, buf.getvalue(), opt)
        if lower.endswith(".svg"):
            try:
                import cairosvg
            except ImportError:
                return FigureResult(name, error="SVG 변환에는 cairosvg 패키지가 필요합니다. 그림 프로그램에서 PDF로 내보내 올려 주세요.")
            pdf = cairosvg.svg2pdf(bytestring=data)
            return process_pdf(name, pdf, opt)
        if lower.endswith(RASTER_EXT):
            return process_raster(name, data, opt)
        return FigureResult(name, error="지원하지 않는 형식입니다 (PNG, JPG, TIFF, BMP, GIF, WEBP, PDF, PPTX, EPS, SVG).")
    except Exception as exc:  # report, never crash the batch
        return FigureResult(name, error=f"처리 실패: {exc}")


def images_from_docx(data: bytes) -> list[tuple[str, bytes]]:
    """Images embedded in a manuscript, in document order where possible."""
    from .ooxml import DocxPackage, R_NS

    pkg = DocxPackage.from_bytes(data)
    rels = pkg.rels("word/document.xml")
    seen, out = set(), []
    root = pkg.xml("word/document.xml")
    for el in root.iter():
        rid = el.get(f"{{{R_NS}}}embed")
        if rid and rid in rels and rels[rid] not in seen and rels[rid] in pkg.files:
            seen.add(rels[rid])
            out.append((rels[rid].rsplit("/", 1)[-1], pkg.files[rels[rid]]))
    return out
