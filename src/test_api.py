import sys
import requests
import json
import os
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
from dotenv import load_dotenv

from src.enricher import enrich_journeys

load_dotenv()

# --- Configuration ---
API_KEY  = os.getenv("IDFM_API_KEY", "")
BASE_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
HEADERS  = {"apikey": API_KEY}

if not API_KEY:
    raise ValueError("IDFM_API_KEY manquante. Vérifie ton fichier .env.")


# --- Fonctions ---

def search_place(query: str) -> dict | None:
    """Cherche une station par nom et retourne le premier résultat."""
    resp = requests.get(
        f"{BASE_URL}/places",
        headers=HEADERS,
        params={"q": query, "type[]": "stop_area", "count": 1}
    )
    resp.raise_for_status()
    places = resp.json().get("places", [])
    if not places:
        print(f"Aucune station trouvée pour : {query}")
        return None
    return places[0]


def get_journeys(from_id: str, to_id: str, dt: str) -> list:
    """Appelle /journeys et retourne les itinéraires bruts."""
    resp = requests.get(
        f"{BASE_URL}/journeys",
        headers=HEADERS,
        params={
            "from":              from_id,
            "to":                to_id,
            "datetime":          dt,
            "data_freshness":    "realtime",
            "equipment_details": "true",
            "count":             3,
        }
    )
    resp.raise_for_status()
    return resp.json().get("journeys", [])


def extract_comfort_data(journey: dict) -> dict:
    """Extrait les données utiles pour le score de confort depuis un itinéraire."""
    comfort = {
        "duree_totale_min": journey.get("duration", 0) // 60,
        "nb_correspondances": journey.get("nb_transfers", 0),
        "correspondances":    [],
        "ascenseurs":         [],
        "perturbations":      [],
    }

    for section in journey.get("sections", []):
        # Correspondances — durée et distance
        if section.get("type") == "transfer":
            comfort["correspondances"].append({
                "duree_sec":  section.get("duration", 0),
                "mode":       section.get("transfer_type", "inconnu"),
            })

        # Accessibilité — statut des équipements
        if section.get("type") == "public_transport":
            for sdt in section.get("stop_date_times", []):
                eq = sdt.get("equipment_availability", {})
                if eq:
                    comfort["ascenseurs"].append({
                        "station":    sdt.get("stop_point", {}).get("name", "?"),
                        "ascenseur":  eq.get("elevator", "inconnu"),
                        "fauteuil":   eq.get("wheelchair_boarding", "inconnu"),
                    })

    # Perturbations actives sur ce trajet
    for disruption in journey.get("disruptions", []):
        comfort["perturbations"].append({
            "severite": disruption.get("severity", {}).get("name", "?"),
            "message":  disruption.get("messages", [{}])[0].get("text", "?")
                        if disruption.get("messages") else "—",
        })

    return comfort


def afficher_itineraire(idx: int, journey: dict, enriched: dict):
    """Affiche un itinéraire et ses données de confort métier."""
    sections = journey.get("sections", [])
    lignes = [
        s.get("display_informations", {}).get("label", "")
        for s in sections
        if s.get("type") == "public_transport"
    ]

    print(f"\n{'━'*50}")
    print(f"Option {idx + 1} — {' → '.join(lignes) or 'trajet direct'}")
    print(f"  Durée          : {enriched['duree_min']} min")
    print(f"  Correspondances: {enriched['nb_correspondances']}")
    print(f"  Recommandation : {enriched['business_summary']['recommandation']}")

    if enriched['dimensions']['correspondances']['details']:
        for c in enriched['dimensions']['correspondances']['details']:
            print(f"    └─ Marche {c['duree_sec']}s ({c['mode']})")

    if enriched["perturbations"]:
        for p in enriched["perturbations"]:
            print(f"  ⚠️  [{p['severite']}] {p['message']}")

    if not enriched['dimensions']['accessibilite']['ok']:
        stations_ko = [p['station'] for p in enriched['dimensions']['accessibilite']['pannes']]
        print(f"  ⚠️  Ascenseur indisponible : {', '.join(stations_ko)}")
    else:
        print(f"  ✅  Accessibilité OK")

    if enriched['business_summary']['alertes']:
        print(f"  ⚠️  Alertes : {', '.join(enriched['business_summary']['alertes'])}")


# --- Main ---

if __name__ == "__main__":
    DEPART  = "Vincennes"
    ARRIVEE = "La Défense"
    HEURE   = datetime.now().strftime("%Y%m%dT083000")

    print(f"Recherche : {DEPART} → {ARRIVEE} à 8h30\n")

    dep = search_place(DEPART)
    arr = search_place(ARRIVEE)

    if not dep or not arr:
        exit(1)

    print(f"Départ  : {dep['name']} ({dep['id']})")
    print(f"Arrivée : {arr['name']} ({arr['id']})")

    journeys = get_journeys(dep["id"], arr["id"], HEURE)
    print(f"\n{len(journeys)} itinéraire(s) trouvé(s)")

    enriched_journeys = enrich_journeys(journeys, HEURE)
    for idx, journey in enumerate(enriched_journeys):
        afficher_itineraire(idx, journeys[idx], journey)

    print(f"\n{'━'*50}")
    print("\nRéponse brute du premier itinéraire (pour debug) :")
    print(json.dumps(journeys[0], indent=2, ensure_ascii=False) if journeys else "Aucun résultat")
