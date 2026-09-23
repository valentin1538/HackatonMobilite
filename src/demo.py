"""Démo en ligne de commande : interroge l'API IDFM et affiche les itinéraires enrichis.

Usage :
    python src/demo.py
    python src/demo.py --depart "Nation" --arrivee "Saint-Lazare"
    python src/demo.py --heure 18:30
    python src/demo.py --raw          # ajoute le JSON brut du 1er itinéraire
"""

import sys
import json
import argparse
import os
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))
from enricher import enrich_journeys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

load_dotenv()

BASE_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"

ICONES_AFFLUENCE = {
    "VERY_HIGH": "👥👥", "HIGH": "👥", "MEDIUM": "🚶", "LOW": "✅", "VERY_LOW": "🌙",
}
ICONES_CLIM = {"total": "🌡️✅", "partiel": "🌡️~", "aucune": "🌡️❌", "inconnu": "🌡️?"}


# ─── Appels API ──────────────────────────────────────────────────────────────

def search_place(query: str, headers: dict) -> dict | None:
    """Cherche une station par nom et retourne le premier résultat."""
    resp = requests.get(
        f"{BASE_URL}/places",
        headers=headers,
        params={"q": query, "type[]": "stop_area", "count": 1},
    )
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        print(f"Aucune station trouvée pour : {query}")
        return None
    return places[0]


def get_journeys(from_id: str, to_id: str, dt: str, headers: dict, count: int = 3) -> list:
    """Appelle /journeys et retourne les itinéraires bruts."""
    resp = requests.get(
        f"{BASE_URL}/journeys",
        headers=headers,
        params={
            "from":              from_id,
            "to":                to_id,
            "datetime":          dt,
            "data_freshness":    "realtime",
            "equipment_details": "true",
            "count":             count,
        },
    )
    resp.raise_for_status()
    return resp.json().get("journeys", [])


# ─── Affichage ───────────────────────────────────────────────────────────────

def afficher_itineraire(idx: int, result: dict):
    """Affiche un itinéraire enrichi avec ses dimensions de confort."""
    d = result["dimensions"]
    lignes_str = " → ".join(result["lignes"]) or "direct"

    print(f"{'━'*55}")
    print(f"Option {idx+1} — {lignes_str:<20}  {result['duree_min']} min")
    print(
        f"  {ICONES_AFFLUENCE.get(d['affluence']['niveau'], '👥')} {d['affluence']['label']:<22}"
        f"  {ICONES_CLIM.get(d['climatisation']['status'], '🌡️?')} {d['climatisation']['label']:<28}"
    )
    print(f"  🧭 Recommandation : {result['business_summary']['recommandation']}")

    print(f"  🔁 Correspondances : {d['correspondances']['nb']}")
    for c in d["correspondances"]["details"]:
        print(f"     └─ marche {c['duree_sec']}s ({c['mode']})")

    if d["accessibilite"]["pannes"]:
        stations_ko = ", ".join(p["station"] for p in d["accessibilite"]["pannes"])
        print(f"  ⚠️  Ascenseur en panne : {stations_ko}")
    else:
        print(f"  ✅ Accessible")

    print(
        f"  🚻 Toilettes : {'oui' if d['equipements']['toilettes'] else 'non':<6}"
        f"  🚰 Fontaines : {'oui' if d['equipements']['fontaines'] else 'non'}"
    )

    for p in result["perturbations"]:
        print(f"  ⚠️  [{p['severite']}] {p['message']}")

    if result["business_summary"]["alertes"]:
        print(f"  ⚠️  Alertes : {', '.join(result['business_summary']['alertes'])}")

    print(f"  ➜  Score confort : {result['score_confort']}/10")


# ─── Main ────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Interroge l'API IDFM et affiche les itinéraires enrichis."
    )
    parser.add_argument("--depart",  default="Vincennes",   help="station de départ")
    parser.add_argument("--arrivee", default="La Défense",  help="station d'arrivée")
    parser.add_argument("--heure",   default="08:30",       help="heure de départ (HH:MM)")
    parser.add_argument("--count",   type=int, default=3,   help="nombre d'itinéraires")
    parser.add_argument("--raw",     action="store_true",
                        help="affiche aussi le JSON brut du premier itinéraire")
    return parser.parse_args()


def main():
    args = parse_args()

    api_key = os.getenv("IDFM_API_KEY", "")
    if not api_key:
        raise SystemExit("IDFM_API_KEY manquante. Vérifie ton fichier .env.")
    headers = {"apikey": api_key}

    try:
        heure = datetime.strptime(args.heure, "%H:%M")
    except ValueError:
        raise SystemExit(f"Heure invalide : {args.heure} (format attendu HH:MM)")
    dt = datetime.now().replace(
        hour=heure.hour, minute=heure.minute, second=0
    ).strftime("%Y%m%dT%H%M%S")

    print(f"Recherche : {args.depart} → {args.arrivee} à {args.heure}\n")

    dep = search_place(args.depart, headers)
    arr = search_place(args.arrivee, headers)
    if not dep or not arr:
        raise SystemExit(1)

    print(f"Départ  : {dep['name']} ({dep['id']})")
    print(f"Arrivée : {arr['name']} ({arr['id']})")

    journeys = get_journeys(dep["id"], arr["id"], dt, headers, args.count)
    print(f"\n{len(journeys)} itinéraire(s) trouvé(s)\n")

    for idx, result in enumerate(enrich_journeys(journeys, dt)):
        afficher_itineraire(idx, result)
    print(f"{'━'*55}")

    if args.raw:
        print("\nRéponse brute du premier itinéraire (debug) :")
        print(json.dumps(journeys[0], indent=2, ensure_ascii=False)
              if journeys else "Aucun résultat")


if __name__ == "__main__":
    main()
