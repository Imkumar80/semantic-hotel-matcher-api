import pytest
import importlib.util
import sys

# Dynamically import module with leading number
spec = importlib.util.spec_from_file_location("score_hotels", "pipeline/03_score_hotels.py")
score_hotels = importlib.util.module_from_spec(spec)
sys.modules["score_hotels"] = score_hotels
spec.loader.exec_module(score_hotels)

def test_haversine_distance():
    dist = score_hotels.haversine_distance(12.9716, 77.5946, 12.9720, 77.5950)
    assert 50 < dist < 100
    
def test_normalize_address():
    assert score_hotels.normalize_address("123 Main St., Apt 4-B") == "123 main st apt 4 b"
    assert score_hotels.normalize_address("Bangalore, Karnataka.") == "bangalore karnataka"
    assert score_hotels.normalize_address(None) == ""

def test_compute_amenity_score():
    assert score_hotels.compute_amenity_score(["wifi", "pool"], ["wifi", "pool"]) == 1.0
    assert score_hotels.compute_amenity_score(["wifi"], ["pool"]) == 0.0
    assert score_hotels.compute_amenity_score(["wifi", "pool"], ["wifi", "gym"]) == 0.3333333333333333
    assert score_hotels.compute_amenity_score([], []) == 0.5
    assert score_hotels.compute_amenity_score(["wifi"], []) == 0.0
