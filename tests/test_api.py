import pytest
from fastapi.testclient import TestClient
from api.main import app
import os

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_search_hotels():
    # Only run this if the DB exists
    if not os.path.exists("data/canonical/hotels.db"):
        pytest.skip("Database not built yet.")
        
    response = client.get("/hotels?search=Bangalore&size=5")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) <= 5

def test_get_hotel_not_found():
    response = client.get("/hotels/invalid-id-12345")
    assert response.status_code == 404

def test_project_upload_run_and_search():
    project = client.post("/v1/projects?name=test%20supplier%20match")
    assert project.status_code == 201
    project_data = project.json()
    project_id = project_data["project_id"]
    headers = {"X-API-Key": project_data["api_key"]}
    hotels_a = b"id,name,address,lat,lon\nA-1,Grand Plaza,10 Main Street,12.0,77.0\n"
    hotels_b = b"id,name,address,lat,lon\nB-1,Grand Plaza Hotel,10 Main St,12.0001,77.0001\n"
    rooms_a = b"room_id,hotel_id,name\nAR-1,A-1,Deluxe King Room\n"
    rooms_b = b"room_id,hotel_id,name\nBR-1,B-1,King Deluxe Room\n"
    assert client.get(f"/v1/projects/{project_id}").status_code == 401
    upload = client.post(f"/v1/projects/{project_id}/uploads", files={
        "supplier_a_hotels": ("supplier_a.csv", hotels_a, "text/csv"),
        "supplier_b_hotels": ("supplier_b.csv", hotels_b, "text/csv"),
        "rooms_a": ("rooms_a.csv", rooms_a, "text/csv"),
        "rooms_b": ("rooms_b.csv", rooms_b, "text/csv"),
    }, headers=headers)
    assert upload.status_code == 200
    run = client.post(f"/v1/projects/{project_id}/runs", headers=headers)
    assert run.status_code == 202
    status = client.get(f"/v1/projects/{project_id}", headers=headers).json()
    assert status["status"] == "completed"
    assert status["room_count"] == 2
    result = client.get(f"/v1/projects/{project_id}/hotels?search=Plaza", headers=headers)
    assert result.status_code == 200
    assert result.json()["total"] == 1
    hotel_id = result.json()["items"][0]["id"]
    matches = client.get(f"/v1/projects/{project_id}/hotels/{hotel_id}/room-matches", headers=headers)
    assert matches.status_code == 200
    assert matches.json()[0]["score"] >= 0.65
