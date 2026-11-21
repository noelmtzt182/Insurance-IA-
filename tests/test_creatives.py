"""Pruebas del creador de imágenes y historias."""
import io
import zipfile

import pytest
from PIL import Image

from services import creatives


def _png(size=(800, 600), color=(120, 90, 70), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGBA" if fmt == "PNG" else "RGB", size, color).save(buf, fmt)
    return buf.getvalue()


@pytest.mark.parametrize("fmt,size", [("post", (1080, 1350)), ("story", (1080, 1920))])
def test_render_sizes_with_and_without_photo(fmt, size):
    for photo in (None, _png(fmt="JPEG")):
        png = creatives.render(fmt, "Protege lo que más importa", "Asesoría personalizada sin compromiso.",
                               "Solicitar cotización", eyebrow="Seguro de vida", brand_name="Mi Agencia",
                               photo=photo, logo=_png((400, 120)))
        img = Image.open(io.BytesIO(png))
        assert img.format == "PNG" and img.size == size


def test_long_text_is_fitted_not_overflowing():
    long = "Un titular muy largo " * 12
    png = creatives.render("post", long, "Texto " * 80, "Más información")
    assert Image.open(io.BytesIO(png)).size == (1080, 1350)


def test_blocks_risky_phrases():
    for text in ("Cobertura garantizada", "Aprobación inmediata", "Desde $299 al mes", "100% cubierto"):
        with pytest.raises(ValueError):
            creatives.render("post", text, "", "Cotizar")
    with pytest.raises(ValueError):
        creatives.render("post", "", "texto", "Cotizar")


def test_zip_contains_all_images():
    imgs = {"a_post.png": b"1", "a_story.png": b"2"}
    with zipfile.ZipFile(io.BytesIO(creatives.zip_images(imgs))) as z:
        assert sorted(z.namelist()) == ["a_post.png", "a_story.png"]
