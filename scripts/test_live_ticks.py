import os
import sys
import time
from dhanhq import DhanContext, MarketFeed
from dotenv import load_dotenv

load_dotenv(".env")

client_id = os.getenv("DHAN_CLIENT_ID")
access_token = os.getenv("DHAN_ACCESS_TOKEN")

if not client_id or not access_token:
    print("[ERROR] Credentials missing in .env")
    sys.exit(1)

print(f"[INFO] Connecting to Live Dhan Market Feed for client {client_id[:4]}******")
context = DhanContext(client_id, access_token)

# Instruments to subscribe:
# (exchange_segment, security_id, request_code)
# Exchange segments: IDX=0, NSE=1, NSE_FNO=2
# Nifty 50 Index Security ID is "13" on Dhan IDX
# Bank Nifty Index Security ID is "25" on Dhan IDX
# Request codes: Ticker=15, Quote=17, Depth=19, Full=21
instruments = [
    (MarketFeed.IDX, "13", MarketFeed.Quote),   # NIFTY 50
    (MarketFeed.IDX, "25", MarketFeed.Quote)    # BANK NIFTY
]

tick_count = 0
max_ticks = 5

def on_connect(feed):
    print("[SUCCESS] Dhan WebSocket connected and subscribed to instruments!")

def on_message(feed, message):
    global tick_count
    tick_count += 1
    print(f"[TICK {tick_count}] Received: {message}")
    if tick_count >= max_ticks:
        print("[INFO] Reached tick limit. Closing connection...")
        feed.close_connection()

def on_error(feed, error):
    print(f"[ERROR] Feed error: {error}")

def on_close(feed):
    print("[INFO] Feed connection closed.")

feed = MarketFeed(
    dhan_context=context,
    instruments=instruments,
    version="v2",
    on_connect=on_connect,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close
)

# Run in separate thread or run
t = feed.start()

start_time = time.time()
while tick_count < max_ticks and (time.time() - start_time) < 15:
    time.sleep(0.5)

feed.close_connection()
print("[INFO] Test finished cleanly.")

