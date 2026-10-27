import bisect
import io

import pandas as pd
import uvicorn
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional

# ─── SSO Imports (4 ไฟล์หลัก) ────────────────────────────────────────────────
from auth_service import SESSION_SECRET, redirect_to_sso, save_auth
from auth_guard import require_auth, NotAuthenticatedException
from auth_routes import router as auth_router
from auth_interceptor import AuthInterceptor

# ─── User Store ───────────────────────────────────────────────────────────────
from user_store import (
    init_users_if_empty, verify_user, get_all_users,
    create_user, update_user, delete_user, public_view, update_last_login,
)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ─── Init users.json ถ้ายังไม่มี ─────────────────────────────────────────────
init_users_if_empty()

# ─── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(AuthInterceptor)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# ─── SSO Routes (/home callback + /logout) ───────────────────────────────────
app.include_router(auth_router)

# ─── Exception Handler: redirect ไป SSO ถ้าไม่ได้ login ─────────────────────
@app.exception_handler(NotAuthenticatedException)
async def not_authenticated(request: Request, exc: NotAuthenticatedException):
    return RedirectResponse(url="/login-page", status_code=302)


# ─── H2S Corrosion Data ───────────────────────────────────────────────────────
TEMP_COLUMNS = [245, 273, 301, 328, 356, 384, 412, 440, 467, 495, 523, float("inf")]

H2S_CORROSION_DATA = {
    (0.0,    0.002 ): {"Naphtha": [0.03, 0.03, 0.03, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 0.25, 0.36, 0.46],
                       "Gas Oil":  [0.03, 0.03, 0.03, 0.05, 0.08, 0.13, 0.18, 0.25, 0.36, 0.51, 0.66, 0.86]},
    (0.0021, 0.0035): {"Naphtha": [0.03, 0.03, 0.03, 0.05, 0.10, 0.15, 0.20, 0.30, 0.41, 0.56, 0.74, 0.94],
                       "Gas Oil":  [0.03, 0.05, 0.08, 0.10, 0.18, 0.28, 0.41, 0.56, 0.79, 1.04, 1.40, 1.80]},
    (0.0036, 0.008 ): {"Naphtha": [0.03, 0.03, 0.05, 0.08, 0.13, 0.18, 0.28, 0.38, 0.53, 0.74, 0.97, 1.27],
                       "Gas Oil":  [0.03, 0.05, 0.10, 0.15, 0.23, 0.36, 0.53, 0.74, 1.04, 1.40, 1.85, 2.39]},
    (0.0081, 0.035 ): {"Naphtha": [0.03, 0.05, 0.08, 0.13, 0.23, 0.33, 0.48, 0.69, 0.97, 1.30, 1.70, 2.21],
                       "Gas Oil":  [0.05, 0.10, 0.15, 0.25, 0.41, 0.64, 0.91, 1.30, 1.80, 2.44, 3.30, 4.32]},
    (0.0351, 0.08  ): {"Naphtha": [0.03, 0.05, 0.10, 0.18, 0.25, 0.41, 0.58, 0.84, 1.17, 1.57, 2.08, 2.79],
                       "Gas Oil":  [0.05, 0.10, 0.20, 0.33, 0.51, 0.76, 1.12, 1.60, 2.21, 3.05, 4.06, 5.08]},
    (0.081,  0.3   ): {"Naphtha": [0.05, 0.08, 0.15, 0.25, 0.38, 0.58, 0.86, 1.22, 1.68, 2.29, 3.05, 3.81],
                       "Gas Oil":  [0.08, 0.15, 0.28, 0.46, 0.74, 1.12, 1.63, 2.31, 3.30, 4.32, 5.84, 7.62]},
    (0.301,  0.75  ): {"Naphtha": [0.05, 0.10, 0.18, 0.28, 0.43, 0.66, 0.97, 1.37, 1.91, 2.54, 3.30, 4.32],
                       "Gas Oil":  [0.10, 0.18, 0.30, 0.53, 0.81, 1.24, 1.83, 2.54, 3.56, 4.83, 6.35, 8.38]},
    (0.751,  1.0   ): {"Naphtha": [0.08, 0.13, 0.20, 0.33, 0.53, 0.81, 1.19, 1.70, 2.36, 3.30, 4.32, 5.59],
                       "Gas Oil":  [0.13, 0.23, 0.38, 0.66, 1.02, 1.55, 2.26, 3.30, 4.57, 6.10, 7.87, 10.41]},
}

SUSCEPTIBLE_MATERIALS = ["Carbon Steel", "Low Alloy", "300 series SS", "400 series SS"]

# ─── Sulfidation / McConomy Curves ───────────────────────────────────────────
MCCONOMY_CURVES = {
    "Carbon Steel": [[260,0.10],[288,0.20],[316,0.38],[343,0.64],[371,1.02],[399,1.65],[427,2.54],[454,3.81],[482,5.84],[510,8.89]],
    "1Cr-0.5Mo":    [[260,0.05],[288,0.10],[316,0.18],[343,0.30],[371,0.51],[399,0.84],[427,1.40],[454,2.29],[482,3.56],[510,5.59]],
    "2.25Cr-1Mo":   [[260,0.03],[288,0.05],[316,0.10],[343,0.18],[371,0.30],[399,0.51],[427,0.84],[454,1.40],[482,2.29],[510,3.56]],
    "5Cr-0.5Mo":    [[260,0.013],[288,0.025],[316,0.05],[343,0.09],[371,0.15],[399,0.25],[427,0.41],[454,0.69],[482,1.14],[510,1.78]],
    "9Cr-1Mo":      [[260,0.008],[288,0.013],[316,0.025],[343,0.046],[371,0.08],[399,0.13],[427,0.22],[454,0.37],[482,0.61],[510,0.97]],
    "12Cr":         [[260,0.005],[288,0.008],[316,0.013],[343,0.025],[371,0.046],[399,0.08],[427,0.13],[454,0.22],[482,0.37],[510,0.61]],
    "SS304":        [[260,0.003],[288,0.005],[316,0.008],[343,0.013],[371,0.025],[399,0.046],[427,0.076],[454,0.13],[482,0.22],[510,0.36]],
    "SS316":        [[260,0.002],[288,0.003],[316,0.005],[343,0.010],[371,0.018],[399,0.030],[427,0.051],[454,0.086],[482,0.14],[510,0.24]],
    "SS410":        [[260,0.004],[288,0.007],[316,0.012],[343,0.020],[371,0.036],[399,0.061],[427,0.10],[454,0.17],[482,0.28],[510,0.46]],
}

# ─── HCl Corrosion Tables (pH × temp-range [0-38, >38-52, >52-79, >79-93 °C]) ─
HCL_CS_TABLE = {
    "0-0.5":     [25.37,25.37,25.37,25.37], "0.51-0.80": [22.86,25.37,25.37,25.37],
    "0.81-1.25": [10.16,25.37,25.37,25.37], "1.26-1.75": [5.08, 17.78,25.37,25.37],
    "1.76-2.25": [2.54, 7.62, 10.16,14.22], "2.26-2.75": [1.52, 3.30, 5.08, 7.11],
    "2.76-3.25": [1.02, 1.78, 2.54, 3.56],  "3.26-3.75": [0.76, 1.27, 2.29, 3.18],
    "3.76-4.25": [0.51, 1.02, 1.78, 2.54],  "4.26-4.75": [0.25, 0.76, 1.27, 1.78],
    "4.76-5.25": [0.18, 0.51, 0.76, 1.02],  "5.26-5.75": [0.10, 0.38, 0.51, 0.76],
    "5.76-6.25": [0.08, 0.25, 0.38, 0.51],  "6.26-6.80": [0.05, 0.13, 0.18, 0.25],
}
HCL_SS300_TABLE = {
    "0-0.5":     [22.86,25.37,25.37,25.37], "0.51-0.80": [12.70,25.37,25.37,25.37],
    "0.81-1.25": [7.62, 12.70,17.78,25.37], "1.26-1.75": [3.81, 6.60, 10.16,12.70],
    "1.76-2.25": [2.03, 3.56, 5.08, 6.35],  "2.26-2.75": [1.27, 1.78, 2.54, 3.05],
    "2.76-3.25": [0.76, 1.02, 1.27, 1.65],  "3.26-3.75": [0.51, 0.64, 0.76, 0.89],
    "3.76-4.25": [0.25, 0.38, 0.51, 0.64],  "4.26-4.75": [0.13, 0.18, 0.25, 0.30],
    "4.76-5.25": [0.10, 0.13, 0.15, 0.18],  "5.26-5.75": [0.08, 0.10, 0.13, 0.15],
    "5.76-6.25": [0.05, 0.08, 0.10, 0.13],  "6.26-6.80": [0.03, 0.05, 0.08, 0.10],
}

# ─── HTHA / Nelson Curves (H2 partial pressure psia → max safe temp °C) ────────
NELSON_CURVES = {
    "Carbon Steel": [[25,222],[50,238],[100,258],[200,282],[400,307],[1000,343],[2000,371]],
    "C-0.5Mo":      [[25,249],[50,260],[100,279],[200,304],[400,329],[1000,366],[2000,393]],
    "1Cr-0.5Mo":    [[25,293],[50,307],[100,324],[200,349],[400,374],[1000,410],[2000,438]],
    "2.25Cr-1Mo":   [[25,360],[50,374],[100,391],[200,416],[400,441],[1000,477],[2000,505]],
}

# ─── Helper functions ─────────────────────────────────────────────────────────
def _interp(points, x):
    if x <= points[0][0]:  return points[0][1]
    if x >= points[-1][0]: return points[-1][1]
    for i in range(len(points) - 1):
        x1, y1 = points[i]; x2, y2 = points[i + 1]
        if x1 <= x <= x2:
            return y1 + (y2 - y1) * (x - x1) / (x2 - x1)
    return points[-1][1]

def _level(ratio: float) -> str:
    if ratio > 4:    return "High"
    if ratio >= 1:   return "Medium"
    if ratio >= 0.5: return "Low"
    return "Negligible"

def _std_material(mat_type: str, material: str, grade) -> str:
    mt  = str(mat_type or "").upper()
    mat = str(material or "").upper()
    gr  = str(grade or "")
    if "SS" in mt or any(x in mat for x in ["SA240","SA312","SA213","SA376","A240"]):
        try:   g = int(float(gr.replace("L","").strip()))
        except: g = 0
        return "400 series SS" if g in [410,430,405] else "300 series SS"
    if "CS" in mt or any(x in mat for x in ["SA516","SA106","SA333","A516","A106"]):
        return "Carbon Steel"
    if "LA" in mt or "LOW ALLOY" in mt or any(x in mat for x in ["SA387","SA335","SA182"]):
        return "Low Alloy"
    return "Carbon Steel"

def _mcconomy_key(mat_std: str) -> str:
    return {"300 series SS":"SS304","400 series SS":"SS410","Low Alloy":"1Cr-0.5Mo"}.get(mat_std, "Carbon Steel")

def _hcl_temp_idx(temp) -> int:
    t = float(temp or 25)
    return 0 if t <= 38 else 1 if t <= 52 else 2 if t <= 79 else 3

def _lookup_hcl(table: dict, ph, tidx: int) -> float:
    ph = float(ph or 7)
    ranges = [("0-0.5",0,.5),("0.51-0.80",.51,.80),("0.81-1.25",.81,1.25),
              ("1.26-1.75",1.26,1.75),("1.76-2.25",1.76,2.25),("2.26-2.75",2.26,2.75),
              ("2.76-3.25",2.76,3.25),("3.26-3.75",3.26,3.75),("3.76-4.25",3.76,4.25),
              ("4.26-4.75",4.26,4.75),("4.76-5.25",4.76,5.25),("5.26-5.75",5.26,5.75),
              ("5.76-6.25",5.76,6.25),("6.26-6.80",6.26,6.80)]
    for key, lo, hi in ranges:
        if lo <= ph <= hi: return table[key][tidx]
    return table["6.26-6.80"][tidx] if ph > 6.8 else table["0-0.5"][tidx]

def _has_chem(fluid: str, keywords: list) -> bool:
    f = str(fluid or "").upper()
    return any(k.upper() in f for k in keywords)

def _safe_float(v):
    try:
        if str(v).strip() in ["#REF!","-","","None"]: return None
        return float(v)
    except: return None

def _get_design_cr(design_col, ca_col, life_col):
    v = _safe_float(design_col)
    if v and v > 0: return v
    ca   = _safe_float(ca_col)
    life = _safe_float(life_col)
    if ca and life and life > 0: return ca / life
    return None  # ไม่มีข้อมูล → None (ไม่ใช่ default 1.0)

# ─── 7 Batch Analysis Functions ───────────────────────────────────────────────
def _batch_h2s(temp, mat, dcr, acr=None):
    if not isinstance(temp,(int,float)) or temp <= 230: return "Not Susceptible"
    if not any(m in mat for m in SUSCEPTIBLE_MATERIALS): return "Not Susceptible"
    if not dcr or dcr <= 0: return "N/A"
    if acr: return _level(acr / dcr)
    mole, hc = 0.05, "Gas Oil"
    for (lo, hi), types in H2S_CORROSION_DATA.items():
        if lo <= mole <= hi:
            rates = types.get(hc, [])
            if rates:
                return _level(rates[bisect.bisect_left(TEMP_COLUMNS, temp)] / dcr)
    return "N/A"

def _batch_flue(mat, dcr, temp, acr=None):
    if not isinstance(temp,(int,float)): return "N/A"
    if not any(m in mat for m in ["Carbon Steel","Low Alloy","300 series SS"]): return "Not Susceptible"
    if not dcr or dcr <= 0: return "N/A"
    if temp > 110: return "Not Susceptible"
    return _level((acr if acr else 1.5) / dcr)

def _batch_hcl(fluid, mat, dcr, ph, temp, acr=None):
    if not _has_chem(fluid, ["HCL","HYDROCHLORIC","CHLORIDE","HCI"]): return "N/A"
    if not dcr or dcr <= 0: return "N/A"
    ph = float(ph) if ph else 7.0
    if ph > 6.8: return "Not Susceptible"
    if acr: return _level(acr / dcr)
    tbl = HCL_SS300_TABLE if "300 series SS" in mat else HCL_CS_TABLE
    return _level(_lookup_hcl(tbl, ph, _hcl_temp_idx(temp)) / dcr)

def _batch_htha(fluid, temp, mat):
    if not _has_chem(fluid, ["H2","HYDROGEN","HYDROG","REFORM"]): return "N/A"
    if not isinstance(temp,(int,float)) or temp <= 177: return "Not Susceptible"
    if any(m in mat for m in ["300 series SS","400 series SS"]): return "Not Susceptible"
    key = "1Cr-0.5Mo" if "Low Alloy" in mat else "Carbon Steel"
    curve_t = _interp(NELSON_CURVES.get(key, NELSON_CURVES["Carbon Steel"]), 50)
    m = curve_t - temp
    return "High" if m <= 0 else "Medium" if m < 15 else "Low" if m <= 30 else "Negligible"

def _batch_sulfidation(temp, ph, mat, dcr, acr=None):
    if not isinstance(temp,(int,float)) or temp <= 260: return "Not Susceptible"
    ph = float(ph) if ph else 7.0
    if not (4.5 <= ph <= 7.0): return "Not Susceptible"
    if not dcr or dcr <= 0: return "N/A"
    if acr: return _level(acr / dcr)
    pts = MCCONOMY_CURVES.get(_mcconomy_key(mat))
    return _level(_interp(pts, temp) / dcr) if pts else "N/A"

def _batch_thermal(equip_type, cycling):
    eq = str(equip_type or "").lower()
    if not any(t in eq for t in ["furnace","fired heater","coil","reformer","waste heat boiler","heater","fired"]):
        return "Not Susceptible"
    return "Low" if str(cycling or "").lower() in ["yes","y","1","true"] else "Negligible"

def _batch_hf(fluid, mat, dcr, acr=None):
    if not _has_chem(fluid, ["HF","HYDROFLUORIC","FLUORIDE","ALKYLAT"]): return "N/A"
    if any(m in mat for m in ["300 series SS","400 series SS"]): return "Not Susceptible"
    if not dcr or dcr <= 0: return "N/A"
    return _level((acr if acr else 0.5) / dcr)


# ─── Pydantic Input Model ─────────────────────────────────────────────────────
class H2SInput(BaseModel):
    has_h2s:   str
    temp:      float
    material:  str
    h2s_mole:  float
    hc_type:   str
    design_cr: float
    actual_cr: Optional[float] = None


# ─── Corrosion Analysis Logic ─────────────────────────────────────────────────
def calculate_h2s_susceptibility(
    has_h2s: str, temp: float, material: str,
    h2s_mole: float, hc_type: str, design_cr: float,
    actual_cr: Optional[float] = None,
) -> dict:
    steps = []

    def step(n, label, detail, passed):
        steps.append({"step": n, "label": label, "detail": detail, "pass": passed})

    if has_h2s.upper() != "YES":
        step(1, "H2S Availability", "No H2S detected in stream", False)
        return {"susceptibility": "Not Susceptible", "reason": "No H2S in stream", "steps": steps}
    step(1, "H2S Availability", "H2S is present in stream", True)

    if temp <= 230:
        step(2, "Temperature Check", f"{temp}°C ≤ 230°C — below corrosion threshold", False)
        return {"susceptibility": "Not Susceptible", "reason": f"Temperature {temp}°C ≤ 230°C", "steps": steps}
    step(2, "Temperature Check", f"{temp}°C > 230°C — within corrosion range", True)

    is_susceptible = any(m in material for m in SUSCEPTIBLE_MATERIALS)
    if not is_susceptible:
        step(3, "Material Check", f"{material} is not in H2S susceptible material list", False)
        return {"susceptibility": "Not Susceptible", "reason": f"{material} not susceptible", "steps": steps}
    step(3, "Material Check", f"{material} is susceptible to H2S corrosion", True)

    if actual_cr is not None:
        final_cr = actual_cr
        step(4, "Corrosion Rate Source", f"Using measured Actual CR = {actual_cr} mm/y", True)
    else:
        selected_rates = None
        for (low, high), types in H2S_CORROSION_DATA.items():
            if low <= h2s_mole <= high:
                selected_rates = types.get(hc_type)
                break
        if selected_rates is None:
            step(4, "Corrosion Rate (Table Lookup)", "H2S mole% out of table range (0.0–1.0)", False)
            return {"susceptibility": "Error", "reason": "H2S content out of table range (0–1.0 mol%)", "steps": steps}
        col_idx = bisect.bisect_left(TEMP_COLUMNS, temp)
        final_cr = selected_rates[col_idx]
        step(4, "Corrosion Rate (Table Lookup)", f"H2S {h2s_mole} mol% | {hc_type} | {temp}°C → CR = {final_cr} mm/y", True)

    ratio = round(final_cr / design_cr, 4)
    level = "High" if ratio > 4 else "Medium" if ratio >= 1 else "Low" if ratio >= 0.5 else "Negligible"
    step(5, "Susceptibility Assessment", f"Ratio = {final_cr} / {design_cr} = {ratio}  →  {level}", True)

    return {"susceptibility": level, "corrosion_rate": final_cr, "design_cr": design_cr, "ratio": ratio, "steps": steps}


# ─── Protected Routes (ทุก route ใช้ Depends(require_auth)) ──────────────────

ADMIN_ID = "26009623"


# ── Manual Login ──────────────────────────────────────────────────────────────
class ManualLoginInput(BaseModel):
    username: str
    password: str


@app.post("/login/manual")
async def manual_login(request: Request, data: ManualLoginInput):
    user = verify_user(data.username, data.password)
    if not user:
        return JSONResponse(
            status_code=401,
            content={"error": "Username หรือ Password ไม่ถูกต้อง หรือบัญชีถูกปิดใช้งาน"},
        )
    save_auth(request, f"manual-{user['id']}", user["id"])
    update_last_login(user["id"])
    return JSONResponse(content={"success": True})


# ── User CRUD API (admin only) ────────────────────────────────────────────────
class UserCreateInput(BaseModel):
    id: str
    name: str
    email: str
    role: str
    status: str = "Active"
    password: str = ""
    created_by: str = ADMIN_ID


class UserUpdateInput(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None


def _require_admin(current_user: str) -> bool:
    return current_user == ADMIN_ID


@app.get("/api/users")
async def api_get_users(current_user: str = Depends(require_auth)):
    if not _require_admin(current_user):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return JSONResponse(content=[public_view(u) for u in get_all_users()])


@app.post("/api/users")
async def api_create_user(data: UserCreateInput, current_user: str = Depends(require_auth)):
    if not _require_admin(current_user):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    try:
        user = create_user(data.model_dump())
        return JSONResponse(content=public_view(user))
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.put("/api/users/{user_id}")
async def api_update_user(user_id: str, data: UserUpdateInput, current_user: str = Depends(require_auth)):
    if not _require_admin(current_user):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    updated = update_user(user_id, data.model_dump(exclude_none=True))
    if not updated:
        return JSONResponse(status_code=404, content={"error": "ไม่พบผู้ใช้นี้ในระบบ"})
    return JSONResponse(content=public_view(updated))


@app.delete("/api/users/{user_id}")
async def api_delete_user(user_id: str, current_user: str = Depends(require_auth)):
    if not _require_admin(current_user):
        return JSONResponse(status_code=403, content={"error": "Forbidden"})
    if user_id == ADMIN_ID:
        return JSONResponse(status_code=400, content={"error": "ไม่สามารถลบบัญชี Admin หลักได้"})
    if not delete_user(user_id):
        return JSONResponse(status_code=404, content={"error": "ไม่พบผู้ใช้นี้ในระบบ"})
    return JSONResponse(content={"success": True})


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("index.html", {"request": request, "current_user": current_user})


@app.get("/admin/users", response_class=HTMLResponse)
async def admin_user_manage(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse(
        "admin_UserManage.html", {"request": request, "current_user": current_user}
    )


@app.post("/upload", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...), current_user: str = Depends(require_auth)):
    contents = await file.read()
    df = pd.read_excel(io.BytesIO(contents), skiprows=7)
    df = df.fillna("-")
    headers = df.columns.tolist()
    data_list = df.to_dict(orient="records")
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "current_user": current_user, "headers": headers, "data": data_list, "total": len(data_list)},
    )


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Page1.html", {"request": request, "current_user": current_user})


@app.get("/h2s", response_class=HTMLResponse)
async def h2s_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/H2S_Analysis.html", {"request": request, "current_user": current_user})


@app.get("/flue_gas_dewpoint", response_class=HTMLResponse)
async def flue_gas_dewpoint_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/Flue_gas_dewpoint.html", {"request": request, "current_user": current_user})


@app.get("/hcl_corrosion", response_class=HTMLResponse)
async def hcl_corrosion_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/Hydrochloric_Acid_Corrosion\u200b.html", {"request": request, "current_user": current_user})


@app.get("/htha", response_class=HTMLResponse)
async def htha_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/High temperature hydrogen attack.html", {"request": request, "current_user": current_user})


@app.get("/sulfidation", response_class=HTMLResponse)
async def sulfidation_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/Sulfidation.html", {"request": request, "current_user": current_user})


@app.get("/thermal_shock", response_class=HTMLResponse)
async def thermal_shock_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/Thermal shock.html", {"request": request, "current_user": current_user})


@app.get("/hf_corrosion", response_class=HTMLResponse)
async def hf_corrosion_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Example_Test_Damage/Hydrofluoric_Acid_Corrosion.html", {"request": request, "current_user": current_user})


@app.get("/customer_company", response_class=HTMLResponse)
async def customer_company_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Customer_Company.html", {"request": request, "current_user": current_user})


@app.get("/plant_customer", response_class=HTMLResponse)
async def plant_customer_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("plant_customer.html", {"request": request, "current_user": current_user})


@app.get("/unit_customer", response_class=HTMLResponse)
async def unit_customer_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Unit_costumer.html", {"request": request, "current_user": current_user})


@app.get("/add_tag_from_unit", response_class=HTMLResponse)
async def add_tag_from_unit_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("add_Tag_From_Unit.html", {"request": request, "current_user": current_user})


@app.post("/h2s/calculate")
async def h2s_calculate(data: H2SInput):
    result = calculate_h2s_susceptibility(
        has_h2s=data.has_h2s, temp=data.temp, material=data.material,
        h2s_mole=data.h2s_mole, hc_type=data.hc_type, design_cr=data.design_cr,
        actual_cr=data.actual_cr,
    )
    return JSONResponse(content=result)


# ─── Excel Batch Analysis Endpoint ───────────────────────────────────────────
@app.post("/api/analyze_excel")
async def api_analyze_excel(
    file: UploadFile = File(...),
    current_user: str = Depends(require_auth),
):
    import openpyxl
    raw = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": str(e)})

    if "Mech. Raw data" not in wb.sheetnames:
        return JSONResponse(status_code=400, content={"error": "ไม่พบ Sheet 'Mech. Raw data' ในไฟล์ Excel"})

    ws = wb["Mech. Raw data"]
    results = []
    skip_tags = {"", "tag", "tag2", "no.", "-", "none"}

    for row in ws.iter_rows(min_row=9, values_only=True):
        tag = row[9]                          # col 10
        if tag is None or str(tag).strip().lower() in skip_tags:
            continue

        fluid    = str(row[17] or "")         # col 18
        mat_type = str(row[20] or "")         # col 21
        material = str(row[21] or "")         # col 22
        grade    = row[22]                    # col 23
        op_temp  = _safe_float(row[36])       # col 37
        cycling  = row[52]                    # col 53
        ca       = _safe_float(row[94])       # col 95
        life     = _safe_float(row[95])       # col 96
        acr_raw  = _safe_float(row[152])      # col 153 Actual CR
        dcr_raw  = row[154]                   # col 155 Design CR
        ph_raw   = _safe_float(row[156])      # col 157
        equip_t  = str(row[15] or "")         # col 16

        mat = _std_material(mat_type, material, grade)
        dcr = _get_design_cr(dcr_raw, ca, life)
        acr = acr_raw if (acr_raw and acr_raw > 0) else None
        ph  = ph_raw if ph_raw is not None else 7.0

        hcl_missing  = not _has_chem(fluid, ["HCL","HYDROCHLORIC","CHLORIDE","HCI"])
        htha_missing = not _has_chem(fluid, ["H2","HYDROGEN","HYDROG","REFORM"])
        hf_missing   = not _has_chem(fluid, ["HF","HYDROFLUORIC","FLUORIDE","ALKYLAT"])
        dcr_missing  = dcr is None
        temp_missing = op_temp is None

        results.append({
            "tag":          str(tag),
            "component":    str(row[13] or ""),   # col 14
            "loop_no":      str(row[2] or ""),
            "loop_name":    str(row[3] or ""),
            "plant_unit":   str(row[1] or ""),
            "material":     mat,
            "op_temp":      op_temp,
            "ph":           ph,
            "design_cr":    round(dcr, 4) if dcr is not None else None,
            "H2S":          _batch_h2s(op_temp, mat, dcr, acr),
            "FlueGas":      _batch_flue(mat, dcr, op_temp, acr),
            "HCl":          _batch_hcl(fluid, mat, dcr, ph, op_temp, acr),
            "HTHA":         _batch_htha(fluid, op_temp, mat),
            "Sulfidation":  _batch_sulfidation(op_temp, ph, mat, dcr, acr),
            "ThermalShock": _batch_thermal(equip_t, cycling),
            "HF":           _batch_hf(fluid, mat, dcr, acr),
            "HCl_missing":  hcl_missing,
            "HTHA_missing": htha_missing,
            "HF_missing":   hf_missing,
            "dcr_missing":  dcr_missing,
            "temp_missing": temp_missing,
        })

    return JSONResponse(content=results)


class RecalcInput(BaseModel):
    tag:               str
    component:         str
    material:          str
    op_temp:           Optional[float] = None
    op_temp_override:  Optional[float] = None
    ph:                Optional[float] = 7.0
    design_cr:         Optional[float] = None
    design_cr_override: Optional[float] = None
    acr:               Optional[float] = None
    equip_type:        str = ""
    cycling:           str = "No"
    hcl_present: str = "NO"
    h2_present:  str = "NO"
    h2_pp:       Optional[float] = 50.0
    hf_present:  str = "NO"


@app.post("/api/recalculate_row")
async def api_recalculate_row(data: RecalcInput, current_user: str = Depends(require_auth)):
    mat  = data.material
    temp = data.op_temp_override  if data.op_temp_override  is not None else data.op_temp
    dcr  = data.design_cr_override if data.design_cr_override is not None else data.design_cr
    ph   = data.ph or 7.0
    acr  = data.acr

    # ── Recalculate all 7 mechanisms ─────────────────────────────────
    h2s_result   = _batch_h2s(temp, mat, dcr, acr)
    flue_result  = _batch_flue(mat, dcr, temp, acr)
    sulf_result  = _batch_sulfidation(temp, ph, mat, dcr, acr)
    therm_result = _batch_thermal(data.equip_type, data.cycling)

    hcl_val = data.hcl_present.upper()
    if hcl_val == "SKIP":
        hcl_result, hcl_missing = "N/A", True
    elif hcl_val == "YES":
        hcl_result  = _batch_hcl("HCL", mat, dcr, ph, temp, acr)
        hcl_missing = False
    else:  # NO → confirmed not present
        hcl_result, hcl_missing = "Not Susceptible", False

    h2_val = data.h2_present.upper()
    if h2_val == "SKIP":
        htha_result, htha_missing = "N/A", True
    elif h2_val == "YES":
        h2pp = data.h2_pp or 50.0
        if not isinstance(temp, (int, float)) or temp <= 177:
            htha_result = "Not Susceptible"
        elif any(m in mat for m in ["300 series SS", "400 series SS"]):
            htha_result = "Not Susceptible"
        else:
            key     = "1Cr-0.5Mo" if "Low Alloy" in mat else "Carbon Steel"
            curve_t = _interp(NELSON_CURVES.get(key, NELSON_CURVES["Carbon Steel"]), h2pp)
            margin  = curve_t - temp
            htha_result = "High" if margin <= 0 else "Medium" if margin < 15 else "Low" if margin <= 30 else "Negligible"
        htha_missing = False
    else:  # NO → confirmed not present
        htha_result, htha_missing = "Not Susceptible", False

    hf_val = data.hf_present.upper()
    if hf_val == "SKIP":
        hf_result, hf_missing = "N/A", True
    elif hf_val == "YES":
        hf_result  = _batch_hf("HF", mat, dcr, acr)
        hf_missing = False
    else:  # NO → confirmed not present
        hf_result, hf_missing = "Not Susceptible", False

    return JSONResponse(content={
        "tag": data.tag, "component": data.component,
        "H2S":         h2s_result,
        "FlueGas":     flue_result,
        "HCl":         hcl_result,  "HCl_missing":  hcl_missing,
        "HTHA":        htha_result, "HTHA_missing": htha_missing,
        "Sulfidation": sulf_result,
        "ThermalShock":therm_result,
        "HF":          hf_result,   "HF_missing":   hf_missing,
        "dcr_missing":  dcr is None or dcr <= 0,
        "temp_missing": temp is None,
    })


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8005)
