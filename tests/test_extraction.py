import json
from pathlib import Path

import pytest

from pid_extractor import build_loops, evaluate, extract_pdf, run_checks, to_excel
from pid_extractor import isa

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "pid_demo.pdf"


@pytest.fixture(scope="module")
def result():
    if not SAMPLE.exists():
        import generate_sample_pid

        generate_sample_pid.main()
    return extract_pdf(SAMPLE)


def test_isa_parsing():
    assert isa.parse_instrument("FIC-103").kind == "Régulateur"
    assert isa.parse_instrument("FV-103").kind == "Vanne de régulation"
    assert isa.parse_instrument("PSV-105").kind == "Soupape de sécurité"
    assert isa.parse_instrument("LSHH-101").kind == "Seuil très haut"
    assert isa.parse_instrument("HV-001").kind == "Vanne manuelle"
    assert isa.parse_instrument("TK-101") is None  # c'est un équipement, pas un instrument
    assert isa.parse_equipment("P-101A")["type"] == "Pompe"
    line = isa.parse_line('2"-S-2001-B2A-IH')
    assert line["fluide"] == "Vapeur" and line["classe_tuyauterie"] == "B2A" and line["isolation"] == "IH"


def test_bubbles_are_reassembled(result):
    tags = {i["repere"] for i in result.instruments}
    assert {"FT-103", "FIC-103", "FV-103", "TIC-104", "AIC-106"} <= tags


def test_equipment_descriptions(result):
    desc = {e["repere"]: e["description"] for e in result.equipments}
    assert desc["TK-101"] == "Cuve de stockage"
    assert desc["R-101"] == "Réacteur agité"


def test_loops(result):
    loops = build_loops(result).set_index("boucle")
    assert loops.loc["F-103", "role"] == "Boucle de régulation"
    assert loops.loc["F-103", "instruments"] == "FIC-103, FT-103, FV-103"


def test_intentional_anomalies_are_found(result):
    checks = run_checks(result)
    found = set(zip(checks["controle"], checks["objet"]))
    assert ("Repère en double", "TT-104") in found
    assert ("Régulateur sans vanne", "AIC-106") in found
    assert ("Ligne sans classe de tuyauterie", '1"-V-3001') in found
    assert ("Régulateur sans vanne", "FIC-103") not in found  # boucle complète : pas de fausse alerte


def test_evaluation_and_export(result):
    truth = json.loads((ROOT / "samples" / "pid_demo_verite_terrain.json").read_text(encoding="utf-8"))
    checks = run_checks(result)
    scores = evaluate(result, checks, truth).set_index("categorie")
    assert (scores["rappel_%"] == 100).all()
    xlsx = to_excel(result, build_loops(result), checks)
    assert xlsx[:2] == b"PK"  # un fichier .xlsx est une archive zip
