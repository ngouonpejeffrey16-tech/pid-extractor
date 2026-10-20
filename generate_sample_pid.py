"""Génère un PID (P&ID) de démonstration, entièrement fictif, au format PDF et PNG.

Le schéma représente une petite unité de préparation : cuve de stockage, pompes,
échangeur chauffé à la vapeur et réacteur, avec leurs lignes et leur instrumentation
(repères ISA 5.1). Quelques erreurs sont volontairement glissées dans le plan pour
montrer les contrôles automatiques (repère en double, boucle incomplète, ligne
sans classe de tuyauterie).

Un fichier « vérité terrain » (ground truth) JSON est aussi produit : il liste ce
qu'un ingénieur aurait relevé à la main et sert à mesurer la précision de l'extraction.

Utilisation :
    python generate_sample_pid.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42  # polices TrueType : le texte reste extractible du PDF
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle

OUT_DIR = Path(__file__).resolve().parent / "samples"
LINE_W = 1.2
INK = "#111111"


# ---------------------------------------------------------------- primitives
def pipe(ax, pts, label=None, label_at=0, dashed=False, arrow=True, offset=3.5):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=INK, lw=LINE_W, ls=(0, (4, 3)) if dashed else "-", solid_capstyle="butt")
    if arrow:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
        ax.annotate("", xy=(x1, y1), xytext=(x0 + (x1 - x0) * 0.9, y0 + (y1 - y0) * 0.9),
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=LINE_W, mutation_scale=9))
    if label:
        (x0, y0), (x1, y1) = pts[label_at], pts[label_at + 1]
        if y0 == y1:  # segment horizontal
            ax.text((x0 + x1) / 2, y0 + offset, label, ha="center", va="bottom", fontsize=6.5)
        else:  # segment vertical : texte horizontal à droite
            ax.text(x0 + 2.5, (y0 + y1) / 2, label, ha="left", va="center", fontsize=6.5)


def signal(ax, pts):
    """Liaison de signal électrique (pointillés fins)."""
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=INK, lw=0.7, ls=(0, (2, 2)))


def bubble(ax, x, y, letters, number, dcs=False):
    """Bulle d'instrument ISA : lettres en haut, numéro de boucle en bas.
    dcs=True : instrument en salle de contrôle (trait horizontal dans la bulle)."""
    ax.add_patch(Circle((x, y), 7, fill=True, facecolor="white", edgecolor=INK, lw=1.0, zorder=3))
    if dcs:
        ax.plot([x - 7, x + 7], [y, y], color=INK, lw=0.8, zorder=4)
    ax.text(x, y + 2.6, letters, ha="center", va="center", fontsize=6.3, fontweight="bold", zorder=5)
    ax.text(x, y - 3.0, number, ha="center", va="center", fontsize=6.3, zorder=5)


def control_valve(ax, x, y, horizontal=True):
    """Vanne de régulation : deux triangles opposés (nœud papillon) + actionneur."""
    s = 4.5
    if horizontal:
        ax.add_patch(Polygon([(x - s, y + s * 0.7), (x - s, y - s * 0.7), (x, y)], closed=True,
                             facecolor="white", edgecolor=INK, lw=1, zorder=3))
        ax.add_patch(Polygon([(x + s, y + s * 0.7), (x + s, y - s * 0.7), (x, y)], closed=True,
                             facecolor="white", edgecolor=INK, lw=1, zorder=3))
        ax.plot([x, x], [y, y + 7], color=INK, lw=1)
        ax.add_patch(matplotlib.patches.Wedge((x, y + 7), 4, 0, 180, facecolor="white", edgecolor=INK, lw=1))
    else:
        ax.add_patch(Polygon([(x + s * 0.7, y + s), (x - s * 0.7, y + s), (x, y)], closed=True,
                             facecolor="white", edgecolor=INK, lw=1, zorder=3))
        ax.add_patch(Polygon([(x + s * 0.7, y - s), (x - s * 0.7, y - s), (x, y)], closed=True,
                             facecolor="white", edgecolor=INK, lw=1, zorder=3))
        ax.plot([x, x - 7], [y, y], color=INK, lw=1)
        ax.add_patch(matplotlib.patches.Wedge((x - 7, y), 4, 90, 270, facecolor="white", edgecolor=INK, lw=1))


def hand_valve(ax, x, y, tag):
    s = 4
    ax.add_patch(Polygon([(x - s, y + s * 0.7), (x - s, y - s * 0.7), (x, y)], closed=True,
                         facecolor="white", edgecolor=INK, lw=1, zorder=3))
    ax.add_patch(Polygon([(x + s, y + s * 0.7), (x + s, y - s * 0.7), (x, y)], closed=True,
                         facecolor="white", edgecolor=INK, lw=1, zorder=3))
    ax.text(x, y - 7.5, tag, ha="center", va="center", fontsize=6)


def pump(ax, x, y, tag, desc):
    ax.add_patch(Circle((x, y), 9, facecolor="white", edgecolor=INK, lw=1.3, zorder=3))
    ax.add_patch(Polygon([(x - 6, y - 5), (x + 7, y), (x - 6, y + 5)], closed=True, fill=False,
                         edgecolor=INK, lw=1, zorder=4))
    ax.text(x, y - 15, tag, ha="center", va="center", fontsize=7.5, fontweight="bold")
    ax.text(x, y - 20.5, desc, ha="center", va="center", fontsize=6)


def equipment_label(ax, x, y, tag, desc):
    ax.text(x, y, tag, ha="center", va="center", fontsize=8, fontweight="bold")
    ax.text(x, y - 5.5, desc, ha="center", va="center", fontsize=6.3)


# ---------------------------------------------------------------- schéma
def draw(ax):
    ax.set_xlim(0, 420)
    ax.set_ylim(0, 297)
    ax.set_aspect("equal")
    ax.axis("off")

    # Cadre et cartouche
    ax.add_patch(Rectangle((8, 8), 404, 281, fill=False, edgecolor=INK, lw=1.4))
    ax.add_patch(Rectangle((292, 8), 120, 34, fill=False, edgecolor=INK, lw=1.0))
    ax.text(352, 34, "PID DE DÉMONSTRATION – DOCUMENT FICTIF", ha="center", fontsize=7, fontweight="bold")
    ax.text(352, 26, "Unité de préparation de solution", ha="center", fontsize=6.5)
    ax.text(352, 18, "N° PID-DEMO-001   Rév. A   Format A3", ha="center", fontsize=6.3)
    ax.text(352, 11.5, "Prototype J. Gandhi – extraction IA de PID", ha="center", fontsize=5.8, style="italic")

    # --- TK-101 : cuve de stockage
    ax.add_patch(FancyBboxPatch((30, 120), 50, 100, boxstyle="round,pad=0,rounding_size=8",
                                facecolor="white", edgecolor=INK, lw=1.4))
    equipment_label(ax, 55, 108, "TK-101", "Cuve de stockage")
    bubble(ax, 98, 195, "LT", "101")
    pipe(ax, [(80, 195), (91, 195)], arrow=False)
    bubble(ax, 98, 230, "LI", "101", dcs=True)
    signal(ax, [(98, 202), (98, 223)])
    bubble(ax, 70, 245, "LSHH", "101")
    signal(ax, [(70, 238), (70, 220)])

    # --- Aspiration pompes : 4"-P-1001-A1A
    hand_valve(ax, 92, 135, "HV-001")
    pipe(ax, [(80, 135), (88, 135)], arrow=False)
    pipe(ax, [(96, 135), (121, 135)], label='4"-P-1001-A1A', arrow=False)
    pipe(ax, [(110, 135), (110, 95), (121, 95)], arrow=False)

    pump(ax, 130, 135, "P-101A", "Pompe de transfert")
    pump(ax, 130, 95, "P-101B", "Pompe de secours")

    # --- Refoulement : 3"-P-1002-A1A
    pipe(ax, [(139, 135), (205, 135)], label='3"-P-1002-A1A', arrow=True)
    pipe(ax, [(139, 95), (160, 95), (160, 135)], arrow=False)
    bubble(ax, 172, 160, "PT", "102")
    pipe(ax, [(172, 135), (172, 153)], arrow=False)
    bubble(ax, 150, 160, "PI", "102")
    pipe(ax, [(150, 135), (150, 153)], arrow=False)

    # --- E-101 : échangeur chauffé vapeur
    ax.add_patch(Rectangle((205, 122), 40, 26, facecolor="white", edgecolor=INK, lw=1.4))
    ax.plot([205, 245], [122, 148], color=INK, lw=0.9)
    equipment_label(ax, 225, 113, "E-101", "Réchauffeur")
    # vapeur 2"-S-2001-B2A-IH avec vanne TV-104
    pipe(ax, [(225, 245), (225, 148)], label='2"-S-2001-B2A-IH', arrow=True)
    control_valve(ax, 225, 215, horizontal=False)
    bubble(ax, 200, 215, "TV", "104")
    bubble(ax, 265, 205, "TIC", "104", dcs=True)
    signal(ax, [(258, 205), (240, 205), (240, 215), (207, 215)])
    # condensats
    pipe(ax, [(225, 122), (225, 70)], label='2"-C-2002-B2A', arrow=True)

    # --- Alimentation réacteur : 3"-P-1003-A1A
    pipe(ax, [(245, 135), (310, 135)], label='3"-P-1003-A1A', label_at=0, arrow=True)
    bubble(ax, 262, 160, "TT", "104")
    pipe(ax, [(262, 135), (262, 153)], arrow=False)
    signal(ax, [(262, 167), (262, 172), (265, 172), (265, 198)])
    bubble(ax, 278, 110, "FT", "103")
    pipe(ax, [(278, 135), (278, 117)], arrow=False)
    control_valve(ax, 296, 135)
    bubble(ax, 296, 165, "FV", "103")
    signal(ax, [(296, 158), (296, 146)])
    bubble(ax, 278, 82, "FIC", "103", dcs=True)
    signal(ax, [(278, 103), (278, 89)])
    signal(ax, [(285, 82), (300, 82), (300, 100), (305, 100), (305, 165), (303, 165)])

    # --- R-101 : réacteur agité
    ax.add_patch(FancyBboxPatch((310, 100), 55, 110, boxstyle="round,pad=0,rounding_size=10",
                                facecolor="white", edgecolor=INK, lw=1.4))
    ax.plot([337.5, 337.5], [210, 140], color=INK, lw=1)
    ax.plot([327, 348], [140, 140], color=INK, lw=2)
    equipment_label(ax, 312, 90, "R-101", "Réacteur agité")
    # soupape + évent sans classe de tuyauterie (anomalie volontaire)
    pipe(ax, [(350, 210), (350, 262)], label='1"-V-3001', arrow=True)
    ax.text(356, 230, "PSV-105", ha="left", va="center", fontsize=6.5, fontweight="bold")
    ax.add_patch(Polygon([(346, 222), (354, 222), (350, 230)], closed=True, facecolor="white",
                         edgecolor=INK, lw=1, zorder=3))
    bubble(ax, 385, 200, "PT", "105")
    pipe(ax, [(365, 200), (378, 200)], arrow=False)
    # analyse pH : régulateur sans vanne (anomalie volontaire)
    bubble(ax, 385, 165, "AT", "106")
    pipe(ax, [(365, 165), (378, 165)], arrow=False)
    bubble(ax, 385, 135, "AIC", "106", dcs=True)
    signal(ax, [(385, 158), (385, 142)])
    # repère en double (anomalie volontaire : devrait être TT-107)
    bubble(ax, 385, 112, "TT", "104")
    pipe(ax, [(365, 112), (378, 112)], arrow=False)
    # vidange
    pipe(ax, [(337.5, 100), (337.5, 45)], label='2"-P-1004-A1A', arrow=True)
    hand_valve(ax, 337.5 + 0.01, 58, "HV-002")

    # Légende
    ax.text(20, 60, "Légende", fontsize=7, fontweight="bold")
    ax.text(20, 52, "Trait plein : tuyauterie   ·   Pointillés : signal", fontsize=6)
    ax.text(20, 45, "Bulle barrée : instrument en salle de contrôle (DCS)", fontsize=6)


EXPECTED = {
    "document": "PID-DEMO-001",
    "equipements": ["TK-101", "P-101A", "P-101B", "E-101", "R-101"],
    "instruments": [
        "LT-101", "LI-101", "LSHH-101", "PT-102", "PI-102", "FT-103", "FIC-103", "FV-103",
        "TT-104", "TIC-104", "TV-104", "PSV-105", "PT-105", "AT-106", "AIC-106", "HV-001", "HV-002",
    ],
    "lignes": ['4"-P-1001-A1A', '3"-P-1002-A1A', '3"-P-1003-A1A', '2"-P-1004-A1A',
               '2"-S-2001-B2A-IH', '2"-C-2002-B2A', '1"-V-3001'],
    "anomalies_attendues": [
        {"type": "Repère en double", "objet": "TT-104"},
        {"type": "Régulateur sans vanne", "objet": "AIC-106"},
        {"type": "Ligne sans classe de tuyauterie", "objet": '1"-V-3001'},
    ],
}


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    fig = plt.figure(figsize=(420 / 25.4, 297 / 25.4))  # A3 paysage
    ax = fig.add_axes([0, 0, 1, 1])
    draw(ax)
    fig.savefig(OUT_DIR / "pid_demo.pdf")
    fig.savefig(OUT_DIR / "pid_demo.png", dpi=110)
    plt.close(fig)
    (OUT_DIR / "pid_demo_verite_terrain.json").write_text(
        json.dumps(EXPECTED, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PID de démonstration créé dans {OUT_DIR}")


if __name__ == "__main__":
    main()
