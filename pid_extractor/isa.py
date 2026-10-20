"""Règles de lecture des repères de PID (norme ISA 5.1 et conventions courantes).

Ce module ne dépend d'aucune bibliothèque : il transforme un texte comme « FIC-103 »
ou « 3"-P-1002-A1A » en une information structurée et lisible par un ingénieur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# 1re lettre d'un repère d'instrument : la grandeur mesurée
MEASURED_VARIABLE = {
    "A": "Analyse",
    "F": "Débit",
    "H": "Commande manuelle",
    "L": "Niveau",
    "P": "Pression",
    "S": "Vitesse",
    "T": "Température",
    "V": "Vibration",
    "W": "Poids",
    "Z": "Position",
}

# Lettres suivantes : la fonction de l'instrument
FUNCTION_LETTERS = {
    "A": "alarme",
    "C": "régulation",
    "E": "élément sensible",
    "G": "voyant",
    "H": "haut",
    "I": "indication",
    "L": "bas",
    "R": "enregistrement",
    "S": "seuil / sécurité",
    "T": "transmission",
    "V": "vanne",
    "Y": "relais / calcul",
}

# Préfixes d'équipements (convention la plus répandue, adaptable à chaque client)
EQUIPMENT_PREFIX = {
    "TK": "Cuve / réservoir",
    "P": "Pompe",
    "E": "Échangeur de chaleur",
    "R": "Réacteur",
    "V": "Ballon / récipient",
    "C": "Colonne",
    "K": "Compresseur",
    "F": "Filtre",
    "M": "Agitateur / moteur",
}

# Codes fluides des numéros de ligne
FLUID_CODES = {
    "P": "Procédé",
    "S": "Vapeur",
    "C": "Condensats",
    "V": "Évent",
    "CW": "Eau de refroidissement",
    "N": "Azote",
    "A": "Air",
    "D": "Vidange",
}

EQUIPMENT_RE = re.compile(r"^(TK|P|E|R|V|C|K|F|M)-(\d{3})([A-Z]?)$")
INSTRUMENT_RE = re.compile(r"^([A-Z]{2,5})-(\d{3,4})([A-Z]?)$")
LINE_RE = re.compile(
    r'^(?P<diam>\d+(?:[.,]\d+)?)"-(?P<fluid>[A-Z]{1,3})-(?P<num>\d{3,5})'
    r"(?:-(?P<spec>[A-Z]\d[A-Z]))?(?:-(?P<insul>[A-Z]{1,3}))?$"
)
ISA_LETTERS_RE = re.compile(r"^[A-Z]{1,5}$")
LOOP_NUMBER_RE = re.compile(r"^\d{3,4}[A-Z]?$")


@dataclass
class InstrumentInfo:
    tag: str
    letters: str
    loop: str
    variable: str
    kind: str


def is_isa_letters(text: str) -> bool:
    """Vrai si le texte ressemble au code lettres d'une bulle d'instrument (ex. « FIC »)."""
    if not ISA_LETTERS_RE.match(text) or len(text) < 2:
        return False
    return text[0] in MEASURED_VARIABLE and all(c in FUNCTION_LETTERS for c in text[1:])


def instrument_kind(letters: str) -> str:
    """Traduit les lettres ISA en type d'instrument compréhensible."""
    first, rest = letters[0], letters[1:]
    if first == "P" and rest.startswith("S") and rest.endswith("V"):
        return "Soupape de sécurité"
    if first == "H" and rest.endswith("V"):
        return "Vanne manuelle"
    if rest.endswith("V") or rest.endswith("CV"):
        return "Vanne de régulation"
    if "C" in rest:
        return "Régulateur"
    if rest.startswith("S"):
        levels = rest[1:]
        if levels.startswith("HH"):
            return "Seuil très haut"
        if levels.startswith("LL"):
            return "Seuil très bas"
        if levels.startswith("H"):
            return "Seuil haut"
        if levels.startswith("L"):
            return "Seuil bas"
        return "Contact / seuil"
    if rest.endswith("T"):
        return "Transmetteur"
    if rest.endswith("E"):
        return "Élément sensible"
    if "I" in rest:
        return "Indicateur"
    return "Instrument"


def parse_instrument(tag: str) -> InstrumentInfo | None:
    m = INSTRUMENT_RE.match(tag)
    if not m:
        return None
    letters, number, suffix = m.groups()
    if not is_isa_letters(letters):
        return None
    return InstrumentInfo(
        tag=tag,
        letters=letters,
        loop=f"{letters[0]}-{number}",
        variable=MEASURED_VARIABLE[letters[0]],
        kind=instrument_kind(letters),
    )


def parse_equipment(tag: str) -> dict | None:
    m = EQUIPMENT_RE.match(tag)
    if not m:
        return None
    prefix, number, suffix = m.groups()
    return {"repere": tag, "type": EQUIPMENT_PREFIX[prefix], "numero": number, "variante": suffix or ""}


def parse_line(text: str) -> dict | None:
    m = LINE_RE.match(text)
    if not m:
        return None
    d = m.groupdict()
    return {
        "numero_ligne": text,
        "diametre_pouces": float(d["diam"].replace(",", ".")),
        "fluide": FLUID_CODES.get(d["fluid"], d["fluid"]),
        "numero": d["num"],
        "classe_tuyauterie": d["spec"] or "",
        "isolation": d["insul"] or "",
    }
