import bisect
import io

import pandas as pd
import uvicorn
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from typing import Optional

# ─── SSO Imports (4 ไฟล์หลัก) ────────────────────────────────────────────────
from auth_service import SESSION_SECRET, redirect_to_sso
from auth_guard import require_auth, NotAuthenticatedException
from auth_routes import router as auth_router
from auth_interceptor import AuthInterceptor

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# ─── Middleware ───────────────────────────────────────────────────────────────
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(AuthInterceptor)

# ─── SSO Routes (/home callback + /logout) ───────────────────────────────────
app.include_router(auth_router)

# ─── Exception Handler: redirect ไป SSO ถ้าไม่ได้ login ─────────────────────
@app.exception_handler(NotAuthenticatedException)
async def not_authenticated(request: Request, exc: NotAuthenticatedException):
    return redirect_to_sso()


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
@app.get("/", response_class=HTMLResponse)
async def home(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("index.html", {"request": request, "current_user": current_user})


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
    return templates.TemplateResponse("H2S_Analysis.html", {"request": request, "current_user": current_user})


@app.get("/flue_gas_dewpoint", response_class=HTMLResponse)
async def flue_gas_dewpoint_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Flue_gas_dewpoint.html", {"request": request, "current_user": current_user})


@app.get("/hcl_corrosion", response_class=HTMLResponse)
async def hcl_corrosion_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Hydrochloric_Acid_Corrosion\u200b.html", {"request": request, "current_user": current_user})


@app.get("/htha", response_class=HTMLResponse)
async def htha_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("High temperature hydrogen attack.html", {"request": request, "current_user": current_user})


@app.get("/sulfidation", response_class=HTMLResponse)
async def sulfidation_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Sulfidation.html", {"request": request, "current_user": current_user})


@app.get("/thermal_shock", response_class=HTMLResponse)
async def thermal_shock_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Thermal shock.html", {"request": request, "current_user": current_user})


@app.get("/hf_corrosion", response_class=HTMLResponse)
async def hf_corrosion_page(request: Request, current_user: str = Depends(require_auth)):
    return templates.TemplateResponse("Hydrofluoric_Acid_Corrosion.html", {"request": request, "current_user": current_user})


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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
