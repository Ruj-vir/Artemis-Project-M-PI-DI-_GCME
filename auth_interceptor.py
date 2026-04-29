"""
auth_interceptor.py — Middleware แนบ token ทุก API request อัตโนมัติ
เทียบกับ: auth.interceptor.ts (Angular)

หน้าที่:
  - ดึง token จาก session
  - แนบ Authorization: Bearer <token> ใน request.state
    เพื่อให้ downstream code หรือ internal API calls ใช้ได้
  - ไม่บล็อก request ถ้าไม่มี token (auth_guard จัดการแทน)

วิธีใช้ใน main.py:
  from auth_interceptor import AuthInterceptor
  app.add_middleware(AuthInterceptor)
"""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class AuthInterceptor(BaseHTTPMiddleware):
    """
    Middleware — แนบ token จาก session เข้า request.state.token
    เทียบกับ authInterceptor ใน Angular ที่แนบ Authorization header ทุก HTTP call
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # ดึง token จาก session (ถ้ามี)
        token: str | None = None
        if hasattr(request, "session"):
            token = request.session.get("token")

        # แนบ token ไว้ใน request.state ให้ทุก route ใช้ได้
        request.state.token = token

        response = await call_next(request)
        return response
