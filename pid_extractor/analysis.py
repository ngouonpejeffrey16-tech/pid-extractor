"""Analyse des données extraites : boucles de régulation, contrôles de cohérence
et mesure de la précision par rapport à un relevé manuel."""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from .extract import ExtractionResult

ERROR = "Erreur"
WARNING = "Avertissement"


def build_loops(result: ExtractionResult) -> pd.DataFrame:
    """Regroupe les instruments par boucle (même grandeur + même numéro : F-103 = FT, FIC, FV)."""
    loops: dict[str, list[dict]] = defaultdict(list)
    for ins in result.instruments:
        if ins["type"] in ("Vanne manuelle",):
            continue
        loops[ins["boucle"]].append(ins)

    rows = []
    for loop, members in sorted(loops.items()):
        kinds = {m["type"] for m in members}
        if "Régulateur" in kinds:
            role = "Boucle de régulation"
        elif "Soupape de sécurité" in kinds or any(k.startswith("Seuil") for k in kinds):
            role = "Sécurité / alarme"
        else:
            role = "Mesure"
        rows.append({
            "boucle": loop,
            "grandeur": members[0]["grandeur"],
            "role": role,
            "instruments": ", ".join(sorted({m["repere"] for m in members})),
            "nb_instruments": len(members),
        })
    return pd.DataFrame(rows)


def run_checks(result: ExtractionResult) -> pd.DataFrame:
    """Contrôles automatiques qu'un ingénieur ferait en relisant le PID."""
    issues = []

    # 1. Repères en double
    counts = Counter(i["repere"] for i in result.instruments) + Counter(e["repere"] for e in result.equipments)
    for tag, n in counts.items():
        if n > 1:
            issues.append((ERROR, "Repère en double", tag, f"Le repère apparaît {n} fois sur le plan."))

    # 2. Cohérence des boucles de régulation
    loops: dict[str, set[str]] = defaultdict(set)
    loop_tags: dict[str, list[str]] = defaultdict(list)
    for ins in result.instruments:
        loops[ins["boucle"]].add(ins["type"])
        loop_tags[ins["boucle"]].append(ins["repere"])
    for loop, kinds in loops.items():
        controllers = [t for t in loop_tags[loop] if "C" in t.split("-")[0][1:]]
        if "Régulateur" in kinds and "Vanne de régulation" not in kinds:
            issues.append((ERROR, "Régulateur sans vanne", controllers[0],
                           "Boucle de régulation sans organe de réglage (vanne) associé."))
        if "Vanne de régulation" in kinds and "Régulateur" not in kinds:
            valve = next(t for t in loop_tags[loop] if t.split("-")[0].endswith("V"))
            issues.append((ERROR, "Vanne sans régulateur", valve,
                           "Vanne de régulation sans régulateur associé."))
        if "Régulateur" in kinds and "Transmetteur" not in kinds:
            issues.append((WARNING, "Régulateur sans mesure", controllers[0],
                           "Aucun transmetteur trouvé pour cette boucle."))

    # 3. Lignes incomplètes
    for line in result.lines:
        if not line["classe_tuyauterie"]:
            issues.append((WARNING, "Ligne sans classe de tuyauterie", line["numero_ligne"],
                           "Classe de matériau non indiquée : impossible de spécifier la tuyauterie."))

    # 4. Plan sans texte exploitable
    if not result.has_text_layer:
        issues.append((WARNING, "Plan scanné", result.source,
                       "Aucun texte lisible : utiliser l'OCR ou le mode IA vision."))

    return pd.DataFrame(issues, columns=["gravite", "controle", "objet", "detail"])


def evaluate(result: ExtractionResult, checks: pd.DataFrame, truth: dict) -> pd.DataFrame:
    """Compare l'extraction au relevé manuel (vérité terrain) : rappel et précision par catégorie."""
    found = {
        "Équipements": {e["repere"] for e in result.equipments},
        "Instruments": {i["repere"] for i in result.instruments},
        "Lignes": {l["numero_ligne"] for l in result.lines},
        "Anomalies": {(r.controle, r.objet) for r in checks.itertuples()},
    }
    expected = {
        "Équipements": set(truth["equipements"]),
        "Instruments": set(truth["instruments"]),
        "Lignes": set(truth["lignes"]),
        "Anomalies": {(a["type"], a["objet"]) for a in truth["anomalies_attendues"]},
    }
    rows = []
    for cat in found:
        f, e = found[cat], expected[cat]
        ok = len(f & e)
        rows.append({
            "categorie": cat,
            "attendus": len(e),
            "trouves": len(f),
            "corrects": ok,
            "rappel_%": round(100 * ok / len(e), 1) if e else 100.0,
            "precision_%": round(100 * ok / len(f), 1) if f else 100.0,
            "manquants": ", ".join(sorted(map(str, e - f))) or "—",
        })
    return pd.DataFrame(rows)
