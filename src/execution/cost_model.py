from dataclasses import dataclass


@dataclass(frozen=True)
class TradeCosts:
    brokerage: float
    stt: float                  # Securities Transaction Tax (0.125% on sell premium)
    exchange_charges: float     # NSE turnover charges (~0.0505%)
    sebi_charges: float         # SEBI turnover charge (₹10 per crore)
    stamp_duty: float           # Stamp duty (0.003% on buy value)
    gst: float                  # 18% on (Brokerage + Exchange charges + SEBI charges)
    total_costs: float


class IndianFOCostModel:
    """
    Calculates realistic statutory transaction charges, taxes, and brokerage for Indian NSE F&O options trades.
    """

    @staticmethod
    def calculate_option_trade_costs(
        buy_price: float,
        sell_price: float,
        quantity: int,
        brokerage_per_order: float = 20.0  # Standard ₹20 per executed order
    ) -> TradeCosts:
        buy_turnover = buy_price * quantity
        sell_turnover = sell_price * quantity
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage: ₹20 on buy + ₹20 on sell
        brokerage = brokerage_per_order * 2.0

        # 2. STT: 0.125% on sell turnover for options
        stt = round(sell_turnover * 0.00125, 2)

        # 3. Exchange Turnover Charges: 0.0505% on total turnover
        exchange_charges = round(total_turnover * 0.000505, 2)

        # 4. SEBI Turnover Fee: ₹10 per crore (0.0001%)
        sebi_charges = round(total_turnover * 0.000001, 2)

        # 5. Stamp Duty: 0.003% on buy turnover
        stamp_duty = round(buy_turnover * 0.00003, 2)

        # 6. GST: 18% on (Brokerage + Exchange + SEBI)
        gst = round((brokerage + exchange_charges + sebi_charges) * 0.18, 2)

        total_costs = round(brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst, 2)

        return TradeCosts(
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exchange_charges,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            gst=gst,
            total_costs=total_costs
        )

