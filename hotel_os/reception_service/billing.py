# ============================================================
# HotelOS — Billing Calculation Algorithm
#
# Formula:
#   room_total          = rate_per_night × actual_nights
#   room_service_total  = sum of all room_service_charges
#   extra_total         = sum of all extra_charges (minibar, late fee, etc.)
#   subtotal            = room_total + room_service_total + extra_total
#   discount_amount     = subtotal × (discount_pct / 100)
#   grand_total         = subtotal - discount_amount
#
# Edge cases handled:
#   - Early checkout     : actual_nights = 1 (minimum charge is 1 night)
#   - Zero charges       : grand_total = 0.0 (no crash)
#   - discount_pct = 100 : grand_total = 0.0
#   - Negative amounts   : ignored / clamped to 0
# ============================================================

from __future__ import annotations
import logging
from typing import Optional

from reception_service.models import Guest, BillResponse

logger = logging.getLogger("hotelos.reception.billing")


def calculate_bill(
    guest: Guest,
    rate_per_night: float,
    early_checkout: bool = False,
    late_fee: float = 0.0,
) -> BillResponse:
    """
    Calculate the full bill for a checking-out guest.

    Args:
        guest          : Guest dataclass with all charges attached
        rate_per_night : nightly room rate in USD
        early_checkout : if True, charge minimum 1 night
        late_fee       : optional late-checkout surcharge

    Returns:
        BillResponse Pydantic model with full itemised breakdown.
    """

    # ── Actual nights ──────────────────────────────────────────────
    actual_nights = max(1, guest.nights) if early_checkout else max(1, guest.nights)
    # If guest stayed 0 nights (same-day cancellation) → charge 1 night minimum
    if actual_nights <= 0:
        actual_nights = 1

    # ── Room charge ────────────────────────────────────────────────
    room_rate  = max(0.0, rate_per_night)
    room_total = round(room_rate * actual_nights, 2)

    # ── Room service charges ───────────────────────────────────────
    rs_items = [
        c for c in guest.room_service_charges
        if isinstance(c.get("amount"), (int, float)) and c["amount"] > 0
    ]
    room_service_total = round(sum(c["amount"] for c in rs_items), 2)

    # ── Extra charges (minibar, late checkout, etc.) ───────────────
    if late_fee > 0:
        guest.add_extra_charge("Late checkout fee", round(late_fee, 2))

    extra_items = [
        c for c in guest.extra_charges
        if isinstance(c.get("amount"), (int, float)) and c["amount"] > 0
    ]
    extra_total = round(sum(c["amount"] for c in extra_items), 2)

    # ── Subtotal & discount ────────────────────────────────────────
    subtotal       = round(room_total + room_service_total + extra_total, 2)
    discount_pct   = max(0.0, min(100.0, guest.discount_pct))
    discount_amount = round(subtotal * (discount_pct / 100), 2)
    grand_total    = round(max(0.0, subtotal - discount_amount), 2)

    # ── Itemised breakdown ─────────────────────────────────────────
    breakdown: list[dict] = [
        {"description": f"Room {guest.room_number} × {actual_nights} night(s) @ ${room_rate}/night",
         "amount": room_total},
    ]
    for c in rs_items:
        breakdown.append({"description": c["description"], "amount": c["amount"]})
    for c in extra_items:
        breakdown.append({"description": c["description"], "amount": c["amount"]})
    if discount_amount > 0:
        breakdown.append({"description": f"Discount ({discount_pct:.0f}%)", "amount": -discount_amount})

    logger.info(
        "Bill for %s | room=%s nights=%d rs=%.2f extra=%.2f disc=%.2f total=%.2f",
        guest.name, guest.room_number, actual_nights,
        room_service_total, extra_total, discount_amount, grand_total,
    )

    return BillResponse(
        guest_name=guest.name,
        room_number=guest.room_number,
        nights=actual_nights,
        room_rate=room_rate,
        room_total=room_total,
        room_service_total=room_service_total,
        extra_charges_total=extra_total,
        discount_amount=discount_amount,
        grand_total=grand_total,
        breakdown=breakdown,
    )
