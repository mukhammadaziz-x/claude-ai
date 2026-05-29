# ============================================================
# HotelOS — Room Assignment Algorithm
#
# Step-by-step logic:
#
# 1. Filter by room_type  — must match guest's booking exactly.
# 2. Filter by status     — only STATUS_CLEAN rooms are eligible.
# 3. Filter by occupancy  — room.guest_name must be None.
# 4. Floor preference     — if guest requested a floor, try that floor first.
#                           If nothing on that floor, fall back to all floors.
# 5. Longest-clean sort   — among eligible rooms sort by cleaned_at ASC
#                           so the room cleaned longest ago is prioritised
#                           (ensures even rotation of room usage).
# 6. Proximity tiebreaker — if the guest requested 'elevator' or 'stairs',
#                           prefer rooms matching that attribute.
# 7. Return best room     — first item after sorting, or None if no room found.
# ============================================================

from __future__ import annotations
import logging
from typing import Optional

from reception_service.models import Room

logger = logging.getLogger("hotelos.reception.algorithm")


def assign_room(
    rooms: dict[int, Room],
    room_type: str,
    floor_preference: Optional[int] = None,
    proximity_pref: Optional[str] = None,
) -> Optional[Room]:
    """
    Core room-assignment algorithm.

    Args:
        rooms            : full room inventory {room_number: Room}
        room_type        : requested room type ('single','double','suite','accessible')
        floor_preference : preferred floor number, or None
        proximity_pref   : 'elevator' | 'stairs' | None

    Returns:
        The best Room object, or None if no room is available.
    """

    # ── STEP 1 & 2 & 3 ─ type + clean + unoccupied ────────────────
    eligible: list[Room] = [
        r for r in rooms.values()
        if r.room_type == room_type and r.is_available()
    ]

    if not eligible:
        logger.info("No eligible rooms for type='%s'", room_type)
        return None

    # ── STEP 4 ─ floor preference ──────────────────────────────────
    if floor_preference is not None:
        on_preferred_floor = [r for r in eligible if r.floor == floor_preference]
        # Use preferred-floor subset if available; otherwise keep all eligible
        if on_preferred_floor:
            eligible = on_preferred_floor
            logger.debug("Applied floor preference %d → %d room(s)", floor_preference, len(eligible))
        else:
            logger.debug(
                "Floor %d has no eligible rooms — falling back to any floor", floor_preference
            )

    # ── STEP 5 ─ longest-clean sort (cleaned_at ASC) ───────────────
    eligible.sort(key=lambda r: r.cleaned_at)

    # ── STEP 6 ─ proximity tiebreaker ─────────────────────────────
    if proximity_pref == "elevator":
        preferred = [r for r in eligible if r.near_elevator]
        if preferred:
            eligible = preferred
    elif proximity_pref == "stairs":
        preferred = [r for r in eligible if r.near_stairs]
        if preferred:
            eligible = preferred

    # ── STEP 7 ─ return best room ──────────────────────────────────
    best = eligible[0]
    logger.info(
        "Assigned room %d (type=%s, floor=%d, cleaned_at=%s)",
        best.number, best.room_type, best.floor, best.cleaned_at.isoformat()
    )
    return best
