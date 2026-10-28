import os
from dhanhq import DhanContext, dhanhq
from dotenv import load_dotenv

load_dotenv(".env")
client_id = os.getenv("DHAN_CLIENT_ID")
access_token = os.getenv("DHAN_ACCESS_TOKEN")

context = DhanContext(client_id, access_token)
dhan = dhanhq(context)

# Test various segments:
# 13 is Nifty 50, 25 is Bank Nifty in Dhan Index
# 11536 is TCS, 1333 is HDFC Bank in NSE_EQ
test_cases = [
    {"IDX_I": [13, 25]},
    {"NSE_EQ": [1333, 11536]},
    {"NSE_INDEX": [13, 25]}
]

for sc in test_cases:
    try:
        print(f"\n--- Testing ticker_data for {sc} ---")
        res = dhan.ticker_data(sc)
        print("LTP Response:", res)
    except Exception as e:
        print("Error:", e)

