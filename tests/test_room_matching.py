import pytest
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("match_rooms", "pipeline/06_match_rooms.py")
match_rooms = importlib.util.module_from_spec(spec)
sys.modules["match_rooms"] = match_rooms
spec.loader.exec_module(match_rooms)

def test_normalize_room_name():
    assert match_rooms.normalize_room_name("a std room") == "a standard room"
    assert match_rooms.normalize_room_name("a 1k bed") == "a king bed"

def test_compute_room_sim():
    room_a_name = "Deluxe Twin Room"
    room_b_name = "Twin Deluxe"
    room_a_parsed = {
        'capacity': 2,
        'bed_type': 'Twin',
        'meal_plan': 'Breakfast'
    }
    room_b_parsed = {
        'capacity': 2,
        'bed_type': 'Twin',
        'meal_plan': 'Breakfast'
    }
    
    sim = match_rooms.compute_room_sim(room_a_name, room_b_name, room_a_parsed, room_b_parsed)
    assert sim == 1.0

    # Conflicting beds test penalty
    room_b_parsed_conflict = {
        'capacity': 3,
        'bed_type': 'King',
        'meal_plan': 'None'
    }
    sim_conflict = match_rooms.compute_room_sim(room_a_name, room_b_name, room_a_parsed, room_b_parsed_conflict)
    assert sim_conflict < 1.0
