import pytest
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("match_rooms", "pipeline/06_match_rooms.py")
match_rooms = importlib.util.module_from_spec(spec)
sys.modules["match_rooms"] = match_rooms
spec.loader.exec_module(match_rooms)

def test_jaccard():
    assert match_rooms.jaccard({"a", "b"}, {"b", "c"}) == 0.3333333333333333
    assert match_rooms.jaccard(set(), set()) == 0.5
    assert match_rooms.jaccard({"a"}, set()) == 0.0

def test_compute_room_sim():
    room_a = {
        'capacity': 2,
        'bed_type': 'Twin',
        'features': ['WiFi'],
        'room_class': 'Deluxe'
    }
    room_b = {
        'capacity': 2,
        'bed_type': 'Twin',
        'features': ['WiFi', 'Breakfast'],
        'room_class': 'Deluxe'
    }
    
    # exact bed match = 1.0 (0.4)
    # cap match = 1.0 (0.3)
    # feat A = {WiFi, Deluxe}, feat B = {WiFi, Breakfast, Deluxe}
    # Jaccard = 2/3 (0.3 * 0.666 = 0.2)
    # Total = 0.4 + 0.3 + 0.2 = 0.9
    sim = match_rooms.compute_room_sim(room_a, room_b)
    assert abs(sim - 0.9) < 1e-6
