"""
Devices and Accounts API Router — manage Signal profile and linked devices.
"""

from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AdminUser, get_current_admin
from app.services.signal_client import signal_client

router = APIRouter(prefix="/account", tags=["Account"])


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = None
    about: Optional[str] = None


@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update the Signal profile name and about text."""
    success = await signal_client.update_profile(name=request.name, about=request.about)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to update profile")
    return {"ok": True}


@router.get("/devices")
async def list_devices(
    admin: AdminUser = Depends(get_current_admin),
):
    """List all devices linked to this Signal account."""
    devices = await signal_client.list_devices()
    return {"devices": devices}


@router.delete("/devices/{device_id}")
async def remove_device(
    device_id: int,
    admin: AdminUser = Depends(get_current_admin),
):
    """Unlink a specific device."""
    success = await signal_client.remove_device(device_id)
    if not success:
        raise HTTPException(status_code=502, detail="Failed to remove device")
    return {"ok": True}
