import sys
import json
import pickle
import unicodedata
import re
import requests as _requests
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from historique import MIN_SAMPLES_CONFORT_MODEL

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass  # Jupyter OutStream ne supporte pas reconfigure

DATA_DIR  = Path(__file__).parent.parent / "data"
MODEL_DIR = Path(__file__).parent.parent / "models"

_DATASETS = None
_MODEL    = None   # chargé une seule fois (lazy)
_AFFLUENCE_IDX = None  # index horaire réel (lazy)
_CONFORT_MODEL = None  # modèle global de confort, chargé une seule fois (lazy)

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


def _load_confort_model():
    global _CONFORT_MODEL
    if _CONFORT_MODEL is not None:
        return _CONFORT_MODEL
    model_path = MODEL_DIR / "confort_model.pkl"
    if model_path.exists():
        with open(model_path, "rb") as f:
            _CONFORT_MODEL = pickle.load(f)
    return _CONFORT_MODEL


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


# Au-delà de cet écart avec l'instant présent, un trajet n'est plus considéré
# comme "temps réel" : la météo/l'accessibilité capturées maintenant ne sont
# plus une estimation fiable de l'état au moment du trajet.
SEUIL_TEMPS_REEL_HEURES = 1.0


def _is_future(departure_dt: str) -> bool:
    """Vrai si l'heure demandée est à plus de SEUIL_TEMPS_REEL_HEURES de maintenant.

    Basé sur l'écart réel en heures, pas seulement le jour calendaire : "aujourd'hui
    dans 6h" doit être traité comme un trajet futur (météo en prévision, éligible
    au modèle ML), pas comme une observation temps réel. Un trajet dans le passé
    (écart négatif) reste considéré comme non-futur.
    """
    try:
        cible = datetime.strptime(departure_dt, "%Y%m%dT%H%M%S")
    except ValueError:
        return False
    ecart_heures = (cible - datetime.now()).total_seconds() / 3600
    return ecart_heures > SEUIL_TEMPS_REEL_HEURES


# ─── Météo (Open-Meteo, sans clé API) ──────────────────────────────────────

def _fetch_meteo(departure_dt: str) -> dict:
    try:
        cible = datetime.strptime(departure_dt, "%Y%m%dT%H%M%S")
    except ValueError:
        cible = datetime.now()

    if not _is_future(departure_dt):
        return _fetch_meteo_actuelle()

    delta_days = (cible.date() - datetime.now().date()).days
    if 0 <= delta_days <= 16:
        return _fetch_meteo_prevision(cible.date(), cible.hour, delta_days)
    # Trop lointain (> 16 jours) : pas de prévision fiable
    return {"temperature": None, "precipitation": 0, "weathercode": 0}


def _fetch_meteo_actuelle() -> dict:
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


def _fetch_meteo_prevision(cible, heure: int, delta_days: int) -> dict:
    """Prévision horaire Open-Meteo pour une date future (jusqu'à 16 jours)."""
    try:
        r = _requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":            _PARIS_LAT,
                "longitude":           _PARIS_LON,
                "hourly":              "temperature_2m,precipitation,weathercode",
                "wind_speed_unit":     "ms",
                "forecast_days":       delta_days + 1,
            },
            timeout=5,
        )
        r.raise_for_status()
        h = r.json().get("hourly", {})
        cible_str = f"{cible.isoformat()}T{heure:02d}:00"
        idx = h.get("time", []).index(cible_str)
        return {
            "temperature":   h["temperature_2m"][idx],
            "precipitation": h.get("precipitation", [])[idx],
            "weathercode":   h.get("weathercode", [])[idx],
        }
    except Exception:
        return {"temperature": None, "precipitation": 0, "weathercode": 0}


def _score_meteo(
    meteo: dict,
    station_names: list,
    aeriennes_idx: dict,
    clim_status: str = "inconnu",
) -> dict:
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

    # Canicule (>= 35°C) → le malus dépend de la climatisation du trajet.
    # Un trajet entièrement climatisé n'est pas pénalisé : c'est précisément
    # le jour où ce choix doit ressortir face aux lignes non climatisées.
    canicule = temp is not None and temp >= 35
    if canicule:
        if clim_status == "total":
            alertes.append("Canicule (trajet climatisé)")
        elif clim_status == "aucune":
            malus += 2.0
            alertes.append("Canicule : trajet non climatisé")
        elif clim_status == "partiel":
            malus += 1.0
            alertes.append("Canicule : trajet partiellement climatisé")
        else:  # "inconnu"
            malus += 1.0
            alertes.append("Canicule : climatisation non renseignée")

    # Chaleur modérée (28-35°C) → signal informatif, inutile si tout est climatisé
    chaleur = temp is not None and 28 <= temp < 35
    if chaleur and clim_status != "total":
        alertes.append("Chaleur : vérifiez la climatisation")

    score = round(max(0.0, 10.0 - malus), 1)

    return {
        "temperature":         temp,
        "precipitation":       precipitation,
        "weathercode":         weathercode,
        "pluie":               pluie,
        "canicule":            canicule,
        "clim_status":         clim_status,
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
    """Statut d'accessibilité du trajet, d'après les équipements renvoyés par IDFM.

    L'absence de donnée n'est PAS traitée comme une garantie d'accessibilité :
    une station dont l'état d'ascenseur est inconnu rend le trajet "inconnu"
    et non "accessible". Un utilisateur en fauteuil ne doit jamais se déplacer
    sur la foi d'une information qui n'existe pas.
    """
    pannes = []
    inconnues = []
    nb_checked = 0

    for section in sections:
        if section.get("type") != "public_transport":
            continue
        for sdt in section.get("stop_date_times", []):
            station = sdt.get("stop_point", {}).get("name", "?")
            eq = sdt.get("equipment_availability", {})
            status = eq.get("elevator", "unknown") if eq else "unknown"

            if status == "unknown":
                inconnues.append(station)
                continue

            nb_checked += 1
            if status != "available":
                pannes.append({"station": station, "status": status})

    if pannes:
        statut = "panne"
        score = max(0, 10 - len(pannes) * 3)
    elif inconnues or nb_checked == 0:
        statut = "inconnu"
        score = 7
    else:
        statut = "accessible"
        score = 10

    return {
        # `ok` vaut True uniquement si l'accessibilité est VÉRIFIÉE, jamais par
        # défaut : c'est ce que consomment les filtres côté API et côté front.
        "ok":         statut == "accessible",
        "statut":     statut,
        "pannes":     pannes,
        "inconnues":  inconnues,
        "nb_checked": nb_checked,
        "score":      score,
    }


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


def _build_sections_resume(sections: list) -> list:
    """Résumé des étapes du trajet pour le frontend (walk / ride / transfer)."""
    resume = []
    for s in sections:
        stype = s.get("type")
        if stype not in ("public_transport", "street_network", "transfer"):
            continue
        duration_min = max(1, round(s.get("duration", 0) / 60))
        from_place   = s.get("from") or {}
        to_place     = s.get("to")   or {}
        from_name    = from_place.get("name", "")
        to_name      = to_place.get("name", "")

        if stype == "street_network":
            resume.append({
                "kind": "walk",
                "from": from_name,
                "to":   to_name,
                "duration_min": duration_min,
            })

        elif stype == "public_transport":
            ligne = (s.get("display_informations") or {}).get("label", "?")
            sdts  = s.get("stop_date_times") or []
            if not from_name and sdts:
                from_name = (sdts[0].get("stop_point") or {}).get("name", "")
            if not to_name and sdts:
                to_name   = (sdts[-1].get("stop_point") or {}).get("name", "")
            resume.append({
                "kind":  "ride",
                "ligne": ligne,
                "from":  from_name,
                "to":    to_name,
                "duration_min": duration_min,
            })

        elif stype == "transfer":
            resume.append({
                "kind": "transfer",
                "from": from_name,
                "to":   to_name,
                "duration_min": duration_min,
            })

    return resume


def _build_business_summary(dimensions: dict, score_confort: float) -> dict:
    alertes = []
    points_forts = []

    if dimensions["affluence"]["score"] < 4:
        alertes.append("Affluence élevée")
    else:
        points_forts.append("Affluence modérée")

    statut_acc = dimensions["accessibilite"]["statut"]
    if statut_acc == "panne":
        alertes.append("Ascenseur en panne")
    elif statut_acc == "inconnu":
        # Ni une alerte ni un point fort : IDFM n'a rien renvoyé sur ce trajet.
        alertes.append("Accessibilité non renseignée")
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
    meteo_raw = _fetch_meteo(departure_dt)
    meteo = _score_meteo(meteo_raw, station_names, aeriennes_idx, clim["status"])

    score_confort = round(
        aff["score"]   * 0.35 +
        acc["score"]   * 0.30 +
        corr["score"]  * 0.20 +
        equip["score"] * 0.15,
        1,
    )

    # Ajustement météo : proportionnel à l'exposition réelle du trajet (aérien
    # sous la pluie, absence de climatisation en cas de canicule). Un malus de
    # 2 pts sur la dimension météo retire 1 pt au score de confort.
    malus_meteo = 10.0 - meteo["score"]
    score_confort = round(max(0.0, score_confort - malus_meteo * 0.5), 1)

    # Pour un trajet futur (jour calendaire différent d'aujourd'hui), aucune donnée
    # temps réel n'est disponible (météo = prévision, accessibilité = défaut neutre).
    # Si un modèle de confort a été entraîné sur suffisamment de trajets réels
    # observés, on l'utilise pour affiner la prédiction ; sinon on reste sur la
    # formule de règles ci-dessus, qui sert alors de filet de sécurité.
    donnee_temps_reel = not _is_future(departure_dt)
    score_confort_source = "regles"

    if not donnee_temps_reel:
        confort_bundle = _load_confort_model()
        if confort_bundle is not None and confort_bundle["meta"]["n_samples"] >= MIN_SAMPLES_CONFORT_MODEL:
            is_weekend = 1 if jour_semaine >= 5 else 0
            temp = meteo_raw.get("temperature")
            features = [[
                heure,
                jour_semaine,
                is_weekend,
                aff["score"],
                clim["score"],
                equip["score"],
                corr["nb"],
                temp if temp is not None else 15.0,
                meteo_raw.get("precipitation") or 0.0,
            ]]
            pred = float(confort_bundle["model"].predict(features)[0])
            score_confort = round(min(10.0, max(0.0, pred)), 1)
            score_confort_source = "ml_predit"

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
        "duree_min":          journey.get("duration", 0) // 60,
        "nb_correspondances": journey.get("nb_transfers", 0),
        "lignes":             lignes,
        "sections_resume":    _build_sections_resume(sections),
        "perturbations": [
            {
                "severite": d.get("severity", {}).get("name", "?"),
                "message":  d.get("messages", [{}])[0].get("text", "?") if d.get("messages") else "—",
            }
            for d in journey.get("disruptions", [])
        ],
        "dimensions": dimensions,
        "score_confort": score_confort,
        "score_confort_source": score_confort_source,
        "donnee_temps_reel": donnee_temps_reel,
        "recommandation": business_summary["recommandation"],
        "business_summary": business_summary,
    }


def enrich_journeys(journeys: list, departure_dt: str) -> list:
    """Enrichit une liste d'itinéraires avec la logique métier de confort."""
    return [enrich(journey, departure_dt) for journey in journeys]

