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
