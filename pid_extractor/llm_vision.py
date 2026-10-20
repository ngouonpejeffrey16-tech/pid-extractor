"""Mode « IA vision » (optionnel) : un LLM multimodal lit directement l'image du PID.

Utile quand le PID est scanné (pas de texte dans le PDF) ou pour récupérer ce que
les règles ne voient pas, comme les connexions entre équipements.

Fonctionne avec :
- Azure OpenAI (recommandé en entreprise : les données restent dans le tenant) :
  AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT (ex. gpt-4o)
- OpenAI : OPENAI_API_KEY (et OPENAI_MODEL, par défaut gpt-4o)

Ne jamais envoyer de PID client vers un service public sans accord : en entreprise,
utiliser l'environnement Azure de la société.
"""

from __future__ import annotations

import base64
import json
import os

from . import isa
from .extract import ExtractionResult

PROMPT = """Tu es ingénieur procédé. Analyse ce schéma PID (P&ID) et renvoie UNIQUEMENT un JSON :
{
  "equipements": [{"repere": "TK-101", "description": "Cuve de stockage"}],
  "instruments": [{"repere": "FIC-103"}],
  "lignes": [{"numero_ligne": "3\\"-P-1002-A1A"}],
  "connexions": [{"de": "TK-101", "vers": "P-101A", "ligne": "4\\"-P-1001-A1A"}]
}
Règles : les repères d'instruments sont dans des bulles (lettres en haut, numéro en bas) :
assemble-les sous la forme LETTRES-NUMÉRO. N'invente rien : si un texte est illisible, ignore-le."""


def is_configured() -> bool:
    return bool(os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY"))


def _client():
    try:
        from openai import AzureOpenAI, OpenAI
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Installez le paquet openai : pip install openai") from exc
    if os.getenv("AZURE_OPENAI_API_KEY"):
        client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )
        return client, os.environ["AZURE_OPENAI_DEPLOYMENT"]
    return OpenAI(), os.getenv("OPENAI_MODEL", "gpt-4o")


def extract_with_llm(png_bytes: bytes, source: str = "image") -> tuple[ExtractionResult, list[dict]]:
    """Envoie l'image au LLM et renvoie le même format que l'extraction par règles,
    plus la liste des connexions détectées."""
    client, model = _client()
    image_b64 = base64.b64encode(png_bytes).decode()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}", "detail": "high"}},
            ],
        }],
    )
    data = json.loads(response.choices[0].message.content)

    result = ExtractionResult(source=source, page_count=1)
    for e in data.get("equipements", []):
        if parsed := isa.parse_equipment(e.get("repere", "")):
            parsed.update(description=e.get("description", ""), page=1, x=0, y=0)
            result.equipments.append(parsed)
    for i in data.get("instruments", []):
        if info := isa.parse_instrument(i.get("repere", "")):
            result.instruments.append({
                "repere": info.tag, "type": info.kind, "grandeur": info.variable, "boucle": info.loop,
                "lettres": info.letters, "lu_dans": "IA vision", "page": 1, "x": 0, "y": 0,
            })
    for l in data.get("lignes", []):
        if parsed := isa.parse_line(l.get("numero_ligne", "")):
            parsed.update(page=1, x=0, y=0)
            result.lines.append(parsed)
    return result, data.get("connexions", [])
