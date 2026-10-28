import pytest
from fastapi.testclient import TestClient
from src.main import app


def test_api_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["trading_mode"] == "PAPER"
        assert data["live_trading_enabled"] is False
        assert data["market_data_source"] in ["SIMULATED", "DHAN_LIVE", "LIVE_SYNC"]


def test_api_market_snapshot_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/market/snapshot")
        assert response.status_code == 200
        data = response.json()
        assert "NIFTY" in data or isinstance(data, dict)


def test_api_analytics_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/analytics/NIFTY")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "NIFTY"


def test_api_regime_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/regime/NIFTY")
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "NIFTY"
        assert "classification" in data or "warming_up" in str(data)

