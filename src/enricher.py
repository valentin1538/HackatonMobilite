import sys
import json
import pickle
import unicodedata
import re
import requests as _requests
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR  = Path(__file__).parent.parent / "data"
MODEL_DIR = Path(__file__).parent.parent / "models"

_DATASETS = None
_MODEL    = None   # chargé une seule fois (lazy)
_AFFLUENCE_IDX = None  # index horaire réel (lazy)

# Coordonnées centre Paris pour l'API météo (lat, lon)
_PARIS_LAT = 48.8566
_PARIS_LON = 2.3522


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
    aeriennes_data = json.loads(
        (DATA_DIR / "stations_aeriennes.json").read_text(encoding="utf-8")
    )

    fontaines_idx = {}
    for f in fontaines_raw:
        fontaines_idx.setdefault(_norm(f["station_ou_gare"]), []).append(f)

    sanitaires_idx = {}
    for s in sanitaires_raw:
        sanitaires_idx.setdefault(_norm(s["station"]), []).append(s)

    aeriennes_idx = {_norm(k): v for k, v in aeriennes_data["stations"].items()}

    _DATASETS = (affluence_data, clim_data, fontaines_idx, sanitaires_idx, aeriennes_idx)
    return _DATASETS


def _load_model():
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    model_path = MODEL_DIR / "affluence_model.pkl"
    if model_path.exists():
        with open(model_path, "rb") as f:
            _MODEL = pickle.load(f)
    return _MODEL


def _load_affluence_idx():
    global _AFFLUENCE_IDX
    if _AFFLUENCE_IDX is not None:
        return _AFFLUENCE_IDX
    idx_path = DATA_DIR / "affluence_horaire.json"
    if idx_path.exists():
        _AFFLUENCE_IDX = json.loads(idx_path.read_text(encoding="utf-8"))
    return _AFFLUENCE_IDX


def _norm_station(name: str) -> str:
    """Normalisation pour le matching avec le dataset IDFM 2023."""
    name = name.upper().strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = re.sub(r"[^A-Z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


# Mapping jour_semaine → CAT_JOUR du dataset
_DOW_TO_CAT = {
    0: "JOHV", 1: "JOHV", 2: "JOHV", 3: "JOHV", 4: "JOHV",
    5: "SAHV",
    6: "DIJFP",
}


# ─── Météo (Open-Meteo, sans clé API) ──────────────────────────────────────

def _fetch_meteo() -> dict:
    try:
        r = _requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":            _PARIS_LAT,
                "longitude":           _PARIS_LON,
                "current":             "temperature_2m,precipitation,weathercode",
                "wind_speed_unit":     "ms",
                "forecast_days":       1,
            },
            timeout=5,
        )
        r.raise_for_status()
        c = r.json().get("current", {})
        return {
            "temperature":   c.get("temperature_2m"),
            "precipitation": c.get("precipitation", 0),
            "weathercode":   c.get("weathercode", 0),
        }
    except Exception:
        return {"temperature": None, "precipitation": 0, "weathercode": 0}


def _score_meteo(meteo: dict, station_names: list, aeriennes_idx: dict) -> dict:
    temp         = meteo.get("temperature")
    precipitation = meteo.get("precipitation", 0)
    weathercode  = meteo.get("weathercode", 0)

    stations_aeriennes = [n for n in station_names if _norm(n) in aeriennes_idx]
    a_l_air_libre = len(stations_aeriennes) > 0

    alertes = []
    malus = 0.0

    # Pluie (weathercode 51-99) + sections aériennes
    pluie = weathercode >= 51 or precipitation > 0.5
    if pluie and a_l_air_libre:
        malus += 2.0
        alertes.append("Pluie sur tronçons aériens")
    elif pluie:
        alertes.append("Pluie (trajet couvert)")

    # Canicule (>= 35°C) → pénalise les lignes sans clim
    canicule = temp is not None and temp >= 35
    if canicule:
        malus += 1.0
        alertes.append("Canicule : préférez une ligne climatisée")

    # Chaleur modérée (28-35°C) → signal informatif
    chaleur = temp is not None and 28 <= temp < 35
    if chaleur:
        alertes.append("Chaleur : vérifiez la climatisation")

    score = round(max(0.0, 10.0 - malus), 1)

    return {
        "temperature":         temp,
        "precipitation":       precipitation,
        "weathercode":         weathercode,
        "pluie":               pluie,
        "canicule":            canicule,
        "stations_aeriennes":  stations_aeriennes,
        "alertes":             alertes,
        "score":               score,
    }


def _norm(name: str) -> str:
    name = name.lower().strip()
    for prefix in ["métro ", "rer ", "gare de ", "gare du ", "gare "]:
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.strip()


# ─── Dimension : Affluence (ML) ─────────────────────────────────────────────

def _niveau_from_score(score: float) -> str:
    if score >= 8.0:  return "VERY_LOW"
    if score >= 6.0:  return "LOW"
    if score >= 4.0:  return "MEDIUM"
    if score >= 2.0:  return "HIGH"
    return "VERY_HIGH"


def _score_affluence(
    heure: int,
    station_names: list,
    affluence_data: dict,
    jour_semaine: int = 0,
) -> dict:
    idx     = _load_affluence_idx()
    cat_jour = _DOW_TO_CAT.get(jour_semaine, "JOHV")

    # ── Source 1 : lookup données réelles ──────────────────────────────────
    if idx:
        aliases  = idx.get("aliases", {})
        stations = idx.get("stations", {})
        p97      = idx.get("p97_pct", 12.51)
        best_pct = None

        for name in station_names:
            key = _norm_station(name)
            key = aliases.get(key, key)
            profil_station = stations.get(key, {})
            profil_cat     = profil_station.get(cat_jour) or profil_station.get("JOHV", {})
            pct = profil_cat.get(str(heure))
            if pct is not None:
                # Prendre la station la plus chargée du trajet (cas le plus pénalisant)
                if best_pct is None or pct > best_pct:
                    best_pct = pct

        if best_pct is not None:
            score  = round(max(0.0, 10.0 * (1 - best_pct / p97)), 1)
            niveau = _niveau_from_score(score)
            return {
                "niveau":      niveau,
                "label":       _label_from_niveau(niveau),
                "pct_reel":    round(best_pct, 2),
                "cat_jour":    cat_jour,
                "score":       score,
                "source":      "reel",
            }

    # ── Source 2 : modèle ML (fallback si station inconnue) ────────────────
    slot = next(
        (s for s in affluence_data["creneaux_horaires"] if s["debut"] <= heure < s["fin"]),
        affluence_data["creneaux_horaires"][0],
    )
    poids = 1
    for name in station_names:
        nn = _norm(name)
        for cat_key, cat in affluence_data["poids_stations"].items():
            if cat_key == "default":
                continue
            if any(_norm(s) == nn for s in cat.get("stations", [])):
                poids = max(poids, cat["poids"])

    model_bundle = _load_model()
    if model_bundle is not None:
        is_weekend = 1 if jour_semaine >= 5 else 0
        score_raw  = float(model_bundle["model"].predict([[heure, jour_semaine, is_weekend, poids]])[0])
        score  = round(min(10.0, max(0.0, score_raw)), 1)
        niveau = _niveau_from_score(score)
        source = "ml"
    else:
        facteur = {1: 1.0, 2: 0.8, 3: 0.6}.get(poids, 1.0)
        score   = round(min(10.0, max(0.0, slot["score"] * facteur)), 1)
        niveau  = slot["niveau"]
        source  = "rules"

    return {
        "niveau":        niveau,
        "label":         slot["label"],
        "poids_station": poids,
        "score":         score,
        "source":        source,
    }


def _label_from_niveau(niveau: str) -> str:
    return {
        "VERY_LOW":  "Très peu de monde",
        "LOW":       "Peu de monde",
        "MEDIUM":    "Modéré",
        "HIGH":      "Chargé",
        "VERY_HIGH": "Très chargé",
    }.get(niveau, niveau)


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


def _build_business_summary(dimensions: dict, score_confort: float) -> dict:
    alertes = []
    points_forts = []

    if dimensions["affluence"]["score"] < 4:
        alertes.append("Affluence élevée")
    else:
        points_forts.append("Affluence modérée")

    if not dimensions["accessibilite"]["ok"]:
        alertes.append("Ascenseur en panne")
    else:
        points_forts.append("Accessibilité stable")

    if dimensions["climatisation"]["status"] == "aucune":
        alertes.append("Pas de climatisation")
    elif dimensions["climatisation"]["status"] == "total":
        points_forts.append("Climatisation présente")

    if dimensions["equipements"]["score"] <= 5:
        alertes.append("Équipements limités")
    else:
        points_forts.append("Équipements disponibles")

    if dimensions["correspondances"]["score"] <= 5:
        alertes.append("Correspondances longues")
    else:
        points_forts.append("Correspondances fluides")

    if score_confort >= 7:
        recommandation = "Recommandé"
    elif score_confort >= 5:
        recommandation = "À considérer"
    else:
        recommandation = "À éviter"

    return {
        "recommandation": recommandation,
        "alertes": alertes,
        "points_forts": points_forts,
    }


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
    affluence_data, clim_data, fontaines_idx, sanitaires_idx, aeriennes_idx = _load()

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
        dt_obj = datetime.strptime(departure_dt[:8], "%Y%m%d")
        jour_semaine = dt_obj.weekday()  # 0=lundi … 6=dimanche
    except (ValueError, IndexError):
        heure = datetime.now().hour
        jour_semaine = datetime.now().weekday()

    aff   = _score_affluence(heure, station_names, affluence_data, jour_semaine)
    clim  = _score_climatisation(lignes, clim_data)
    acc   = _score_accessibilite(sections)
    corr  = _score_correspondances(sections)
    equip = _score_equipements(station_names, fontaines_idx, sanitaires_idx)
    meteo_raw = _fetch_meteo()
    meteo = _score_meteo(meteo_raw, station_names, aeriennes_idx)

    score_confort = round(
        aff["score"]   * 0.35 +
        acc["score"]   * 0.30 +
        corr["score"]  * 0.20 +
        equip["score"] * 0.15,
        1,
    )

    # Ajustement météo : -1 pt si pluie sur aérien, -0.5 si canicule
    if meteo["alertes"]:
        score_confort = round(max(0.0, score_confort - (meteo.get("score", 10) < 10) * 1.0), 1)

    dimensions = {
        "affluence":      aff,
        "climatisation":  clim,
        "accessibilite":  acc,
        "correspondances": corr,
        "equipements":    equip,
        "meteo":          meteo,
    }

    business_summary = _build_business_summary(dimensions, score_confort)

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
        "dimensions": dimensions,
        "score_confort": score_confort,
        "recommandation": business_summary["recommandation"],
        "business_summary": business_summary,
    }


def enrich_journeys(journeys: list, departure_dt: str) -> list:
    """Enrichit une liste d'itinéraires avec la logique métier de confort."""
    return [enrich(journey, departure_dt) for journey in journeys]


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
        print(f"  🧭 Recommandation : {result['business_summary']['recommandation']}")
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
