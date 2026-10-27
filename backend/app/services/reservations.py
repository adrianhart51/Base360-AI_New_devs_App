from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

import pytz
from sqlalchemy import text

from app.core.database_pool import db_pool


def _month_bounds_utc(month: int, year: int, timezone_name: str):
    """
    Build month boundaries in the property's local timezone, then convert to UTC.

    check_in_date is TIMESTAMPTZ. Naive boundaries are interpreted as UTC, which
    misclassifies bookings that fall either side of local midnight - e.g. a
    booking at 2024-02-29 23:30 UTC is 2024-03-01 00:30 in Europe/Paris and
    therefore belongs to March for a Paris property.
    """
    tz = pytz.timezone(timezone_name)
    start_local = tz.localize(datetime(year, month, 1))
    if month < 12:
        end_local = tz.localize(datetime(year, month + 1, 1))
    else:
        end_local = tz.localize(datetime(year + 1, 1, 1))
    return start_local.astimezone(pytz.UTC), end_local.astimezone(pytz.UTC)


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Decimal:
    """
    Calculates revenue for a specific month, in the property's own timezone.
    """
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        timezone_result = await session.execute(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        property_row = timezone_result.fetchone()
        if property_row is None:
            return Decimal("0.00")

        start_date, end_date = _month_bounds_utc(month, year, property_row.timezone)

        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS total
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_date
                  AND check_in_date <  :end_date
            """),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        return Decimal(str(result.scalar() or "0"))


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        # COALESCE/COUNT without GROUP BY always yields exactly one row, so a
        # property with no reservations reports 0.00 rather than no row at all.
        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS total_revenue,
                       COUNT(*)                       AS reservation_count
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
            """),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        row = result.fetchone()

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(Decimal(str(row.total_revenue))),
            "currency": "USD",
            "count": row.reservation_count,
        }
