import requests
from urllib.parse import quote_plus
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import math

app = FastAPI(
    title="OSM Places API",
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
    'pg': 'guest_house',   # mapped to OSM
    'hostel': 'hostel',
    # extend with more OSM amenity types
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
# Geocoding (Nominatim)
# -----------------------------
def get_location_components(location: str):
    """Convert any address/ward/area into lat/lng + structured info"""
    location_encoded = quote_plus(location)
    url = f"https://nominatim.openstreetmap.org/search?q={location_encoded}&format=json&addressdetails=1"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).json()

    if not response:
        return None

    loc = response[0]
    lat = float(loc['lat'])
    lng = float(loc['lon'])
    address = loc.get('address', {})
    ward = address.get('suburb', address.get('city_district', 'N/A'))
    city = address.get('city', address.get('town', 'N/A'))
    state = address.get('state', 'N/A')
    country = address.get('country', 'N/A')
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
# Places Search (Overpass)
# -----------------------------
def get_places(user_types: List[str], user_location: str, radius: int = 5000, limit: int = 10):
    loc = get_location_components(user_location)
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    lat, lng, ward, city, state, country = loc
    normalized_types = [normalize_type(t) for t in user_types]

    # Build Overpass query with multiple types
    conditions = "\n".join(
        [f'node["amenity"="{t}"](around:{radius},{lat},{lng});\n'
         f'way["amenity"="{t}"](around:{radius},{lat},{lng});\n'
         f'relation["amenity"="{t}"](around:{radius},{lat},{lng});'
         for t in normalized_types]
    )

    query = f"""
    [out:json][timeout:25];
    (
      {conditions}
    );
    out center;
    """

    url = "https://overpass-api.de/api/interpreter"
    response = requests.post(url, data={"data": query}).json()

    if "elements" not in response or not response["elements"]:
        return []

    results = []
    for place in response.get('elements', []):
        tags = place.get('tags', {})
        name = tags.get('name', 'N/A')

        # Construct address
        addr_parts = [
            tags.get('addr:housenumber', ''),
            tags.get('addr:street', ''),
            tags.get('addr:suburb', ''),
            tags.get('addr:city', ''),
            tags.get('addr:state', ''),
            tags.get('addr:postcode', '')
        ]
        address = ", ".join([p for p in addr_parts if p])

        lat_p = place.get('lat', place.get('center', {}).get('lat'))
        lng_p = place.get('lon', place.get('center', {}).get('lon'))
        osm_link = f"https://www.openstreetmap.org/?mlat={lat_p}&mlon={lng_p}&zoom=18" if lat_p and lng_p else 'N/A'

        # detect type from tags
        detected_type = tags.get("amenity", "N/A")

        # calculate distance
        distance = haversine(lat, lng, lat_p, lng_p) if lat_p and lng_p else -1

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
            type=detected_type,
            distance_km=round(distance, 2)
        ))

    # Sort nearest-first
    results.sort(key=lambda x: x.distance_km if x.distance_km >= 0 else 9999)

    return results[:limit]