"""
user_store.py — จัดการ user data ใน users.json
รองรับ: load / save / verify password / CRUD
"""
import hashlib
import json
import os
from datetime import datetime
from typing import Optional

USERS_FILE = os.path.join(os.path.dirname(__file__), "users.json")
_SALT = "artemis-pttgc-2026"


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_SALT}{password}".encode()).hexdigest()


def verify_password(password: str, pw_hash: str) -> bool:
    return hash_password(password) == pw_hash


# ─── File I/O ─────────────────────────────────────────────────────────────────

def load_users() -> list:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_users(users: list) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def public_view(user: dict) -> dict:
    """คืน user dict โดยไม่มี password_hash"""
    return {k: v for k, v in user.items() if k != "password_hash"}


# ─── Init default users (ถ้าไฟล์ยังไม่มี) ────────────────────────────────────

def init_users_if_empty() -> None:
    if os.path.exists(USERS_FILE):
        return
    today = datetime.now().strftime("%d/%m/%Y")
    defaults = [
        {"id": "26009623", "name": "Admin User",    "email": "26009623@PTTGCGroup.com", "role": "Admin",  "status": "Active"},
        {"id": "26009624", "name": "Suphawit T.",   "email": "26009624@PTTGCGroup.com", "role": "User",   "status": "Active"},
        {"id": "26009625", "name": "Nattaporn K.",  "email": "26009625@PTTGCGroup.com", "role": "User",   "status": "Active"},
        {"id": "26009626", "name": "Patchara M.",   "email": "26009626@PTTGCGroup.com", "role": "Viewer", "status": "Active"},
        {"id": "26009627", "name": "Ratchanee W.",  "email": "26009627@PTTGCGroup.com", "role": "User",   "status": "Inactive"},
        {"id": "26009630", "name": "Kraiwit S.",    "email": "26009630@PTTGCGroup.com", "role": "User",   "status": "Active"},
        {"id": "26009649", "name": "Thanakorn L.",  "email": "26009649@PTTGCGroup.com", "role": "Admin",  "status": "Active"},
    ]
    users = []
    for d in defaults:
        users.append({
            **d,
            "password_hash": hash_password(d["id"]),  # default password = employee ID
            "last_login": "-",
            "created_by": "System",
        })
    save_users(users)


# ─── Auth ──────────────────────────────────────────────────────────────────────

def verify_user(username: str, password: str) -> Optional[dict]:
    """คืน user dict ถ้า login สำเร็จ, None ถ้าไม่ผ่าน"""
    for u in load_users():
        match_id    = u["id"] == username
        match_email = u["email"].lower() == username.lower()
        if (match_id or match_email) and verify_password(password, u.get("password_hash", "")):
            if u["status"] != "Active":
                return None  # บัญชีถูกปิด
            return u
    return None


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def get_all_users() -> list:
    return load_users()


def get_user(user_id: str) -> Optional[dict]:
    return next((u for u in load_users() if u["id"] == user_id), None)


def create_user(data: dict) -> dict:
    users = load_users()
    if any(u["id"] == data["id"] for u in users):
        raise ValueError(f"Employee ID '{data['id']}' มีอยู่แล้วในระบบ")
    today = datetime.now().strftime("%d/%m/%Y")
    password = data.pop("password", data["id"])  # ถ้าไม่ระบุ default = employee ID
    new_user = {
        "id":            data["id"],
        "name":          data["name"],
        "email":         data["email"],
        "role":          data.get("role", "User"),
        "status":        data.get("status", "Active"),
        "password_hash": hash_password(password),
        "last_login":    "-",
        "created_by":    data.get("created_by", "Admin"),
    }
    users.insert(0, new_user)
    save_users(users)
    return new_user


def update_user(user_id: str, data: dict) -> Optional[dict]:
    users = load_users()
    for i, u in enumerate(users):
        if u["id"] == user_id:
            if "password" in data and data["password"]:
                data["password_hash"] = hash_password(data.pop("password"))
            else:
                data.pop("password", None)
            users[i] = {**u, **data}
            save_users(users)
            return users[i]
    return None


def update_last_login(user_id: str) -> None:
    users = load_users()
    today = datetime.now().strftime("%d/%m/%Y")
    for u in users:
        if u["id"] == user_id:
            u["last_login"] = today
            break
    save_users(users)


def delete_user(user_id: str) -> bool:
    users = load_users()
    new_users = [u for u in users if u["id"] != user_id]
    if len(new_users) == len(users):
        return False
    save_users(new_users)
    return True
