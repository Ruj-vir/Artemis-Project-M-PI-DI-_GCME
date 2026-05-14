"""
auth_service.py — SSO Logic หลักทั้งหมด
เทียบกับ: auth.service.ts (Angular)

หน้าที่:
  - กำหนด SSO URL และ config
  - redirect ไปหน้า login ของ SSO
  - บันทึก / ลบ session (token + user)
  - ดึง user ปัจจุบันจาก session
"""
import urllib.parse
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse

# ─── SSO Configuration ────────────────────────────────────────────────────────
SSO_LOGIN_URL = "https://login.gcmeapps.com/signin/"
SSO_CALLBACK_URL = "https://artimis.gcmeapps.com/home"   # SSO จะ redirect กลับมาที่นี่
SESSION_SECRET = "artemis-secret-key-change-in-production"


# ─── Core Functions ───────────────────────────────────────────────────────────

def redirect_to_sso() -> RedirectResponse:
    """สร้าง redirect ไปหน้า login ของ SSO พร้อม callback URL"""
    sso_url = SSO_LOGIN_URL + urllib.parse.quote(SSO_CALLBACK_URL, safe="")
    return RedirectResponse(url=sso_url, status_code=302)


def get_session_user(request: Request) -> Optional[str]:
    """ดึง username จาก session — คืน None ถ้ายังไม่ได้ login"""
    return request.session.get("user")


def get_session_token(request: Request) -> Optional[str]:
    """ดึง token จาก session"""
    return request.session.get("token")


def save_auth(request: Request, token: str, user: str) -> None:
    """บันทึก token + user ลง session หลัง SSO callback สำเร็จ"""
    request.session["token"] = token
    request.session["user"] = user


def clear_auth(request: Request) -> None:
    """ลบ session ทั้งหมด (logout)"""
    request.session.pop("token", None)
    request.session.pop("user", None)
