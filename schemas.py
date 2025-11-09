from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List

# Each model corresponds to a Mongo collection named by class name lowercased

class User(BaseModel):
    email: EmailStr
    full_name: str
    hashed_password: str
    role: str = Field(default="student", description="student|instructor|admin")
    is_active: bool = True

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: Optional[str] = "student"

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: str
    is_active: bool

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class Course(BaseModel):
    title: str
    description: str
    level: str = "beginner"
    price: float = 0.0
    published: bool = False
    thumbnail_url: Optional[str] = None
    lessons: List[str] = []

class CourseUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    price: Optional[float] = None
    published: Optional[bool] = None
    thumbnail_url: Optional[str] = None
    lessons: Optional[List[str]] = None
