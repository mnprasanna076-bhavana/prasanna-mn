import os
import json
import re
import base64
import shutil
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from io import BytesIO
from contextlib import asynccontextmanager

from fastapi import (
    FastAPI, HTTPException, Depends, File, UploadFile,
    Form, Request, status, Cookie
)
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
import bcrypt
from jose import JWTError, jwt
from dotenv import load_dotenv
import asyncio
import uuid

from models import (
    RegisterUser, UserLogin, UserInDB, Token, TokenData,
    UserSession, HomeBudgetInput, PartyBudgetInput,
    JewelryBudgetInput, RecommendationHistoryItem
)
import database
from gemini_utils import (
    get_home_recommendations,
    get_party_recommendations,
    get_jewelry_recommendations,
    extract_json_from_response,
    usd_to_inr
)

# Load environment
load_dotenv()

# Security and Session Settings
SECRET_KEY = os.getenv("SECRET_KEY", "pocketsmart_super_secure_jwt_secret_key_2026_x89a!")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# In-memory stores
active_sessions: Dict[str, UserSession] = {}
blacklisted_tokens = set()

# Password hashing utilities
def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def ensure_demo_user():
    try:
        demo_user = database.get_user_by_username("sai")
        if not demo_user:
            database.save_user(
                id=str(uuid.uuid4()),
                username="sai",
                email="sai@pocketsmart.ai",
                full_name="Sai Kumar",
                hashed_password=get_password_hash("password123")
            )
            print("Default demo user 'sai' initialized.")
    except Exception as e:
        print(f"Demo user notice: {e}")

ensure_demo_user()

# Lifespan background task management
@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_demo_user()
    cleanup_task = asyncio.create_task(cleanup_expired_sessions_loop())
    yield
    cleanup_task.cancel()

async def cleanup_expired_sessions_loop():
    """Background task to clean up inactive sessions"""
    while True:
        try:
            current_time = datetime.utcnow()
            expired = [
                uname for uname, sess in list(active_sessions.items())
                if (current_time - sess.last_activity).total_seconds() > (ACCESS_TOKEN_EXPIRE_MINUTES * 60)
            ]
            for uname in expired:
                if uname in active_sessions:
                    del active_sessions[uname]
        except Exception:
            pass
        await asyncio.sleep(300)

# App initialization
app = FastAPI(title="PocketSmart: AI Budget Planner", version="1.0.0", lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static and Templates
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("static/images", exist_ok=True)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# ==================== AUTH UTILITIES ====================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def extract_token_from_request(request: Request) -> Optional[str]:
    """Retrieve token from either Authorization header or Cookie safely"""
    # 1. Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        if auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return auth_header.strip()

    # 2. Cookie 'access_token'
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        if cookie_token.startswith("Bearer "):
            return cookie_token[7:].strip()
        return cookie_token.strip()
    return None

async def get_token(request: Request, token_header: Optional[str] = Depends(oauth2_scheme)) -> Optional[str]:
    """Retrieve token from either Authorization header or Cookie"""
    if token_header and isinstance(token_header, str):
        return token_header.strip()
    return extract_token_from_request(request)

async def get_current_user(request: Request, token: Optional[str] = Depends(get_token)) -> UserInDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token or not isinstance(token, str):
        token = extract_token_from_request(request)

    if not token or token in blacklisted_tokens:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception

    user_dict = database.get_user_by_username(username)
    if user_dict is None:
        raise credentials_exception

    return UserInDB(**user_dict)

async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

async def get_current_user_optional(request: Request) -> Optional[UserInDB]:
    """Returns the current user if logged in, or None if guest"""
    try:
        return await get_current_user(request)
    except Exception:
        return None

def save_upload_file(upload_file: UploadFile) -> str:
    """Save uploaded image file to static/uploads/ with unique filename"""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    clean_filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", upload_file.filename or "upload.jpg")
    saved_filename = f"{timestamp}_{clean_filename}"
    file_path = os.path.join("static", "uploads", saved_filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return file_path

# ==================== PAGE ROUTES ====================

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Serve the landing / index page"""
    current_user = await get_current_user_optional(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"user": current_user}
    )

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page"""
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={}
    )

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page"""
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={}
    )

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """User Dashboard page"""
    current_user = await get_current_user_optional(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    recent_history = database.get_user_recommendations(current_user.username)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "user": current_user,
            "recent_activity": recent_history[:5]
        }
    )

@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request):
    """Home budget planner page"""
    current_user = await get_current_user_optional(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="home_planner.html",
        context={"user": current_user}
    )

@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request):
    """Party budget planner page"""
    current_user = await get_current_user_optional(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="party_planner.html",
        context={"user": current_user}
    )

@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request):
    """Jewelry budget planner page"""
    current_user = await get_current_user_optional(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request=request,
        name="jewelry_planner.html",
        context={"user": current_user}
    )

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    """History page to view past recommendations"""
    current_user = await get_current_user_optional(request)
    if not current_user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    user_history = database.get_user_recommendations(current_user.username)
    return templates.TemplateResponse(
        request=request,
        name="history.html",
        context={"user": current_user, "history": user_history}
    )

# ==================== AUTHENTICATION API ROUTES ====================

@app.post("/register")
async def register(user_data: RegisterUser):
    """Handles new user registration"""
    if database.get_user_by_username(user_data.username):
        raise HTTPException(status_code=400, detail="Username already registered")
    if database.get_user_by_email(user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_id = str(uuid.uuid4())
    hashed_pwd = get_password_hash(user_data.password)
    database.save_user(
        id=user_id,
        username=user_data.username,
        email=user_data.email,
        full_name=user_data.full_name or user_data.username,
        hashed_password=hashed_pwd
    )

    access_token = create_access_token(data={"sub": user_data.username})
    response = JSONResponse(content={
        "message": "User registered successfully",
        "access_token": access_token,
        "token_type": "bearer",
        "username": user_data.username
    })
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax"
    )
    return response

@app.post("/login")
async def login(credentials: UserLogin):
    """Authenticates user credentials and initiates a session"""
    user_dict = database.get_user_by_username(credentials.username)
    if not user_dict or not verify_password(credentials.password, user_dict["hashed_password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token = create_access_token(data={"sub": credentials.username})
    
    active_sessions[credentials.username] = UserSession(
        username=credentials.username,
        login_time=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        token=access_token,
        user_data={}
    )

    response = JSONResponse(content={
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "username": credentials.username
    })
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax"
    )
    return response

@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint for OAuth2 form access token"""
    user_dict = database.get_user_by_username(form_data.username)
    if not user_dict or not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": form_data.username})

    existing_user_data = {}
    if form_data.username in active_sessions:
        existing_user_data = active_sessions[form_data.username].user_data
        old_token = active_sessions[form_data.username].token
        blacklisted_tokens.add(old_token)

    active_sessions[form_data.username] = UserSession(
        username=form_data.username,
        login_time=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        token=access_token,
        user_data=existing_user_data
    )

    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        samesite="lax"
    )
    return response

@app.get("/logout")
@app.post("/logout")
async def logout(request: Request):
    """Logout user by blacklisting their token and clearing session"""
    token = extract_token_from_request(request)
    if token:
        blacklisted_tokens.add(token)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username and username in active_sessions:
                del active_sessions[username]
        except Exception:
            pass

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token", path="/")
    return response

# ==================== SESSION INFO API ====================

@app.get("/session-info")
async def get_session_info(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get current user's session information"""
    if current_user.username in active_sessions:
        session = active_sessions[current_user.username]
        duration_mins = int((datetime.utcnow() - session.login_time).total_seconds() // 60)
        return {
            "username": session.username,
            "login_time": session.login_time.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "session_duration": duration_mins,
            "user_data": session.user_data
        }
    return {
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_active": current_user.is_active,
        "session_duration": 0,
        "user_data": {}
    }

@app.post("/session-data")
async def update_session_data(
    data: Dict[str, Any],
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Update user's session data"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data.update(data)
        active_sessions[current_user.username].last_activity = datetime.utcnow()
        return {
            "message": "Session data updated",
            "data": active_sessions[current_user.username].user_data
        }
    return {"message": "Session stored locally", "data": data}

# ==================== RECOMMENDATION PLANNING ENDPOINTS ====================

@app.post("/home-budget")
@app.post("/generate-home")
async def plan_home_budget(
    budget_input: HomeBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate home budget recommendations and persist to history"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_home_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "requirements": {
                "lights": budget_input.num_lights,
                "fans": budget_input.num_fans,
                "furniture": budget_input.num_furniture,
                "dining_tables": budget_input.num_dining_tables
            }
        }

    result = get_home_recommendations(budget_input)

    rec_id = database.add_recommendation_history(
        username=current_user.username,
        recommendation_type="home",
        input_data=budget_input.model_dump(),
        result=result
    )
    result["recommendation_id"] = rec_id
    return result

@app.post("/party-budget")
@app.post("/generate-party")
async def plan_party_budget(
    budget_input: PartyBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate party budget recommendations and persist to history"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_party_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "party_type": budget_input.party_type,
            "guests": budget_input.num_guests
        }

    result = get_party_recommendations(budget_input)

    rec_id = database.add_recommendation_history(
        username=current_user.username,
        recommendation_type="party",
        input_data=budget_input.model_dump(),
        result=result
    )
    result["recommendation_id"] = rec_id
    return result

@app.post("/jewelry-budget")
@app.post("/generate-jewelry")
async def plan_jewelry_budget(
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    request: Request = None,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate jewelry budget recommendations with optional outfit image"""
    budget_input = JewelryBudgetInput(
        total_budget=total_budget,
        occasion=occasion,
        style_preferences=preferences,
        preferences=preferences
    )

    image_path = None
    saved_filename = None
    if image and image.filename:
        image_path = save_upload_file(image)
        saved_filename = os.path.basename(image_path)

    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_jewelry_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "occasion": budget_input.occasion,
            "has_image": image_path is not None
        }

    result = get_jewelry_recommendations(budget_input, image_path)

    input_data = budget_input.model_dump()
    if saved_filename:
        input_data["image"] = saved_filename
        input_data["image_url"] = f"/static/uploads/{saved_filename}"

    rec_id = database.add_recommendation_history(
        username=current_user.username,
        recommendation_type="jewelry",
        input_data=input_data,
        result=result
    )
    result["recommendation_id"] = rec_id
    return result

# ==================== RECOMMENDATION HISTORY API ====================

@app.get("/recommendation-history")
@app.get("/api/history")
async def get_recommendation_history(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get the user's recommendation history"""
    history_list = database.get_user_recommendations(current_user.username)
    history_data = []
    for item in history_list:
        history_data.append({
            "id": item["id"],
            "timestamp": item["timestamp"],
            "type": item["type"],
            "input": item["input"],
            "summary": item["summary"]
        })
    return {"history": history_data}

@app.get("/recommendation-details/{recommendation_id}")
async def get_recommendation_details(
    recommendation_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get full details of a specific past recommendation"""
    rec = database.get_recommendation_by_id(recommendation_id)
    if not rec or rec["username"] != current_user.username:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    return {
        "id": rec["id"],
        "timestamp": rec["timestamp"],
        "type": rec["type"],
        "input": rec["input"],
        "input_data": rec.get("input_data"),
        "full_result": rec.get("full_result")
    }

@app.get("/startup")
async def startup_check():
    """Initializes and returns health status"""
    return {
        "status": "online",
        "service": "PocketSmart AI",
        "gemini_api_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
        "timestamp": datetime.utcnow().isoformat()
    }

def find_available_port(start_port: int = 8000) -> int:
    """Finds an available TCP port starting from start_port"""
    import socket
    for p in range(start_port, start_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start_port

# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn
    import webbrowser
    import threading
    import time

    preferred_port = int(os.getenv("PORT", 8000))
    port = find_available_port(preferred_port)
    host = os.getenv("HOST", "127.0.0.1")
    url = f"http://{host}:{port}"
    print("\n========================================================")
    print(f"🚀 PocketSmart AI running successfully!")
    print(f"👉 Open in browser: {url}")
    print("========================================================\n")

    def open_external_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    threading.Thread(target=open_external_browser, daemon=True).start()
    uvicorn.run(app, host=host, port=port)
