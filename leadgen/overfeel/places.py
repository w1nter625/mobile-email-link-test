"""Google Places API (New) — Text Search."""
from __future__ import annotations

import os
import time

import requests

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join(
    "places." + f
    for f in [
        "id", "displayName", "formattedAddress", "businessStatus", "websiteUri",
        "nationalPhoneNumber", "internationalPhoneNumber", "rating", "userRatingCount",
        "primaryTypeDisplayName", "types", "googleMapsUri", "editorialSummary",
        "reviews", "regularOpeningHours",
    ]
) + ",nextPageToken"


def search(query: str, max_pages: int = 3) -> list[dict]:
    """Return raw place dicts for a text query (up to 20 per page)."""
    key = os.environ["GOOGLE_MAPS_API_KEY"]
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"}
    body: dict = {"textQuery": query, "pageSize": 20}
    out: list[dict] = []
    for _ in range(max_pages):
        r = requests.post(SEARCH_URL, json=body, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("places", []))
        token = data.get("nextPageToken")
        if not token:
            break
        body["pageToken"] = token
        time.sleep(1.5)  # page tokens need a moment to become valid
    return out


def normalize(p: dict) -> dict:
    return {
        "place_id": p.get("id"),
        "name": (p.get("displayName") or {}).get("text", ""),
        "address": p.get("formattedAddress", ""),
        "status": p.get("businessStatus", ""),
        "website": p.get("websiteUri"),
        "phone": p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber"),
        "rating": p.get("rating"),
        "review_count": p.get("userRatingCount"),
        "category": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
        "types": p.get("types", []),
        "maps_url": p.get("googleMapsUri"),
        "summary": (p.get("editorialSummary") or {}).get("text", ""),
        "hours": (p.get("regularOpeningHours") or {}).get("weekdayDescriptions", []),
        "reviews": [
            {
                "rating": rv.get("rating"),
                "text": ((rv.get("text") or rv.get("originalText") or {}).get("text", ""))[:600],
                "when": rv.get("relativePublishTimeDescription"),
            }
            for rv in (p.get("reviews") or [])[:5]
        ],
    }
