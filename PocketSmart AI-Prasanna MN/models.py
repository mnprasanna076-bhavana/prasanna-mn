from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime

class RegisterUser(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    password: str = Field(..., min_length=4)

class UserLogin(BaseModel):
    username: str
    password: str

class UserInDB(BaseModel):
    id: Optional[str] = None
    username: str
    email: str
    full_name: Optional[str] = None
    hashed_password: str
    is_active: bool = True
    created_at: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    username: Optional[str] = None

class UserSession(BaseModel):
    username: str
    login_time: datetime
    last_activity: datetime
    token: str
    user_data: Dict[str, Any] = {}

class HomeBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0, description="Total budget in INR or selected currency")
    num_lights: int = Field(default=0, ge=0)
    num_fans: int = Field(default=0, ge=0)
    num_furniture: int = Field(default=0, ge=0)
    num_dining_tables: int = Field(default=0, ge=0)
    has_living_room: bool = True
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = None

class PartyBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0)
    num_guests: int = Field(default=10, ge=1)
    party_type: str = Field(default="Birthday", description="e.g. Birthday, Anniversary, Wedding, Reunion")
    venue_type: Optional[str] = Field(default="Home", description="e.g. Home, Banquet Hall, Outdoor, Restaurant")
    needs_catering: bool = True
    needs_decoration: bool = True
    needs_entertainment: bool = False
    additional_requirements: Optional[str] = None

class JewelryBudgetInput(BaseModel):
    total_budget: float = Field(..., gt=0)
    occasion: str = Field(..., description="e.g. Wedding, Daily Wear, Party, Festival, Engagement")
    style_preferences: Optional[str] = Field(default=None, description="e.g. Minimalist, Traditional Gold, Silver, Diamond")
    preferences: Optional[str] = None  # alias for style_preferences

class RecommendationHistoryItem(BaseModel):
    id: str
    username: str
    timestamp: str
    recommendation_type: str  # 'home', 'party', 'jewelry'
    input_data: Dict[str, Any]
    input_summary: str
    result_summary: str
    result: Dict[str, Any]
