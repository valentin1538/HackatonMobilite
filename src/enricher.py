import sys
import json
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = Path(__file__).parent.parent / "data"

_DATASETS = None


def _load():
    global _DATASETS
    if _DATASETS:
        return _DATASETS

    affluence_data = json.loads((DATA_DIR / "affluence.json").read_text(encoding="utf-8"))
    clim_data = json.loads((DATA_DIR / "climatisation.json").read_text(encoding="utf-8"))
    fontaines_raw = json.loads(
        (DATA_DIR / "fontaines-a-eau-dans-le-reseau-ratp.json").read_text(encoding="utf-8")
    )
    sanitaires_raw = json.loads(
        (DATA_DIR / "sanitaires-reseau-ratp.json").read_text(encoding="utf-8")
    )

    fontaines_idx = {}
    for f in fontaines_raw:
        fontaines_idx.setdefault(_norm(f["station_ou_gare"]), []).append(f)

    sanitaires_idx = {}
    for s in sanitaires_raw:
        sanitaires_idx.setdefault(_norm(s["station"]), []).append(s)

    _DATASETS = (affluence_data, clim_data, fontaines_idx, sanitaires_idx)
    return _DATASETS


def _norm(name: str) -> str:
    name = name.lower().strip()
    for prefix in ["métro ", "rer ", "gare de ", "gare du ", "gare "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.strip()


# ─── Dimension : Affluence ──────────────────────────────────────────────────

def _score_affluence(heure: int, station_names: list, affluence_data: dict) -> dict:
    slot = next(
        (s for s in affluence_data["creneaux_horaires"] if s["debut"] <= heure < s["fin"]),
        affluence_data["creneaux_horaires"][0],
    )

    poids = 1
    poids_data = affluence_data["poids_stations"]
    for name in station_names:
        nn = _norm(name)
        for cat_key, cat in poids_data.items():
            if cat_key == "default":
                continue
            if any(_norm(s) == nn for s in cat.get("stations", [])):
                poids = max(poids, cat["poids"])

    facteur = {1: 1.0, 2: 0.8, 3: 0.6}.get(poids, 1.0)
    score = round(min(10.0, max(0.0, slot["score"] * facteur)), 1)

    return {
        "niveau": slot["niveau"],
        "label": slot["label"],
        "poids_station": poids,
        "score": score,
    }


# ─── Dimension : Climatisation ──────────────────────────────────────────────

def _score_climatisation(lignes: list, clim_data: dict) -> dict:
    if not lignes:
        return {"status": "inconnu", "label": "Inconnu", "lignes": [], "score": clim_data["default"]["score"]}

    labels = {"total": "Climatisé", "partiel": "Partiellement climatisé", "aucune": "Non climatisé", "inconnu": "Inconnu"}
    details = []
    for ligne in lignes:
        info = clim_data["lignes"].get(ligne, clim_data["default"])
        details.append({"ligne": ligne, "clim": info["clim"], "score": info["score"]})

    pire = min(details, key=lambda d: d["score"])

    return {
        "status": pire["clim"],
        "label": labels.get(pire["clim"], "Inconnu"),
        "lignes": details,
        "score": pire["score"],
    }


# ─── Dimension : Accessibilité ──────────────────────────────────────────────

def _score_accessibilite(sections: list) -> dict:
    pannes = []
    nb_checked = 0

    for section in sections:
        if section.get("type") != "public_transport":
            continue
        for sdt in section.get("stop_date_times", []):
            eq = sdt.get("equipment_availability", {})
            if not eq:
                continue
            nb_checked += 1
            status = eq.get("elevator", "unknown")
            if status not in ("available", "unknown"):
                pannes.append({
                    "station": sdt.get("stop_point", {}).get("name", "?"),
                    "status": status,
                })

    if not pannes:
        score = 10 if nb_checked > 0 else 7
    else:
        score = max(0, 10 - len(pannes) * 3)

    return {"ok": len(pannes) == 0, "pannes": pannes, "nb_checked": nb_checked, "score": score}


# ─── Dimension : Correspondances ────────────────────────────────────────────

def _score_correspondances(sections: list) -> dict:
    transfers = [
        {"duree_sec": s.get("duration", 0), "mode": s.get("transfer_type", "walk")}
        for s in sections
        if s.get("type") == "transfer"
    ]

    if not transfers:
        return {"nb": 0, "max_duree_sec": 0, "details": [], "score": 10}

    max_dur = max(t["duree_sec"] for t in transfers)

    if max_dur < 120:
        score = 9
    elif max_dur < 300:
        score = 7
    elif max_dur < 600:
        score = 5
    else:
        score = 3

    return {"nb": len(transfers), "max_duree_sec": max_dur, "details": transfers, "score": score}


# ─── Dimension : Équipements ────────────────────────────────────────────────

def _score_equipements(station_names: list, fontaines_idx: dict, sanitaires_idx: dict) -> dict:
    toilettes = any(_norm(n) in sanitaires_idx for n in station_names)
    fontaines = any(_norm(n) in fontaines_idx for n in station_names)

    if toilettes and fontaines:
        score = 10
    elif toilettes:
        score = 7
    elif fontaines:
        score = 5
    else:
        score = 2

    return {"toilettes": toilettes, "fontaines": fontaines, "score": score}


# ─── Point d'entrée public ──────────────────────────────────────────────────

def enrich(journey: dict, departure_dt: str) -> dict:
    """
    Enrichit un itinéraire brut de l'API IDFM avec les 4 dimensions de confort.
    Toutes les dimensions sont toujours retournées.

    Args:
        journey:      itinéraire brut tel que retourné par GET /journeys
        departure_dt: heure de départ au format "YYYYMMDDThhmmss"

    Returns:
        dict {duree_min, lignes, perturbations, dimensions, score_confort}
        Formule : affluence×0.35 + accessibilité×0.30 + correspondances×0.20 + équipements×0.15
    """
    affluence_data, clim_data, fontaines_idx, sanitaires_idx = _load()

    sections = journey.get("sections", [])

    lignes = []
    station_names = []
    for s in sections:
        if s.get("type") != "public_transport":
            continue
        label = s.get("display_informations", {}).get("label", "")
        if label and label not in lignes:
            lignes.append(label)
        for sdt in s.get("stop_date_times", []):
            name = sdt.get("stop_point", {}).get("name")
            if name and name not in station_names:
                station_names.append(name)

    try:
        heure = int(departure_dt[9:11])
    except (ValueError, IndexError):
        heure = datetime.now().hour

    aff  = _score_affluence(heure, station_names, affluence_data)
    clim = _score_climatisation(lignes, clim_data)
    acc  = _score_accessibilite(sections)
    corr = _score_correspondances(sections)
    equip = _score_equipements(station_names, fontaines_idx, sanitaires_idx)

    score_confort = round(
        aff["score"]   * 0.35 +
        acc["score"]   * 0.30 +
        corr["score"]  * 0.20 +
        equip["score"] * 0.15,
        1,
    )

    return {
        "duree_min":        journey.get("duration", 0) // 60,
        "nb_correspondances": journey.get("nb_transfers", 0),
        "lignes":           lignes,
        "perturbations": [
            {
                "severite": d.get("severity", {}).get("name", "?"),
                "message":  d.get("messages", [{}])[0].get("text", "?") if d.get("messages") else "—",
            }
            for d in journey.get("disruptions", [])
        ],
        "dimensions": {
            "affluence":      aff,
            "climatisation":  clim,
            "accessibilite":  acc,
            "correspondances": corr,
            "equipements":    equip,
        },
        "score_confort": score_confort,
    }


# ─── Demo ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import requests
    from dotenv import load_dotenv

    load_dotenv()
    API_KEY  = os.getenv("IDFM_API_KEY", "")
    BASE_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"
    HEADERS  = {"apikey": API_KEY}

    if not API_KEY:
        raise ValueError("IDFM_API_KEY manquante. Vérifie ton fichier .env.")

    DEPART  = "Vincennes"
    ARRIVEE = "La Défense"
    DT      = datetime.now().strftime("%Y%m%dT083000")

    def _get_id(query):
        r = requests.get(f"{BASE_URL}/places", headers=HEADERS,
                         params={"q": query, "type[]": "stop_area", "count": 1})
        r.raise_for_status()
        places = r.json().get("places", [])
        return places[0]["id"] if places else None

    dep_id = _get_id(DEPART)
    arr_id = _get_id(ARRIVEE)
    if not dep_id or not arr_id:
        print("Station introuvable.")
        raise SystemExit(1)

    r = requests.get(f"{BASE_URL}/journeys", headers=HEADERS,
                     params={"from": dep_id, "to": arr_id, "datetime": DT,
                             "data_freshness": "realtime", "equipment_details": "true", "count": 3})
    r.raise_for_status()
    journeys = r.json().get("journeys", [])

    print(f"Recherche : {DEPART} → {ARRIVEE}  |  {len(journeys)} itinéraire(s)\n")

    ICONES = {
        "VERY_HIGH": "👥👥", "HIGH": "👥", "MEDIUM": "🚶", "LOW": "✅", "VERY_LOW": "🌙",
    }
    CLIM_ICONE = {"total": "🌡️✅", "partiel": "🌡️~", "aucune": "🌡️❌", "inconnu": "🌡️?"}

    for idx, journey in enumerate(journeys):
        result = enrich(journey, DT)
        d = result["dimensions"]
        lignes_str = " → ".join(result["lignes"]) or "direct"

        print(f"{'━'*55}")
        print(f"Option {idx+1} — {lignes_str:<20}  {result['duree_min']} min")
        print(
            f"  {ICONES.get(d['affluence']['niveau'], '👥')} {d['affluence']['label']:<22}"
            f"  {CLIM_ICONE.get(d['climatisation']['status'], '🌡️?')} {d['climatisation']['label']:<28}"
        )
        if d["accessibilite"]["pannes"]:
            print(f"  ⚠️  Ascenseur en panne : {', '.join(p['station'] for p in d['accessibilite']['pannes'])}")
        else:
            print(f"  ✅ Accessible")
        print(
            f"  🚻 Toilettes : {'oui' if d['equipements']['toilettes'] else 'non':<6}"
            f"  🚰 Fontaines : {'oui' if d['equipements']['fontaines'] else 'non'}"
        )
        if result["perturbations"]:
            for p in result["perturbations"]:
                print(f"  ⚠️  [{p['severite']}] {p['message']}")
        print(f"  ➜  Score confort : {result['score_confort']}/10")

    print(f"{'━'*55}")
