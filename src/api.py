import sys
import os
import requests
from fastapi import FastAPI, HTTPException
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


class ItineraryRequest(BaseModel):
    depart: str
    arrivee: str
    datetime: str  # format YYYYMMDDThhmmss, ex: "20250624T083000"


def _get_place_id(query: str, headers: dict) -> str | None:
    r = requests.get(
        f"{BASE_URL}/places",
        headers=headers,
        params={"q": query, "type[]": "stop_area", "count": 1},
    )
    r.raise_for_status()
    places = r.json().get("places", [])
    return places[0]["id"] if places else None


@app.post("/itineraries")
def post_itineraries(req: ItineraryRequest):
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

    return {
        "depart":      req.depart,
        "arrivee":     req.arrivee,
        "datetime":    req.datetime,
        "itineraires": [enrich(j, req.datetime) for j in journeys],
    }
