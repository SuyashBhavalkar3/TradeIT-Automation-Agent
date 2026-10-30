from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"


def get_fresh_settings() -> "Settings":
    if ENV_PATH.exists():
        from dotenv import dotenv_values
        import os
        _vals = dotenv_values(ENV_PATH)
        for k, v in _vals.items():
            if v is not None:
                os.environ[k] = v
    return Settings()


# Prioritize .env file values over lingering terminal shell environment variables
if ENV_PATH.exists():
    from dotenv import dotenv_values
    _vals = dotenv_values(ENV_PATH)
    if _vals.get("TRADING_MODE"):
        import os
        os.environ["TRADING_MODE"] = _vals["TRADING_MODE"]


class TradingMode(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"


class MarketDataSource(str, Enum):
    SIMULATED = "SIMULATED"
    LIVE_SYNC = "LIVE_SYNC"
    DHAN_LIVE = "DHAN_LIVE"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Core Execution Mode (Default is ALWAYS PAPER for capital safety)
    TRADING_MODE: TradingMode = Field(default=TradingMode.PAPER)
    MARKET_DATA_SOURCE: MarketDataSource = Field(default=MarketDataSource.SIMULATED)

    # Safe Mode (Human-in-the-Loop Consent & Anti-Chasing)
    SAFE_MODE: bool = Field(default=True, description="When True, trades require advance pre-approval before execution")
    MAX_ENTRY_SLIPPAGE_PCT: float = Field(default=0.03, description="Max 3.0% price deviation allowed upon execution. Rejects if price spikes.")
    MAX_ORDER_RETRIES: int = Field(default=1, description="Max order submission attempts to prevent duplicate executions")

    # Dhan Credentials
    DHAN_CLIENT_ID: str = Field(default="")
    DHAN_ACCESS_TOKEN: str = Field(default="")

    # Logging
    LOG_LEVEL: str = Field(default="INFO")

    # Risk Management Guardrails
    MAX_DAILY_LOSS: float = Field(default=5000.0, description="Max cumulative loss in INR before hard shutdown")
    MAX_PER_TRADE_RISK: float = Field(default=1500.0, description="Max allowed risk per trade in INR")
    MAX_OPEN_POSITIONS: int = Field(default=2, description="Max concurrent positions")
    MAX_CAPITAL_PER_TRADE: float = Field(default=25000.0, description="Max total premium/capital committed per trade")

    # Operating Timings (IST)
    MARKET_OPEN_TIME: str = Field(default="09:15:00")
    MARKET_CLOSE_TIME: str = Field(default="15:30:00")
    NO_NEW_ENTRY_TIME: str = Field(default="15:00:00")
    AUTO_SQUARE_OFF_TIME: str = Field(default="15:15:00")

    # Expiry Configurations (IST)
    NIFTY_EXPIRY_DATE: str = Field(default="2026-11-03 15:30:00", description="Expiry datetime for NIFTY weekly contracts")
    BANKNIFTY_EXPIRY_DATE: str = Field(default="2026-11-23 15:30:00", description="Monthly expiry datetime for BANKNIFTY contracts")

    # Stale Data & Health
    MAX_STALE_TICK_SECONDS: float = Field(default=12.0, description="Seconds without ticks before feed is flagged stale")


settings = Settings()

