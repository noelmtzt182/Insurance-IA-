"""Creador de imágenes para anuncios: publicación (1080×1350) e historia (1080×1920).

Genera piezas con plantilla a partir del texto de cada variante aprobada:
foto opcional del asesor o de una familia, logo opcional, colores azul marino y
naranja, titular, texto, botón y una nota legal breve. No inventa fotografías:
si no se sube una foto, se usa un fondo gráfico con los colores de la marca.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.campaign_generator import compliance_issues

NAVY = (11, 42, 91)
NAVY_2 = (20, 60, 122)
NAVY_3 = (31, 78, 156)
ORANGE = (227, 82, 5)
WHITE = (255, 255, 255)
SOFT = (214, 224, 240)
PEACH = (255, 178, 125)

FORMATS = {
    "post": {"label": "Publicación (1080×1350)", "size": (1080, 1350)},
    "story": {"label": "Historia (1080×1920)", "size": (1080, 1920)},
}
DISCLAIMER = "Sujeto a las condiciones de cada aseguradora."
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

_BOLD_CANDIDATES = [
    "DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "Arial Bold.ttf", "arialbd.ttf",
]
_REGULAR_CANDIDATES = [
    "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf", "Arial.ttf", "arial.ttf",
]


@dataclass
class _Font:
    font: ImageFont.FreeTypeFont
    fake_bold: bool = False  # sin fuente negrita disponible se simula con contorno


def _load_font(size: int, bold: bool) -> _Font:
    for path in (_BOLD_CANDIDATES if bold else _REGULAR_CANDIDATES):
        try:
            return _Font(ImageFont.truetype(path, size))
        except OSError:
            continue
    # Fuente escalable incluida en Pillow (≥ 10.1): siempre disponible, también en Streamlit Cloud
    return _Font(ImageFont.load_default(size=size), fake_bold=bold)


def _wrap(draw: ImageDraw.ImageDraw, text: str, f: _Font, max_width: int) -> list[str]:
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=f.font) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text: str, bold: bool, max_width: int, max_lines: int, start: int, minimum: int):
    """Reduce el tamaño de letra hasta que el texto quepa en max_lines renglones."""
    size = start
    while True:
        f = _load_font(size, bold)
        lines = _wrap(draw, text, f, max_width)
        if len(lines) <= max_lines or size <= minimum:
            if len(lines) > max_lines:  # último recurso: recortar con puntos suspensivos
                lines = lines[:max_lines]
                while lines[-1] and draw.textlength(lines[-1] + "…", font=f.font) > max_width:
                    lines[-1] = lines[-1][:-1]
                lines[-1] = lines[-1].rstrip(" ,.;:") + "…"
            return f, lines, size
        size -= 4


def _draw_lines(draw, xy, lines, f: _Font, fill, line_gap: float = 1.18) -> int:
    x, y = xy
    asc, desc = f.font.getmetrics()
    step = int((asc + desc) * line_gap)
    for line in lines:
        draw.text((x, y), line, font=f.font, fill=fill,
                  stroke_width=2 if f.fake_bold else 0, stroke_fill=fill)
        y += step
    return y


def _cover(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.4))


def _brand_background(size: tuple[int, int]) -> Image.Image:
    """Fondo gráfico (sin foto): degradado azul marino con círculos suaves."""
    w, h = size
    bg = Image.new("RGB", size, NAVY)
    grad = Image.linear_gradient("L").resize((w, h))
    bg = Image.composite(Image.new("RGB", size, NAVY_3), bg, ImageOps.invert(grad).point(lambda v: int(v * 0.55)))
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((w * 0.55, -h * 0.15, w * 1.35, h * 0.55), fill=(255, 255, 255, 16))
    d.ellipse((-w * 0.40, h * 0.30, w * 0.40, h * 1.10), fill=(255, 255, 255, 10))
    r = w * 0.045
    d.ellipse((w * 0.80 - r, h * 0.62 - r, w * 0.80 + r, h * 0.62 + r), fill=(227, 82, 5, 230))
    return Image.alpha_composite(bg.convert("RGBA"), layer).convert("RGB")


def _fade(height: int, width: int, start_alpha: int = 0, end_alpha: int = 255) -> Image.Image:
    grad = Image.linear_gradient("L").resize((width, height))
    return grad.point(lambda v: int(start_alpha + (end_alpha - start_alpha) * v / 255))


def _paste_logo(canvas: Image.Image, logo_bytes: Optional[bytes], box: tuple[int, int, int, int]) -> bool:
    if not logo_bytes:
        return False
    logo = ImageOps.exif_transpose(Image.open(io.BytesIO(logo_bytes))).convert("RGBA")
    logo.thumbnail((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    x = box[0]
    y = box[1] + (box[3] - box[1] - logo.height) // 2
    canvas.paste(logo, (x, y), logo)
    return True


def _button(draw, x: int, y: int, text: str, f: _Font, pad_x: int = 44, pad_y: int = 26) -> int:
    tw = draw.textlength(text, font=f.font)
    asc, desc = f.font.getmetrics()
    h = asc + desc + pad_y * 2
    draw.rounded_rectangle((x, y, x + tw + pad_x * 2, y + h), radius=h // 2, fill=ORANGE)
    draw.text((x + pad_x, y + pad_y), text, font=f.font, fill=WHITE,
              stroke_width=2 if f.fake_bold else 0, stroke_fill=WHITE)
    return y + h


# Variantes que el filtro general no detecta (género/número)
EXTRA_RISKY = ["garantizada", "garantizadas", "garantizados", "garantía total", "100 %", "sin exclusiones"]


def validate_texts(headline: str, body: str, cta: str) -> list[str]:
    text = f"{headline} {body} {cta}"
    issues = compliance_issues(text) + [p for p in EXTRA_RISKY if p in text.lower()]
    errors = [f"Frase no permitida en anuncios de seguros: «{p}»" for p in issues]
    if not (headline or "").strip():
        errors.append("Falta el titular.")
    return errors


def render(fmt: str, headline: str, body: str, cta: str, *, eyebrow: str = "", brand_name: str = "",
           photo: Optional[bytes] = None, logo: Optional[bytes] = None) -> bytes:
    """Devuelve la imagen PNG del anuncio. Lanza ValueError si el texto no cumple."""
    if fmt not in FORMATS:
        raise ValueError("Formato inválido.")
    errors = validate_texts(headline, body, cta)
    if errors:
        raise ValueError(" ".join(errors))
    for blob, name in ((photo, "foto"), (logo, "logo")):
        if blob is not None and len(blob) > MAX_UPLOAD_BYTES:
            raise ValueError(f"La {name} excede 8 MB.")
    w, h = FORMATS[fmt]["size"]
    story = fmt == "story"
    margin = 80
    text_w = w - margin * 2

    # Zona de imagen (arriba) y panel de texto (abajo)
    photo_h = int(h * (0.50 if story else 0.52))
    if photo:
        top = _cover(Image.open(io.BytesIO(photo)), (w, photo_h))
    else:
        top = _brand_background((w, photo_h))
    canvas = Image.new("RGB", (w, h), NAVY)
    canvas.paste(top, (0, 0))
    # Degradado de la foto hacia el panel azul marino para que el texto sea legible
    fade_h = int(photo_h * 0.45)
    canvas.paste(Image.new("RGB", (w, fade_h), NAVY), (0, photo_h - fade_h), _fade(fade_h, w, 0, 255))
    if photo:  # oscurecer ligeramente la parte superior para el logo
        canvas.paste(Image.new("RGB", (w, 220), NAVY), (0, 0), _fade(220, w, 140, 0))

    draw = ImageDraw.Draw(canvas)
    # Logo o marca arriba
    top_safe = 120 if story else 56
    if not _paste_logo(canvas, logo, (margin, top_safe, margin + 360, top_safe + 110)) and brand_name:
        f = _load_font(38, True)
        draw.text((margin, top_safe + 30), brand_name[:40], font=f.font, fill=WHITE,
                  stroke_width=2 if f.fake_bold else 0, stroke_fill=WHITE)

    # Bloque de texto
    y = photo_h - int(fade_h * 0.35)
    draw.rectangle((margin, y, margin + 120, y + 10), fill=ORANGE)
    y += 40
    if eyebrow:
        f = _load_font(34, True)
        draw.text((margin, y), eyebrow.upper()[:48], font=f.font, fill=PEACH,
                  stroke_width=1 if f.fake_bold else 0, stroke_fill=PEACH)
        y += 64
    hf, hlines, _ = _fit(draw, headline.strip(), True, text_w, 3 if not story else 4, 92 if story else 84, 52)
    y = _draw_lines(draw, (margin, y), hlines, hf, WHITE, 1.12) + 18
    if body.strip():
        bf, blines, _ = _fit(draw, body.strip(), False, text_w, 4 if story else 3, 44 if story else 40, 30)
        y = _draw_lines(draw, (margin, y), blines, bf, SOFT, 1.3) + 30

    # Botón (por encima de la zona reservada a la interfaz en historias)
    bottom_safe = 300 if story else 120
    cf = _load_font(42 if story else 38, True)
    asc, desc = cf.font.getmetrics()
    btn_h = asc + desc + 52
    btn_y = min(max(y, h - bottom_safe - btn_h - 60), h - bottom_safe - btn_h)
    _button(draw, margin, btn_y, (cta or "Más información").strip()[:32], cf)

    # Nota legal
    nf = _load_font(26, False)
    draw.text((margin, h - (bottom_safe - 40 if story else 70)), DISCLAIMER, font=nf.font, fill=(160, 178, 210))

    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


def zip_images(images: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in images.items():
            z.writestr(name, data)
    return buf.getvalue()
