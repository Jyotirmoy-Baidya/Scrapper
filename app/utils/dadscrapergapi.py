import requests
from urllib.parse import quote_plus
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import math

# -----------------------------
# CONFIG
# -----------------------------
API_KEY = "AIzaSyBM44aqLRx-FNn65WhjCieLvEm2BbI__Zo"  # <<< put your Google Maps API key here

app = FastAPI(
    title="Google Maps Places API",
    description="Search nearby places by type(s) within a radius of any input location/address/ward",
    version="2.0"
)

# -----------------------------
# Type Mapping
# -----------------------------
TYPE_CORRECTIONS = {
    'resturants': 'restaurant',
    'restaurants': 'restaurant',
    'supermarkets': 'supermarket',
    'cafes': 'cafe',
    'cafe': 'cafe',
    'bar': 'bar',
    'pub': 'pub',
    'hotel': 'hotel',
    'pg': 'lodging',   # mapped to Google "lodging"
    'hostel': 'lodging',
}

def normalize_type(user_type: str) -> str:
    corrected = TYPE_CORRECTIONS.get(user_type.lower())
    return corrected if corrected else user_type.lower()

# -----------------------------
# Schemas
# -----------------------------
class Place(BaseModel):
    name: str
    address: str
    latitude: Optional[float]
    longitude: Optional[float]
    osmLink: str
    ward: str
    city: str
    state: str
    country: str
    type: str
    distance_km: float

class PlacesResponse(BaseModel):
    query: str
    types: List[str]
    radius: int
    results: List[Place]

# -----------------------------
# Geocoding (Google)
# -----------------------------
def get_location_components(location: str):
    """Convert any address/ward/area into lat/lng + structured info using Google Geocoding"""
    location_encoded = quote_plus(location)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={location_encoded}&key={API_KEY}"
    response = requests.get(url).json()

    if not response.get("results"):
        return None

    loc = response["results"][0]
    lat = loc["geometry"]["location"]["lat"]
    lng = loc["geometry"]["location"]["lng"]

    address = loc.get("address_components", [])
    def get_component(types):
        for comp in address:
            if any(t in comp["types"] for t in types):
                return comp["long_name"]
        return "N/A"

    ward = get_component(["sublocality", "administrative_area_level_3"])
    city = get_component(["locality", "administrative_area_level_2"])
    state = get_component(["administrative_area_level_1"])
    country = get_component(["country"])

    return lat, lng, ward, city, state, country

# -----------------------------
# Utility: Haversine distance
# -----------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * (2*math.atan2(math.sqrt(a), math.sqrt(1-a)))

# -----------------------------
# Places Search (Google)
# -----------------------------
def get_places_gApi(user_types: List[str], user_location: str, radius: int = 5000, limit: int = 10):
    loc = get_location_components(user_location)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    lat, lng, ward, city, state, country = loc
    normalized_types = [normalize_type(t) for t in user_types]

    results = []
    for t in normalized_types:
        url = (
            f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
            f"location={lat},{lng}&radius={radius}&type={t}&key={API_KEY}"
        )
        response = requests.get(url).json()

        if "results" not in response or not response["results"]:
            continue

        for place in response["results"]:
            name = place.get("name", "N/A")
            address = place.get("vicinity", "N/A")
            lat_p = place["geometry"]["location"]["lat"]
            lng_p = place["geometry"]["location"]["lng"]

            osm_link = f"https://www.google.com/maps/search/?api=1&query={lat_p},{lng_p}"

            distance = haversine(lat, lng, lat_p, lng_p)

            results.append(Place(
                name=name,
                address=address,
                latitude=lat_p,
                longitude=lng_p,
                osmLink=osm_link,
                ward=ward,
                city=city,
                state=state,
                country=country,
                type=t,
                distance_km=round(distance, 2)
            ))

    results.sort(key=lambda x: x.distance_km)
    return results[:limit]
