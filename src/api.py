import sys
import os
import time
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

from enricher import enrich

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
    if accessible and not d["accessibilite"]["ok"]:
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
            "from":              dep_id,
            "to":                arr_id,
            "datetime":          req.datetime,
            "data_freshness":    "realtime",
            "equipment_details": "true",
            "count":             3,
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
