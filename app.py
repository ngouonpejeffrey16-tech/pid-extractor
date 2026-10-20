"""Interface de démonstration : extraction automatique d'informations à partir d'un PID.

Lancer :  streamlit run app.py
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pandas as pd
import pymupdf
import streamlit as st

from pid_extractor import build_loops, evaluate, extract_pdf, run_checks, to_excel
from pid_extractor import llm_vision

ROOT = Path(__file__).resolve().parent
SAMPLE_PDF = ROOT / "samples" / "pid_demo.pdf"
SAMPLE_TRUTH = ROOT / "samples" / "pid_demo_verite_terrain.json"

COLORS = {  # RVB 0-1 pour PyMuPDF
    "equipement": (0.13, 0.39, 0.85),
    "instrument": (0.10, 0.60, 0.33),
    "ligne": (0.93, 0.55, 0.10),
    "anomalie": (0.86, 0.15, 0.20),
}

st.set_page_config(page_title="Extraction PID – prototype", page_icon="🛠️", layout="wide")


def annotated_png(pdf_path: Path, result, checks: pd.DataFrame, zoom: float = 1.5) -> bytes:
    """Rend la page 1 avec un repère de couleur sur chaque élément détecté."""
    flagged = set(checks["objet"]) if not checks.empty else set()
    with pymupdf.open(pdf_path) as doc:
        page = doc[0]

        def mark(x, y, color, r=13):
            page.draw_circle((x, y), r, color=color, width=2.2)

        for e in result.equipments:
            mark(e["x"], e["y"], COLORS["anomalie"] if e["repere"] in flagged else COLORS["equipement"], 22)
        for i in result.instruments:
            mark(i["x"], i["y"] + 7, COLORS["anomalie"] if i["repere"] in flagged else COLORS["instrument"], 19)
        for l in result.lines:
            mark(l["x"], l["y"], COLORS["anomalie"] if l["numero_ligne"] in flagged else COLORS["ligne"], 16)
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")


# ------------------------------------------------------------------ barre latérale
st.sidebar.title("Paramètres")
source = st.sidebar.radio("PID à analyser", ["PID de démonstration", "Importer un PDF"])
uploaded = None
if source == "Importer un PDF":
    uploaded = st.sidebar.file_uploader("PID au format PDF", type=["pdf"])

mode = st.sidebar.radio(
    "Méthode d'extraction",
    ["Règles ISA (local, sans IA générative)", "IA vision (Azure OpenAI / OpenAI)"],
    help="Le mode règles fonctionne hors ligne sur les PDF vectoriels. "
         "Le mode IA vision lit l'image : utile pour les plans scannés.",
)
if mode.startswith("IA") and not llm_vision.is_configured():
    st.sidebar.warning("Mode IA vision : aucune clé API configurée (voir README). "
                       "Le mode règles sera utilisé.")

st.sidebar.markdown("---")
st.sidebar.caption("Légende du plan annoté")
st.sidebar.markdown(
    "🔵 Équipement &nbsp; 🟢 Instrument  \n🟠 Ligne &nbsp; 🔴 Anomalie détectée"
)

# ------------------------------------------------------------------ chargement
st.title("Extraction automatique d'informations à partir d'un PID")
st.caption("Prototype : du PID au format PDF vers les listes d'équipements, d'instruments et de lignes, "
           "avec contrôles de cohérence automatiques.")

if source == "PID de démonstration":
    pdf_path, truth = SAMPLE_PDF, json.loads(SAMPLE_TRUTH.read_text(encoding="utf-8"))
elif uploaded is not None:
    tmp = Path(tempfile.gettempdir()) / f"pid_upload_{uploaded.name}"
    tmp.write_bytes(uploaded.getvalue())
    pdf_path, truth = tmp, None
else:
    st.info("Importez un PID au format PDF dans la barre latérale, ou choisissez le PID de démonstration.")
    st.stop()

start = time.perf_counter()
connections: list[dict] = []
if mode.startswith("IA") and llm_vision.is_configured():
    from pid_extractor import render_page_png

    with st.spinner("Lecture du plan par l'IA…"):
        result, connections = llm_vision.extract_with_llm(render_page_png(pdf_path), source=pdf_path.name)
else:
    result = extract_pdf(pdf_path)
loops = build_loops(result)
checks = run_checks(result)
elapsed = time.perf_counter() - start

# ------------------------------------------------------------------ indicateurs
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Équipements", len(result.equipments))
c2.metric("Instruments", len(result.instruments))
c3.metric("Lignes", len(result.lines))
c4.metric("Boucles", len(loops))
c5.metric("Anomalies", len(checks), delta=None)
c6.metric("Temps d'analyse", f"{elapsed:.2f} s")

tabs = st.tabs(["Plan annoté", "Équipements", "Instruments", "Lignes", "Boucles", "Contrôles"]
               + (["Précision"] if truth else []) + (["Connexions"] if connections else []))

with tabs[0]:
    if result.equipments or result.instruments:
        st.image(annotated_png(pdf_path, result, checks), use_container_width=True)
    else:
        st.warning("Aucun texte détecté : ce PDF est probablement un scan. Essayez le mode IA vision.")

with tabs[1]:
    st.dataframe(pd.DataFrame(result.equipments).drop(columns=["page", "x", "y"], errors="ignore"),
                 use_container_width=True, hide_index=True)
with tabs[2]:
    df = pd.DataFrame(result.instruments)
    if not df.empty:
        st.dataframe(df[["repere", "type", "grandeur", "boucle", "lu_dans", "page"]],
                     use_container_width=True, hide_index=True)
with tabs[3]:
    st.dataframe(pd.DataFrame(result.lines).drop(columns=["page", "x", "y"], errors="ignore"),
                 use_container_width=True, hide_index=True)
with tabs[4]:
    st.dataframe(loops, use_container_width=True, hide_index=True)
with tabs[5]:
    if checks.empty:
        st.success("Aucune anomalie détectée.")
    else:
        for row in checks.itertuples():
            box = st.error if row.gravite == "Erreur" else st.warning
            box(f"**{row.controle}** — `{row.objet}` : {row.detail}")

if truth:
    with tabs[6]:
        st.markdown("Comparaison avec le relevé fait à la main (vérité terrain) :")
        st.dataframe(evaluate(result, checks, truth), use_container_width=True, hide_index=True)
        st.caption("Le PID de démonstration est un PDF vectoriel propre. Sur de vrais PID (symboles propres "
                   "à chaque client, plans scannés), il faut s'attendre à un taux plus faible : "
                   "c'est ce qu'il faudra mesurer sur un échantillon de PID réels.")
if connections:
    with tabs[-1]:
        st.dataframe(pd.DataFrame(connections), use_container_width=True, hide_index=True)

st.download_button(
    "📥 Télécharger les listes (Excel)",
    data=to_excel(result, loops, checks),
    file_name=f"listes_{Path(result.source).stem}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
