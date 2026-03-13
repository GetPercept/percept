"""Team API key authentication middleware."""
from fastapi import Request, HTTPException, Depends
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from percept.mesh.server.database import get_member_by_key


async def get_current_member(request: Request) -> dict:
    """Extract and validate API key from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Use: Bearer <api_key>")
    
    api_key = auth[7:].strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Empty API key")
    
    member = get_member_by_key(api_key)
    if not member:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    
    return member


async def require_admin(member: dict = Depends(get_current_member)) -> dict:
    """Require admin role."""
    if member["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return member


async def require_write(member: dict = Depends(get_current_member)) -> dict:
    """Require write access (admin or member role)."""
    if member["role"] not in ("admin", "member"):
        raise HTTPException(status_code=403, detail="Write access required")
    return member
