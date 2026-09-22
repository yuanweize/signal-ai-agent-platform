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
    """Get the bot's Signal profile info."""
    phone = ""
    name = ""
    try:
        from app.config import settings as app_settings

        phone = app_settings.signal_phone_number or ""
        name = app_settings.bot_name or ""
    except Exception:
        pass

    return {
        "number": phone,
        "name": name,
        "about": "",
        "note": "Signal CLI REST API does not provide a GET profile endpoint. Use PUT to update.",
    }


@router.put("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update the Signal profile name and about text."""
    from app.config import settings as app_settings

    if request.name:
        app_settings.bot_name = request.name.strip()

    if (app_settings.signal_api_url or "").strip() and app_settings.signal_phone_number:
        success = await signal_client.update_profile(name=request.name, about=request.about)
        if not success:
            raise HTTPException(status_code=502, detail="Failed to update Signal profile on gateway")
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
