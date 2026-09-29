import os
import pytest
from fastapi.testclient import TestClient
from app import app
import database

client = TestClient(app)

def test_startup_check():
    """Test health check and startup endpoint"""
    response = client.get("/startup")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "service" in data

def test_public_pages():
    """Test landing and auth HTML pages serve 200 OK"""
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "PocketSmart" in res_home.text

    res_login = client.get("/login")
    assert res_login.status_code == 200
    assert "Welcome Back" in res_login.text

    res_register = client.get("/register")
    assert res_register.status_code == 200
    assert "Create Your Account" in res_register.text

def test_user_registration_and_login():
    """Test user registration and subsequent login"""
    unique_user = f"testuser_{os.urandom(3).hex()}"
    reg_payload = {
        "username": unique_user,
        "email": f"{unique_user}@example.com",
        "full_name": "Test Tester",
        "password": "securepassword123"
    }
    
    # Register
    reg_res = client.post("/register", json=reg_payload)
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    token = reg_data["access_token"]
    assert token

    # Login
    login_payload = {
        "username": unique_user,
        "password": "securepassword123"
    }
    login_res = client.post("/login", json=login_payload)
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data

def test_home_planner_recommendations():
    """Test Home Interior Budget Planner AI generation and history saving"""
    # Login demo user 'sai'
    login_res = client.post("/login", json={"username": "sai", "password": "password123"})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    home_payload = {
        "total_budget": 5000.0,
        "num_lights": 5,
        "num_fans": 4,
        "num_furniture": 2,
        "num_dining_tables": 1,
        "has_living_room": True,
        "has_kitchen": True,
        "has_bedroom": False,
        "additional_requirements": "Modern aesthetic in warm tones"
    }

    res = client.post("/home-budget", json=home_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "budget_breakdown" in data
    assert "total_budget" in data
    assert "recommendation_id" in data
    assert len(data["budget_breakdown"]) > 0

    # Verify shopping links attached
    first_item = data["budget_breakdown"][0]["items"][0]
    assert "shopping_links" in first_item
    assert "amazon" in first_item["shopping_links"]

def test_party_planner_recommendations():
    """Test Party Budget Planner AI generation and history saving"""
    login_res = client.post("/login", json={"username": "sai", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    party_payload = {
        "total_budget": 5000.0,
        "num_guests": 20,
        "party_type": "Birthday",
        "venue_type": "Home",
        "needs_catering": True,
        "needs_decoration": True,
        "needs_entertainment": True,
        "additional_requirements": "Vegan dietary options"
    }

    res = client.post("/party-budget", json=party_payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "budget_breakdown" in data
    assert "venue_suggestions" in data
    assert "recommendation_id" in data

def test_jewelry_planner_recommendations():
    """Test Jewelry Budget Planner with multimodal upload support"""
    login_res = client.post("/login", json={"username": "sai", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    form_data = {
        "total_budget": "5000.0",
        "occasion": "Birthday",
        "preferences": "Minimalist silver or platinum finish"
    }

    res = client.post("/jewelry-budget", data=form_data, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "jewelry_recommendations" in data
    assert "outfit_analysis" in data
    assert len(data["jewelry_recommendations"]) > 0
    assert "recommendation_id" in data

def test_history_and_details_endpoints():
    """Test recommendation history listing and detail retrieval"""
    login_res = client.post("/login", json={"username": "sai", "password": "password123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Fetch history
    res = client.get("/recommendation-history", headers=headers)
    assert res.status_code == 200
    history = res.json()["history"]
    assert isinstance(history, list)

    if len(history) > 0:
        first_id = history[0]["id"]
        detail_res = client.get(f"/recommendation-details/{first_id}", headers=headers)
        assert detail_res.status_code == 200
        detail_data = detail_res.json()
        assert "full_result" in detail_data
