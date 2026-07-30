import re

SYNONYMS = {
    "ac": "Air Conditioning",
    "air conditioner": "Air Conditioning",
    "air conditioning": "Air Conditioning",
    "gym": "Fitness Center",
    "fitness center": "Fitness Center",
    "fitness centre": "Fitness Center",
    "room service": "Room Service",
    "24-hour room service": "Room Service",
    "room upgrade": "Room Upgrade",
    "room upgrade on availability": "Room Upgrade",
    "wifi": "Free WiFi",
    "free wifi": "Free WiFi",
    "free wi-fi": "Free WiFi",
    "parking": "Parking",
    "free parking": "Parking"
}

def normalize_amenity(am):
    am_clean = am.strip().lower()
    
    # Check exact synonym match
    if am_clean in SYNONYMS:
        return SYNONYMS[am_clean]
        
    # Heuristics
    if "wifi" in am_clean or "wi-fi" in am_clean:
        return "Free WiFi"
    if "air condition" in am_clean or am_clean == "a/c":
        return "Air Conditioning"
    if "gym" in am_clean or "fitness" in am_clean:
        return "Fitness Center"
    if "room service" in am_clean:
        return "Room Service"
    if "upgrade" in am_clean:
        return "Room Upgrade"
    if "24-hour security" in am_clean or "24 hour security" in am_clean:
        return "24-Hour Security"
    if "front desk" in am_clean or "reception" in am_clean:
        return "24-Hour Front Desk"
        
    # Title case fallback
    return am.strip().title()

def deduplicate_amenities(amenities_list):
    seen = set()
    deduped = []
    for am in amenities_list:
        if not am: continue
        norm = normalize_amenity(am)
        if norm.lower() not in seen:
            seen.add(norm.lower())
            deduped.append(norm)
    return deduped
