"""Utilisation en ligne de commande.

    python cli.py samples/pid_demo.pdf
    python cli.py mon_pid.pdf --excel listes.xlsx
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from pid_extractor import build_loops, evaluate, extract_pdf, run_checks, to_excel


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraction automatique d'informations d'un PID (PDF)")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--excel", type=Path, help="Chemin du fichier Excel à produire")
    parser.add_argument("--verite", type=Path, help="Relevé manuel JSON pour mesurer la précision")
    args = parser.parse_args()

    start = time.perf_counter()
    result = extract_pdf(args.pdf)
    loops, checks = build_loops(result), run_checks(result)
    elapsed = time.perf_counter() - start

    print(f"\nPID analysé : {result.source}  ({elapsed:.2f} s)")
    print(f"  Équipements : {len(result.equipments)}")
    print(f"  Instruments : {len(result.instruments)}")
    print(f"  Lignes      : {len(result.lines)}")
    print(f"  Boucles     : {len(loops)}")
    print(f"  Anomalies   : {len(checks)}")
    for row in checks.itertuples():
        print(f"    [{row.gravite}] {row.controle} – {row.objet}")

    truth_path = args.verite or args.pdf.with_name(args.pdf.stem + "_verite_terrain.json")
    if truth_path.exists():
        print("\nPrécision par rapport au relevé manuel :")
        print(evaluate(result, checks, json.loads(truth_path.read_text(encoding="utf-8"))).to_string(index=False))

    excel = args.excel or Path(f"listes_{args.pdf.stem}.xlsx")
    excel.write_bytes(to_excel(result, loops, checks))
    print(f"\nListes exportées : {excel}")


if __name__ == "__main__":
    main()
