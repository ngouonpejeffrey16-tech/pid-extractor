"""Extraction des informations d'un PID au format PDF.

Méthode (sans IA générative, 100 % locale et reproductible) :
1. Lire chaque texte du PDF avec sa position sur le plan (PyMuPDF).
2. Reconstituer les repères d'instruments écrits dans les bulles ISA
   (lettres en haut, numéro de boucle en bas → « FIC » + « 103 » = « FIC-103 »).
3. Classer chaque texte : équipement, instrument, numéro de ligne.
4. Rattacher à chaque équipement sa description (texte situé juste en dessous).

Pour un PID scanné (image sans texte), il faut ajouter une étape d'OCR ou passer
par le mode « IA vision » (voir llm_vision.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from . import isa


@dataclass
class TextItem:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    used: bool = False

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class ExtractionResult:
    source: str
    page_count: int
    equipments: list[dict] = field(default_factory=list)
    instruments: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    unclassified: list[str] = field(default_factory=list)
    has_text_layer: bool = True


def read_text_items(page: pymupdf.Page) -> list[TextItem]:
    """Renvoie chaque ligne de texte du PDF avec sa boîte englobante (en points)."""
    items = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                x0, y0, x1, y1 = line["bbox"]
                items.append(TextItem(text, x0, y0, x1, y1))
    return items


def merge_isa_bubbles(items: list[TextItem], max_dx: float = 8, max_dy: float = 28) -> list[tuple[str, TextItem]]:
    """Associe les lettres d'une bulle ISA au numéro situé juste en dessous.

    Dans une bulle, les lettres (« FIC ») et le numéro (« 103 ») sont deux textes
    séparés. On cherche, pour chaque code lettres, le numéro le plus proche
    verticalement et aligné horizontalement.
    """
    numbers = [it for it in items if isa.LOOP_NUMBER_RE.match(it.text)]
    tags = []
    for it in items:
        if it.used or not isa.is_isa_letters(it.text):
            continue
        candidates = [
            n for n in numbers
            if not n.used and abs(n.cx - it.cx) <= max_dx and 0 < n.cy - it.cy <= max_dy
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda n: n.cy - it.cy)
        it.used = best.used = True
        tags.append((f"{it.text}-{best.text}", it))
    return tags


def find_description(item: TextItem, items: list[TextItem], max_dy: float = 18) -> str:
    """Texte descriptif placé juste sous un repère d'équipement (ex. « Cuve de stockage »)."""
    below = [
        o for o in items
        if not o.used and o is not item and 0 < o.cy - item.cy <= max_dy and abs(o.cx - item.cx) <= 40
        and not isa.EQUIPMENT_RE.match(o.text) and not isa.INSTRUMENT_RE.match(o.text)
    ]
    if not below:
        return ""
    best = min(below, key=lambda o: o.cy - item.cy)
    best.used = True
    return best.text


def extract_pdf(path: str | Path) -> ExtractionResult:
    path = Path(path)
    doc = pymupdf.open(path)
    result = ExtractionResult(source=path.name, page_count=doc.page_count)

    for page_no, page in enumerate(doc, start=1):
        items = read_text_items(page)
        if not items:
            result.has_text_layer = False
            continue

        # 1) Bulles ISA reconstituées
        for tag, anchor in merge_isa_bubbles(items):
            info = isa.parse_instrument(tag)
            if info:
                result.instruments.append(_instrument_row(info, page_no, anchor, "bulle"))

        # 2) Textes isolés : équipements, instruments en ligne, numéros de ligne
        for it in items:
            if it.used:
                continue
            if eq := isa.parse_equipment(it.text):
                it.used = True
                eq["description"] = find_description(it, items)
                eq.update(page=page_no, x=round(it.cx), y=round(it.cy))
                result.equipments.append(eq)
            elif info := isa.parse_instrument(it.text):
                it.used = True
                result.instruments.append(_instrument_row(info, page_no, it, "texte"))
            elif line := isa.parse_line(it.text):
                it.used = True
                line.update(page=page_no, x=round(it.cx), y=round(it.cy))
                result.lines.append(line)

        result.unclassified += [it.text for it in items if not it.used]

    doc.close()
    return result


def _instrument_row(info: isa.InstrumentInfo, page_no: int, anchor: TextItem, origin: str) -> dict:
    return {
        "repere": info.tag,
        "type": info.kind,
        "grandeur": info.variable,
        "boucle": info.loop,
        "lettres": info.letters,
        "lu_dans": origin,
        "page": page_no,
        "x": round(anchor.cx),
        "y": round(anchor.cy),
    }


def render_page_png(path: str | Path, page_no: int = 1, zoom: float = 1.6) -> bytes:
    """Image PNG d'une page du PDF (pour l'affichage et le mode IA vision)."""
    with pymupdf.open(path) as doc:
        pix = doc[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        return pix.tobytes("png")
