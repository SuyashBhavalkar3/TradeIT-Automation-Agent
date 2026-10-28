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


def test_api_risk_status_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/risk/status")
        assert response.status_code == 200
        data = response.json()
        assert "is_emergency_halt" in data
        assert "cumulative_daily_pnl" in data
        assert data["max_daily_loss"] > 0


def test_api_strategy_proposal_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/strategy/proposal/NIFTY")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data


def test_api_paper_trading_endpoints():
    with TestClient(app) as client:
        # 1. Portfolio
        res_portfolio = client.get("/api/paper/portfolio")
        assert res_portfolio.status_code == 200
        port = res_portfolio.json()
        assert "available_cash" in port
        assert port["available_cash"] > 0

        # 2. Positions
        res_positions = client.get("/api/paper/positions")
        assert res_positions.status_code == 200
        assert isinstance(res_positions.json(), list)

        # 3. Trades
        res_trades = client.get("/api/paper/trades")
        assert res_trades.status_code == 200
        assert isinstance(res_trades.json(), list)

