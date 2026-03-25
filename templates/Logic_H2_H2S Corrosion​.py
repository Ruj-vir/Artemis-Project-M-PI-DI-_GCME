import bisect

# --- ฐานข้อมูลตาราง (TABLE DATA) ---
# นิยามช่วงอุณหภูมิที่เป็นหัวตาราง (Upper Bounds สำหรับแต่ละคอลัมน์)
TEMP_COLUMNS = [245, 273, 301, 328, 356, 384, 412, 440, 467, 495, 523, float('inf')]

# ข้อมูลตาราง H2S (mole %) และ Hydrocarbon Type ตามที่คุณให้มา
# โครงสร้าง: { (Min_H2S, Max_H2S): { "Type": [ค่า CR ตามช่วงอุณหภูมิ 12 ช่วง] } }
H2S_CORROSION_DATA = {
    (0.0, 0.002): {
        "Naphtha": [0.03, 0.03, 0.03, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.25, 0.36, 0.46],
        "Gas Oil": [0.03, 0.03, 0.03, 0.05, 0.08, 0.13, 0.18, 0.25, 0.36, 0.51, 0.66, 0.86]
    },
    (0.0021, 0.0035): {
        "Naphtha": [0.03, 0.03, 0.03, 0.05, 0.1, 0.15, 0.2, 0.3, 0.41, 0.56, 0.74, 0.94],
        "Gas Oil": [0.03, 0.05, 0.08, 0.1, 0.18, 0.28, 0.41, 0.56, 0.79, 1.04, 1.4, 1.8]
    },
    (0.0036, 0.008): {
        "Naphtha": [0.03, 0.03, 0.05, 0.08, 0.13, 0.18, 0.28, 0.38, 0.53, 0.74, 0.97, 1.27],
        "Gas Oil": [0.03, 0.05, 0.1, 0.15, 0.23, 0.36, 0.53, 0.74, 1.04, 1.4, 1.85, 2.39]
    },
    (0.0081, 0.035): {
        "Naphtha": [0.03, 0.05, 0.08, 0.13, 0.23, 0.33, 0.48, 0.69, 0.97, 1.3, 1.7, 2.21],
        "Gas Oil": [0.05, 0.1, 0.15, 0.25, 0.41, 0.64, 0.91, 1.3, 1.8, 2.44, 3.3, 4.32]
    },
    (0.0351, 0.08): {
        "Naphtha": [0.03, 0.05, 0.1, 0.18, 0.25, 0.41, 0.58, 0.84, 1.17, 1.57, 2.08, 2.79],
        "Gas Oil": [0.05, 0.1, 0.2, 0.33, 0.51, 0.76, 1.12, 1.6, 2.21, 3.05, 4.06, 5.08]
    },
    (0.081, 0.3): {
        "Naphtha": [0.05, 0.08, 0.15, 0.25, 0.38, 0.58, 0.86, 1.22, 1.68, 2.29, 3.05, 3.81],
        "Gas Oil": [0.08, 0.15, 0.28, 0.46, 0.74, 1.12, 1.63, 2.31, 3.3, 4.32, 5.84, 7.62]
    },
    (0.301, 0.75): {
        "Naphtha": [0.05, 0.1, 0.18, 0.28, 0.43, 0.66, 0.97, 1.37, 1.91, 2.54, 3.3, 4.32],
        "Gas Oil": [0.1, 0.18, 0.3, 0.53, 0.81, 1.24, 1.83, 2.54, 3.56, 4.83, 6.35, 8.38]
    },
    (0.751, 1.0): {
        "Naphtha": [0.08, 0.13, 0.2, 0.33, 0.53, 0.81, 1.19, 1.7, 2.36, 3.3, 4.32, 5.59],
        "Gas Oil": [0.13, 0.23, 0.38, 0.66, 1.02, 1.55, 2.26, 3.3, 4.57, 6.1, 7.87, 10.41]
    }
}

def calculate_h2s_susceptibility(has_h2s, temp, material, h2s_mole, hc_type, design_cr, actual_cr=None):
    """
    Main Logic Function: รวมทุก Step ตาม Flowchart
    """
    print(f"\n--- เริ่มการวิเคราะห์ Corrosion Loop: {material} ---")

    # STEP 1: H2S Availability
    if has_h2s.upper() != "YES":
        return "Not Susceptible (No H2S)"

    # STEP 2: Temperature > 230°C
    if temp <= 230:
        return f"Not Susceptible (Temp {temp}°C <= 230°C)"

    # STEP 3: Material Check
    susceptible_materials = ["Carbon Steel", "Low Alloy", "300 series SS", "400 series SS"]
    # เช็คว่า material ที่ส่งมามีคำหลักเหล่านี้อยู่หรือไม่
    is_valid_material = any(m in material for m in susceptible_materials)
    
    if not is_valid_material:
        return f"Not Susceptible (Material {material} not in scope)"

    # STEP 4: Determine Corrosion Rate (CR)
    final_cr = 0.0
    if actual_cr is not None:
        print(f"[*] ใช้ค่า Actual Corrosion Rate: {actual_cr} mm/y")
        final_cr = actual_cr
    else:
        print(f"[*] ค้นหาค่าจากตาราง (H2S: {h2s_mole} mole%, Type: {hc_type}, Temp: {temp}°C)")
        
        # ค้นหาช่วง H2S
        selected_rates = None
        for (low, high), types in H2S_CORROSION_DATA.items():
            if low <= h2s_mole <= high:
                selected_rates = types.get(hc_type)
                break
        
        if not selected_rates:
            return "Error: H2S content out of table range"

        # ค้นหา Column อุณหภูมิ
        col_idx = bisect.bisect_left(TEMP_COLUMNS, temp)
        final_cr = selected_rates[col_idx]
        print(f"[*] ค่า Estimated CR จากตาราง: {final_cr} mm/y")

    # STEP 5: Calculate Ratio & Susceptibility
    ratio = final_cr / design_cr
    
    if ratio > 4:
        level = "High"
    elif 1 <= ratio <= 4:
        level = "Medium"
    elif 0.5 <= ratio < 1:
        level = "Low"
    else:
        level = "Negligible"

    # --- สรุปผล ---
    result = {
        "Corrosion Rate": final_cr,
        "Ratio": round(ratio, 2),
        "Susceptibility": level
    }
    return result

# --- ตัวอย่างการเรียกใช้งาน (Example Usage) ---
if __name__ == "__main__":
    # ใส่ข้อมูลที่ต้องการทดสอบตรงนี้
    my_result = calculate_h2s_susceptibility(
        has_h2s="YES",
        temp=350,
        material="Carbon Steel",
        h2s_mole=0.05,
        hc_type="Gas Oil",
        design_cr=1.0,
        actual_cr=None  # ถ้ามีค่าจริงให้ใส่ตัวเลข เช่น 2.5 ถ้าไม่มีให้ใส่ None
    )

    print("\n[ สรุปผลการวิเคราะห์ ]")
    print(my_result)