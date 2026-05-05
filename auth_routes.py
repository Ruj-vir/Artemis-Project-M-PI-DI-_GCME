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
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from auth_service import clear_auth, redirect_to_sso, save_auth

templates = Jinja2Templates(directory="templates")

router = APIRouter()


@router.get("/login-page")
async def login_page(request: Request):
    """หน้า Login — แสดงปุ่มก่อนไปหน้า SSO"""
    return templates.TemplateResponse("LogIn_page.html", {"request": request})


@router.get("/login")
async def login_redirect():
    """กด ปุ่ม Log in → redirect ไป SSO"""
    return redirect_to_sso()


@router.get("/home/{user}/{token}")
async def sso_callback(
    request: Request,
    user: str,
    token: str,
):
    """
    SSO Callback — SSO server redirect กลับมาที่นี่พร้อม user + token เป็น path parameter
    รูปแบบ: /home/{user}/{token}
    เทียบกับ HomeComponent.handleAuth() ใน Angular
    """
    if token and user:
        save_auth(request, token, user)
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
    response = RedirectResponse(url="/login-page", status_code=302)
    response.delete_cookie("session")
    return response
