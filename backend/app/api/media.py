"""
Media API Router — serves Signal attachments to the web client.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.api.deps import AdminUser, get_current_admin
from app.services.signal_client import signal_client

router = APIRouter(prefix="/media", tags=["Media"])


@router.get("/{attachment_id}")
async def get_attachment(
    attachment_id: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Fetch an attachment's raw bytes from the Signal backend.
    """
    content = await signal_client.serve_attachment(attachment_id)
    if not content:
        raise HTTPException(status_code=404, detail="Attachment not found or expired")

    # In a full implementation, we might want to guess the mimetype based on headers
    # or the attachment schema. For now, signal-cli usually doesn't give us the MIME
    # in the serve endpoint unless we stored it in the DB previously.
    # We'll return it as application/octet-stream and let the browser sniff it,
    # or we can try to use python-magic if necessary.
    return Response(content=content, media_type="application/octet-stream")


@router.delete("/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """
    Delete an attachment from the Signal internal storage to free space.
    """
    success = await signal_client.delete_attachment(attachment_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete attachment")
    return {"ok": True}
