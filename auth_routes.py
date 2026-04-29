"""
auth_routes.py — SSO Callback Routes (/home, /logout)
เทียบกับ: home.component.ts (Angular)

หน้าที่:
  - GET /home  → รับ token + user จาก SSO server แล้วบันทึก session
  - GET /logout → ล้าง session แล้ว redirect ไป SSO login

วิธีใช้ใน main.py:
  from auth_routes import router as auth_router
  app.include_router(auth_router)
"""
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from auth_service import clear_auth, redirect_to_sso, save_auth

router = APIRouter()


@router.get("/home")
async def sso_callback(
    request: Request,
    token: Optional[str] = None,
    idToken: Optional[str] = None,
    user: Optional[str] = None,
    id: Optional[str] = None,
):
    """
    SSO Callback — SSO server redirect กลับมาที่นี่พร้อม token + user
    เทียบกับ HomeComponent.handleAuth() ใน Angular
    """
    resolved_token = token or idToken
    resolved_user = user or id or "sso-user"

    if resolved_token and resolved_user:
        save_auth(request, resolved_token, resolved_user)
        return RedirectResponse(url="/", status_code=302)

    # ไม่มี token → redirect กลับ SSO ใหม่
    return redirect_to_sso()


@router.get("/logout")
async def logout(request: Request):
    """
    Logout — ล้าง session แล้ว redirect ไป SSO login
    เทียบกับ AuthService.logout() ใน Angular
    """
    clear_auth(request)
    return redirect_to_sso()
