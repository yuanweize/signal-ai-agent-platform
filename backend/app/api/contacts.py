"""
Contacts API Router — sync and fetch contacts from the Signal backend.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import AdminUser, get_current_admin
from app.services.signal_client import signal_client

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get("")
async def list_contacts(
    admin: AdminUser = Depends(get_current_admin),
):
    """
    List all contacts currently known by the Signal account.
    """
    contacts = await signal_client.list_contacts()
    return {"contacts": contacts}


@router.post("/sync")
async def sync_contacts(
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Trigger a contact synchronization with all linked devices.
    """
    success = await signal_client.sync_contacts()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to sync contacts")
    return {"ok": True}


@router.get("/{uuid}/avatar")
async def get_contact_avatar(
    uuid: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Fetch the contact's avatar as raw bytes.
    """
    content = await signal_client.get_contact_avatar(uuid)
    if not content:
        raise HTTPException(status_code=404, detail="Avatar not found")

    # Assuming PNG or JPEG, let browser sniff or default to image/jpeg
    return Response(content=content, media_type="image/jpeg")
