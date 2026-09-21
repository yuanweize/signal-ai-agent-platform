"""
Devices and Accounts API Router — manage Signal profile and linked devices.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import AdminUser, get_current_admin
from app.services.signal_client import signal_client

router = APIRouter(prefix="/account", tags=["Account"])


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    about: str | None = None


@router.get("/profile")
async def get_profile(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get the bot's Signal profile info.

    Note: signal-cli-rest-api does not expose a GET /v1/profiles endpoint.
    We return the profile from the contacts list (own number) if available,
    otherwise return the configured phone number.
    """
    phone = None
    try:
        from app.config import settings as app_settings

        phone = app_settings.signal_phone_number
    except Exception:
        pass

    return {
        "number": phone or "",
        "name": None,
        "about": None,
        "note": "Signal CLI REST API does not provide a GET profile endpoint. Use PUT to update.",
    }


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
