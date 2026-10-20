"""Export Excel des listes issues du PID (le livrable que les équipes réutilisent)."""

from __future__ import annotations

import io

import pandas as pd

from .extract import ExtractionResult


def to_excel(result: ExtractionResult, loops: pd.DataFrame, checks: pd.DataFrame) -> bytes:
    sheets = {
        "Équipements": pd.DataFrame(result.equipments).drop(columns=["page", "x", "y"], errors="ignore"),
        "Instruments": pd.DataFrame(result.instruments).drop(columns=["x", "y", "lettres"], errors="ignore"),
        "Lignes": pd.DataFrame(result.lines).drop(columns=["page", "x", "y"], errors="ignore"),
        "Boucles": loops,
        "Contrôles": checks,
    }
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, sheet_name=name, index=False)
            ws = writer.sheets[name]
            for col in ws.columns:  # largeur de colonne adaptée au contenu
                width = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 10), 60)
            ws.freeze_panes = "A2"
    return buffer.getvalue()
