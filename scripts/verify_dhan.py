import os
import sys
from dhanhq import DhanContext, dhanhq
from dotenv import load_dotenv

# Load credentials from .env
load_dotenv(".env")

client_id = os.getenv("DHAN_CLIENT_ID")
access_token = os.getenv("DHAN_ACCESS_TOKEN")

if not client_id or not access_token or "dummy" in client_id:
    print("[ERROR] DHAN_CLIENT_ID or DHAN_ACCESS_TOKEN is missing or still set to dummy values in .env")
    sys.exit(1)

print(f"[INFO] Initializing DhanHQ client for Client ID: {client_id[:4]}******")
context = DhanContext(client_id, access_token)
dhan = dhanhq(context)

try:
    # 1. Test REST Authentication via fund limits check
    print("[INFO] Testing REST API authentication (get_fund_limits)...")
    funds = dhan.get_fund_limits()
    print("[SUCCESS] Connected to Dhan API!")
    print(f"Response status: {funds.get('status')}")
    if funds.get("status") == "success":
        data = funds.get("data", {})
        avail = data.get("availabelBalance", data.get("availableBalance", "N/A"))
        print(f"[INFO] Account connected successfully. Available Balance: {avail}")
    else:
        print(f"[REPLY] {funds}")

except Exception as e:
    print(f"[ERROR] REST Connection failed: {e}")
