"""
auth_guard.py — Guard ป้องกัน route ที่ต้อง login ก่อน
เทียบกับ: auth.guard.ts + authGuard / rootGuard ใน app.routes.ts (Angular)

หน้าที่:
  - ตรวจสอบว่า user login อยู่ไหม
  - ถ้าไม่ login → raise NotAuthenticatedException
  - main.py จัดการ exception นี้โดย redirect ไป SSO อัตโนมัติ

วิธีใช้ใน route:
  @app.get("/example")
  async def example(current_user: str = Depends(require_auth)):
      ...
"""
from fastapi import Request


class NotAuthenticatedException(Exception):
    """Raise เมื่อ user ไม่ได้ login — main.py จะ redirect ไป SSO"""
    pass


async def require_auth(request: Request) -> str:
    """
    FastAPI Dependency — ตรวจสอบ session ก่อนเข้า route
    คืน username ถ้า login แล้ว, raise NotAuthenticatedException ถ้ายังไม่ได้ login
    """
    user = request.session.get("user")
    if not user:
        raise NotAuthenticatedException()
    return user
