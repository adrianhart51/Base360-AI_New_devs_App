from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import property_belongs_to_tenant
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # Falling back to a shared placeholder tenant would merge every
    # tenant-less user into one bucket, so refuse the request instead.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")

    # Authentication alone is not authorisation: confirm the caller's tenant
    # actually owns this property before returning any figures for it.
    if not await property_belongs_to_tenant(property_id, tenant_id):
        raise HTTPException(status_code=404, detail="Property not found")

    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
