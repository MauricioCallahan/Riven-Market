import requests
from config import API_HEADERS, API_BASE_URL


def search_auctions_raw(params: dict, platform: str = "pc", crossplay: str = "true") -> list[dict]:
    """Call warframe.market auction search. Returns raw auction dicts from the API."""
    headers = {**API_HEADERS, "Platform": platform, "Crossplay": crossplay}
    response = requests.get(
        f"{API_BASE_URL}/auctions/search", params=params, headers=headers, timeout=10
    )
    response.raise_for_status()
    return response.json().get("payload", {}).get("auctions", [])
