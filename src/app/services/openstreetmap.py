import httpx
from typing import Dict, Any, List
from app.config import settings
from app.log import get_logger

log = get_logger(__name__)


class OpenStreetMapService:
    """Find nearby shops in OpenStreetMap data via the Geoapify Places API."""

    GEOAPIFY_API_URL = "https://api.geoapify.com/v2/places"
    # Every shop type where products get scanned: food shops
    GEOAPIFY_CATEGORIES = ",".join([
        "commercial.supermarket",
        "commercial.convenience",
        "commercial.marketplace",
        "commercial.discount_store",
        "commercial.department_store",
        "commercial.food_and_drink",
        "commercial.garden",
    ])
    GEOAPIFY_RESULT_LIMIT = 20
    GEOAPIFY_TIMEOUT = httpx.Timeout(5.0, connect=3.0)

    @staticmethod
    async def find_nearby_shops(latitude: float, longitude: float, radius_meters: int = 100) -> List[Dict[str, Any]]:
        """
        Find all nearby shops using the Geoapify Places API, sorted by distance (closest first).

        Parameters:
            latitude (float): The latitude to search around.
            longitude (float): The longitude to search around.
            radius_meters (int): The search radius in meters (default 100).

        Returns:
            List[Dict[str, Any]]: List of shop data sorted by distance, or
            empty list if none found or the lookup failed.
        """
        if not settings.GEOAPIFY_API_KEY:
            log.error("GEOAPIFY_API_KEY is not configured; skipping nearby shop lookup")
            return []

        params = {
            "categories": OpenStreetMapService.GEOAPIFY_CATEGORIES,
            "filter": f"circle:{longitude},{latitude},{radius_meters}",
            "bias": f"proximity:{longitude},{latitude}",
            "limit": OpenStreetMapService.GEOAPIFY_RESULT_LIMIT,
            "apiKey": settings.GEOAPIFY_API_KEY,
        }
        try:
            async with httpx.AsyncClient(timeout=OpenStreetMapService.GEOAPIFY_TIMEOUT) as client:
                response = await client.get(OpenStreetMapService.GEOAPIFY_API_URL, params=params)
                response.raise_for_status()
                features = response.json().get("features", [])
        except Exception as e:
            # httpx errors embed the full request URL, which contains the API key
            error_message = str(e).replace(settings.GEOAPIFY_API_KEY, "***")
            log.error(f"Geoapify Places failed: {type(e).__name__}: {error_message}")
            return []

        features.sort(key=lambda f: f.get("properties", {}).get("distance", float("inf")))

        parsed_shops = []
        for feature in features:
            parsed = OpenStreetMapService._parse_geoapify_shop(feature)
            if parsed.get("latitude") and parsed.get("longitude") and parsed.get("osm_id"):
                parsed_shops.append(parsed)
            else:
                log.warning(f"Shop from Geoapify has no valid coordinates or osm_id: {feature.get('properties', {}).get('place_id')}")
        return parsed_shops

    @staticmethod
    def _parse_geoapify_shop(feature: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Geoapify Places GeoJSON feature into our shop format.

        Geoapify serves OSM data: the raw OSM id, type and tags are exposed
        under properties.datasource.raw, which keeps osm_id compatible with
        shops previously imported from Overpass.

        Parameters:
            feature (Dict[str, Any]): A GeoJSON feature from Geoapify Places.

        Returns:
            Dict[str, Any]: Parsed shop data.
        """
        props = feature.get("properties", {})
        raw = props.get("datasource", {}).get("raw", {})

        address_parts = []
        if props.get("housenumber"):
            address_parts.append(props["housenumber"])
        if props.get("street"):
            address_parts.append(props["street"])
        address = " ".join(address_parts) if address_parts else None

        osm_id = raw.get("osm_id")
        osm_type_map = {"n": "node", "w": "way", "r": "relation"}

        name = props.get("name") or raw.get("brand") or raw.get("name:fr") or raw.get("name:en") or "Magasin inconnu"
        return {
            "name": name,
            "latitude": props.get("lat"),
            "longitude": props.get("lon"),
            "address": address,
            "city": props.get("city"),
            "country": props.get("country"),
            "osm_id": str(osm_id) if osm_id is not None else None,
            "osm_type": osm_type_map.get(raw.get("osm_type"), raw.get("osm_type")),
            # Pharmacies and marketplaces are tagged amenity=... in OSM, not shop=...
            "shop_type": raw.get("shop") or raw.get("amenity") or "supermarket",
        }


osm_service = OpenStreetMapService()
