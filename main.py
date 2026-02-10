from fastapi import FastAPI, Request, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import io
import uvicorn

app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/upload", response_class=HTMLResponse)
async def handle_upload(request: Request, file: UploadFile = File(...)):
    contents = await file.read()
    # อ่านไฟล์เริ่มจาก Row 8
    df = pd.read_excel(io.BytesIO(contents), skiprows=7)
    df = df.fillna("-")
    
    # ดึงรายชื่อ Header ออกมาเป็น List
    headers = df.columns.tolist() 
    # แปลงข้อมูลเป็น List of Dict
    data_list = df.to_dict(orient='records')

    return templates.TemplateResponse("index.html", {
        "request": request,
        "headers": headers,  # ส่งรายชื่อ Header ไปที่ HTML
        "data": data_list,   # ส่งข้อมูลทั้งหมดไปที่ HTML
        "total": len(data_list)
    })
 

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)