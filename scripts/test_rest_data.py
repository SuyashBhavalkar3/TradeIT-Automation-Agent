import os
from dhanhq import DhanContext, dhanhq
from dotenv import load_dotenv

load_dotenv(".env")
client_id = os.getenv("DHAN_CLIENT_ID")
access_token = os.getenv("DHAN_ACCESS_TOKEN")

context = DhanContext(client_id, access_token)
dhan = dhanhq(context)

# Check positions, holdings, orders
print("Positions:", dhan.get_positions())
print("Orders:", dhan.get_order_list())
print("Holdings:", dhan.get_holdings())

