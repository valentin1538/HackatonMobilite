import sys
import os
import time
import requests
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")


from enricher import enrich, _norm_station, _load_affluence_idx
from historique import log_trajet

load_dotenv()

BASE_URL = "https://prim.iledefrance-mobilites.fr/marketplace/v2/navitia"

app = FastAPI(title="HackatonMobilite API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# ─── Charge dynamique ────────────────────────────────────────────────────────
# Clé : "dep_id|arr_id|lignes|heure" → (nb_utilisateurs, timestamp_derniere_maj)
# Les entrées expirent après 30 minutes.

_CHARGE: dict[str, tuple[int, float]] = {}
_CHARGE_TTL = 1800  # secondes


def _charge_key(dep_id: str, arr_id: str, lignes: list[str], datetime_str: str) -> str:
    heure = datetime_str[9:11] if len(datetime_str) >= 11 else "00"
    return f"{dep_id}|{arr_id}|{'_'.join(sorted(lignes))}|{heure}"


def _get_charge(key: str) -> int:
    now = time.time()
    if key in _CHARGE:
        count, ts = _CHARGE[key]
        if now - ts < _CHARGE_TTL:
            return count
        del _CHARGE[key]
    return 0


def _apply_charge(itineraire: dict, charge: int) -> dict:
    if charge == 0:
        return itineraire
    # -0.5 point par utilisateur supplémentaire, max -3 points sur l'affluence
    malus = min(3.0, charge * 0.5)
    aff = itineraire["dimensions"]["affluence"]
    aff["score"] = round(max(0.0, aff["score"] - malus), 1)
    aff["charge_dynamique"] = charge

    # Recalcule le score global
    d = itineraire["dimensions"]
    itineraire["score_confort"] = round(
        d["affluence"]["score"]      * 0.35 +
        d["accessibilite"]["score"]  * 0.30 +
        d["correspondances"]["score"] * 0.20 +
        d["equipements"]["score"]    * 0.15,
        1,
    )
    return itineraire


# ─── Filtres ─────────────────────────────────────────────────────────────────

def _passe_filtres(
    itineraire: dict,
    accessible: bool,
    peu_de_monde: bool,
    climatise: bool,
) -> bool:
    d = itineraire["dimensions"]
    # Un trajet dont l'accessibilité n'est pas renseignée est écarté : pour ce
    # filtre, "on ne sait pas" ne doit pas être servi comme "c'est accessible".
    if accessible and d["accessibilite"]["statut"] != "accessible":
        return False
    if peu_de_monde and d["affluence"]["niveau"] not in ("LOW", "VERY_LOW"):
        return False
    if climatise and d["climatisation"]["status"] == "aucune":
        return False
    return True


# ─── Modèles ─────────────────────────────────────────────────────────────────

class ItineraryRequest(BaseModel):
    depart: str
    arrivee: str
    datetime: str  # format YYYYMMDDThhmmss, ex: "20260625T083000"
    datetime_represents: str = "departure"  # "departure" | "arrival"


class SelectRequest(BaseModel):
    dep_id: str
    arr_id: str
    lignes: list[str]
    datetime: str


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_place_id(query: str, headers: dict) -> str | None:
    r = requests.get(
        f"{BASE_URL}/places",
        headers=headers,
        params={"q": query, "type[]": "stop_area", "count": 1},
    )
    r.raise_for_status()
    places = r.json().get("places", [])
    return places[0]["id"] if places else None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/itineraries")
def post_itineraries(
    req: ItineraryRequest,
    accessible:   bool = Query(False, description="Garder uniquement les itinéraires sans ascenseur en panne"),
    peu_de_monde: bool = Query(False, description="Garder uniquement les itinéraires peu fréquentés"),
    climatise:    bool = Query(False, description="Garder uniquement les itinéraires avec climatisation"),
):
    api_key = os.getenv("IDFM_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="IDFM_API_KEY manquante")

    headers = {"apikey": api_key}

    dep_id = _get_place_id(req.depart, headers)
    if not dep_id:
        raise HTTPException(status_code=404, detail=f"Station introuvable : {req.depart}")

    arr_id = _get_place_id(req.arrivee, headers)
    if not arr_id:
        raise HTTPException(status_code=404, detail=f"Station introuvable : {req.arrivee}")

    r = requests.get(
        f"{BASE_URL}/journeys",
        headers=headers,
        params={
            "from":                 dep_id,
            "to":                   arr_id,
            "datetime":             req.datetime,
            "datetime_represents":  req.datetime_represents,
            "data_freshness":       "realtime",
            "equipment_details":    "true",
            "count":                3,
        },
    )
    r.raise_for_status()
    journeys = r.json().get("journeys", [])

    itineraires = []
    for j in journeys:
        enrichi = enrich(j, req.datetime)
        key = _charge_key(dep_id, arr_id, enrichi["lignes"], req.datetime)
        enrichi = _apply_charge(enrichi, _get_charge(key))
        itineraires.append(enrichi)

        # Alimente l'historique d'apprentissage uniquement avec des trajets
        # réellement observés (jamais une prédiction ML) pour permettre de
        # ré-entraîner le modèle de confort. Best-effort : ne doit jamais
        # casser la réponse API.
        if enrichi.get("donnee_temps_reel"):
            try:
                log_trajet(req.depart, req.arrivee, req.datetime, enrichi)
            except Exception:
                pass

    if accessible or peu_de_monde or climatise:
        itineraires = [
            it for it in itineraires
            if _passe_filtres(it, accessible, peu_de_monde, climatise)
        ]

    return {
        "depart":      req.depart,
        "arrivee":     req.arrivee,
        "datetime":    req.datetime,
        "filtres":     {"accessible": accessible, "peu_de_monde": peu_de_monde, "climatise": climatise},
        "itineraires": itineraires,
    }


@app.post("/itineraries/select")
def select_itinerary(req: SelectRequest):
    """Enregistre qu'un utilisateur a choisi cet itinéraire. Ajuste le score en temps réel."""
    key = _charge_key(req.dep_id, req.arr_id, req.lignes, req.datetime)
    count, _ = _CHARGE.get(key, (0, 0.0))
    _CHARGE[key] = (count + 1, time.time())
    return {"key": key, "utilisateurs_actifs": count + 1}


# ─── Autocomplétion stations ─────────────────────────────────────────────────

@app.get("/stations")
def search_stations(q: str = Query("", description="Recherche de station (min 2 chars)")):
    if len(q.strip()) < 2:
        return {"stations": []}

    idx = _load_affluence_idx()
    if not idx:
        return {"stations": []}

    q_norm = _norm_station(q)
    canonical_keys = list(idx.get("stations", {}).keys())
    alias_keys     = list(idx.get("aliases",  {}).keys())
    all_keys       = list(set(canonical_keys + alias_keys))

    # Prefix matches first, then other substring matches
    prefix = sorted(k for k in all_keys if k.startswith(q_norm))
    middle = sorted(k for k in all_keys if q_norm in k and not k.startswith(q_norm))

    results, seen = [], set()
    for k in prefix + middle:
        display = k.title()
        if display not in seen:
            seen.add(display)
            results.append(display)
        if len(results) >= 12:
            break

    return {"stations": results}


# ─── Frontend statique ────────────────────────────────────────────────────────

_STATIC_DIR = Path(__file__).parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
