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
import zlib
from dataclasses import dataclass, field

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
    if scale > 1.0001:
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


def process_pdf(name: str, data: bytes, opt: FigureOptions) -> FigureResult:
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter, Transformation

    res = FigureResult(name)
    reader = PdfReader(io.BytesIO(data))
    doc = pdfium.PdfDocument(data)
    stem = _stem(name)
    for i, page in enumerate(reader.pages):
        suffix = f"_p{i + 1}" if len(reader.pages) > 1 else ""
        w_pt, h_pt = float(page.mediabox.width), float(page.mediabox.height)
        if i == 0:
            res.source_info = {"페이지": len(reader.pages), "폭(mm)": round(w_pt / 72 * MM_PER_INCH, 1),
                               "높이(mm)": round(h_pt / 72 * MM_PER_INCH, 1)}
        width_mm = opt.width_mm or w_pt / 72 * MM_PER_INCH
        factor = (width_mm / MM_PER_INCH * 72) / w_pt
        if "PDF" in opt.formats:
            writer = PdfWriter()
            writer.add_page(page)
            out_page = writer.pages[0]
            if abs(factor - 1) > 1e-6:
                out_page.add_transformation(Transformation().scale(factor, factor))
                out_page.mediabox.lower_left = (float(page.mediabox.left) * factor, float(page.mediabox.bottom) * factor)
                out_page.mediabox.upper_right = (float(page.mediabox.right) * factor, float(page.mediabox.top) * factor)
                for box in ("/CropBox", "/TrimBox", "/BleedBox", "/ArtBox"):
                    if box in out_page:
                        del out_page[box]
            buf = io.BytesIO()
            writer.write(buf)
            res.outputs.append(FigureOutput(f"{stem}{suffix}.pdf", buf.getvalue(), measure_pdf(buf.getvalue())))
            if opt.color_mode != "RGB":
                res.warnings.append("PDF(벡터) 출력은 원본 색 공간을 그대로 유지합니다. 컬러 모드 변환은 PNG에만 적용됩니다.")
        if "PNG" in opt.formats:
            scale = opt.dpi / 72 * factor
            bitmap = doc[i].render(scale=scale)
            img = bitmap.to_pil()
            img = _to_mode(img, "RGB" if opt.color_mode == "CMYK" else opt.color_mode, True)
            buf = io.BytesIO()
            img.save(buf, "PNG", dpi=(opt.dpi, opt.dpi), optimize=True)
            res.outputs.append(FigureOutput(f"{stem}{suffix}.png", buf.getvalue(), measure_png(buf.getvalue())))
        _warn_embedded_raster(page, width_mm, opt.dpi, res)
    return res


def _warn_embedded_raster(page, width_mm: float, dpi: int, res: FigureResult) -> None:
    """A 'vector' PDF often just wraps a low-resolution bitmap; say so."""
    try:
        xobjects = page["/Resources"].get("/XObject") or {}
        w_in = width_mm / MM_PER_INCH
        for ref in xobjects.values():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image":
                eff = int(obj["/Width"]) / w_in
                if eff < dpi * 0.95:
                    res.warnings.append(f"이 PDF 안의 그림은 비트맵이며 {width_mm:.0f} mm 폭에서 약 {eff:.0f} dpi입니다(목표 {dpi} dpi). "
                                        "PDF로 감싸도 해상도는 올라가지 않습니다.")
                    return
    except Exception:
        return


RASTER_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp")


def process(name: str, data: bytes, opt: FigureOptions) -> FigureResult:
    lower = name.lower()
    try:
        if lower.endswith(".pdf"):
            return process_pdf(name, data, opt)
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
        return FigureResult(name, error="지원하지 않는 형식입니다 (PNG, JPG, TIFF, BMP, GIF, WEBP, PDF, EPS, SVG).")
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
