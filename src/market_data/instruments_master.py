from datetime import datetime
import os
from typing import Dict, List, Optional
import pandas as pd
from src.core.logging import get_logger

logger = get_logger("instruments_master")


class InstrumentsMaster:
    """Dynamically loads, parses, and provides contract specifications directly from Dhan's official live scrip master."""

    DHAN_SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
    CACHE_PATH = "data/scrip_master_cache.parquet"

    def __init__(self, cache_dir: str = "data"):
        self.cache_dir = cache_dir
        self.cache_path = os.path.join(cache_dir, "scrip_master.parquet")
        self._df: Optional[pd.DataFrame] = None
        self._last_loaded: Optional[datetime] = None

    def load(self, force_refresh: bool = False) -> bool:
        """Loads master from local cache or downloads directly from Dhan."""
        os.makedirs(self.cache_dir, exist_ok=True)

        if not force_refresh and os.path.exists(self.cache_path):
            try:
                # Check cache freshness (valid for 12 hours)
                mtime = datetime.fromtimestamp(os.path.getmtime(self.cache_path))
                if (datetime.now() - mtime).total_seconds() < 43200:
                    self._df = pd.read_parquet(self.cache_path)
                    self._last_loaded = mtime
                    logger.info("Loaded Dhan scrip master from local cache", count=len(self._df))
                    return True
            except Exception as e:
                logger.warning("Cache read failed, downloading fresh master", error=str(e))

        logger.info("Downloading Dhan live scrip master CSV...")
        try:
            df = pd.read_csv(self.DHAN_SCRIP_MASTER_URL, low_memory=False)
            # Filter to NSE / BSE derivatives and equities for fast query performance
            fno_df = df[
                (df["SEM_EXM_EXCH_ID"].isin(["NSE", "BSE"])) &
                (df["SEM_SEGMENT"].isin(["D", "E"]))
            ].copy()

            fno_df.to_parquet(self.cache_path, index=False)
            self._df = fno_df
            self._last_loaded = datetime.now()
            logger.info("Downloaded and cached Dhan scrip master", total_records=len(fno_df))
            return True
        except Exception as exc:
            logger.error("Failed to load Dhan scrip master", error=str(exc))
            return False

    def get_underlying_specs(self, underlying_symbol: str) -> Dict[str, any]:
        """Dynamically extracts live lot size, strike intervals, and active expiries from exchange metadata."""
        if self._df is None:
            if not self.load():
                return {}

        symbol = underlying_symbol.upper()
        # Find OPTIDX contracts
        opts = self._df[
            (self._df["SEM_TRADING_SYMBOL"].str.startswith(f"{symbol}-")) &
            (self._df["SEM_INSTRUMENT_NAME"] == "OPTIDX")
        ]

        if opts.empty:
            return {}

        # 1. Dynamic Lot Size from exchange metadata
        lot_size = int(opts["SEM_LOT_UNITS"].dropna().iloc[0])

        # 2. Dynamic Expiry Dates sorted chronologically
        expiries = sorted(
            [exp for exp in opts["SEM_EXPIRY_DATE"].dropna().unique() if str(exp) != "nan"]
        )

        # Filter out past expiries
        now_str = datetime.now().strftime("%Y-%m-%d")
        valid_expiries = [e for e in expiries if str(e)[:10] >= now_str]

        # 3. Dynamic Strike Interval calculated from strike distribution
        strikes = sorted(opts["SEM_STRIKE_PRICE"].dropna().unique())
        strike_diffs = pd.Series(strikes).diff().dropna()
        strike_interval = int(strike_diffs.mode().iloc[0]) if not strike_diffs.empty else 50

        # 4. Dynamic Tick Size
        tick_size = float(opts["SEM_TICK_SIZE"].dropna().iloc[0]) / 100.0 if opts["SEM_TICK_SIZE"].iloc[0] > 1 else float(opts["SEM_TICK_SIZE"].iloc[0])

        return {
            "symbol": symbol,
            "lot_size": lot_size,
            "strike_interval": strike_interval,
            "tick_size": tick_size,
            "active_expiries": valid_expiries,
            "nearest_expiry": valid_expiries[0] if valid_expiries else None
        }

    def get_option_contract(
        self,
        underlying_symbol: str,
        strike: float,
        option_type: str,
        expiry: Optional[str] = None
    ) -> Optional[Dict[str, any]]:
        """Resolves the exact security ID, trading symbol, and exchange specs for an option dynamically."""
        if self._df is None:
            if not self.load():
                return None

        symbol = underlying_symbol.upper()
        opt_type = option_type.upper()

        opts = self._df[
            (self._df["SEM_TRADING_SYMBOL"].str.startswith(f"{symbol}-")) &
            (self._df["SEM_INSTRUMENT_NAME"] == "OPTIDX") &
            (self._df["SEM_STRIKE_PRICE"] == strike) &
            (self._df["SEM_OPTION_TYPE"] == opt_type)
        ]

        if opts.empty:
            return None

        if expiry:
            opts = opts[opts["SEM_EXPIRY_DATE"].str.startswith(str(expiry)[:10])]

        if opts.empty:
            return None

        row = opts.iloc[0]
        return {
            "security_id": str(row["SEM_SMST_SECURITY_ID"]),
            "trading_symbol": str(row["SEM_TRADING_SYMBOL"]),
            "custom_symbol": str(row["SEM_CUSTOM_SYMBOL"]),
            "lot_size": int(row["SEM_LOT_UNITS"]),
            "strike": float(row["SEM_STRIKE_PRICE"]),
            "option_type": str(row["SEM_OPTION_TYPE"]),
            "expiry_date": str(row["SEM_EXPIRY_DATE"]),
            "exchange": str(row["SEM_EXM_EXCH_ID"]),
            "segment": str(row["SEM_SEGMENT"])
        }

