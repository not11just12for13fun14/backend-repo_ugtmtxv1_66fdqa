from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from typing import Optional, List
from datetime import datetime, timedelta
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import User, UserCreate, UserPublic, Token, Course, CourseUpdate

SECRET_KEY = "dev-secret-key-change-in-prod"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

app = FastAPI(title="E-learning API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


async def get_user_by_identifier(identifier: str) -> Optional[dict]:
    # Try by email first
    user = await db["user"].find_one({"email": identifier})
    if user:
        return user
    # Fallback: allow login by full_name as a username-like field
    user = await db["user"].find_one({"full_name": identifier})
    return user


async def authenticate_user(identifier: str, password: str) -> Optional[dict]:
    user = await get_user_by_identifier(identifier)
    if not user or not verify_password(password, user.get("hashed_password", "")):
        return None
    user["id"] = str(user.pop("_id"))
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await db["user"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise credentials_exception
    user["id"] = str(user.pop("_id"))
    return user


async def get_current_admin(user=Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@app.get("/")
async def root():
    return {"ok": True, "service": "e-learning-api"}


@app.get("/test")
async def test():
    # Verify db connection on demand
    try:
        await db["__health"].insert_one({"ok": True, "ts": datetime.utcnow()})
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {e}")


async def ensure_default_admin():
    """Create a default admin if none exists. Safe to call at auth time."""
    try:
        existed = await db["user"].find_one({"role": "admin"})
        if existed:
            return
        # Create default admin based on user's request
        hashed = get_password_hash("Antonio89")
        user_doc = User(
            email="antonio.admin@demo.local",
            full_name="AntonioAdmin",
            hashed_password=hashed,
            role="admin",
        ).model_dump()
        await create_document("user", user_doc)
    except Exception:
        # Silently ignore to avoid breaking auth if DB is down
        return


# Auth routes
@app.post("/auth/register", response_model=UserPublic)
async def register(user_in: UserCreate):
    existing = await db["user"].find_one({"email": user_in.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = get_password_hash(user_in.password)
    user_doc = User(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed,
        role=user_in.role or "student",
    ).model_dump()
    created = await create_document("user", user_doc)
    return UserPublic(
        id=created["id"],
        email=created["email"],
        full_name=created["full_name"],
        role=created["role"],
        is_active=created.get("is_active", True),
    )


@app.post("/auth/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    # Ensure a default admin exists for first run
    await ensure_default_admin()
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect credentials")
    access_token = create_access_token({"sub": user["id"], "role": user.get("role", "student")})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=UserPublic)
async def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "full_name": current_user["full_name"],
        "role": current_user.get("role", "student"),
        "is_active": current_user.get("is_active", True),
    }


# Courses CRUD
@app.get("/courses", response_model=List[dict])
async def list_courses(skip: int = 0, limit: int = 50):
    docs = await get_documents("course", {}, limit)
    return docs[skip: skip + limit]


@app.post("/courses", response_model=dict)
async def create_course(course: Course, admin=Depends(get_current_admin)):
    return await create_document("course", course.model_dump())


@app.patch("/courses/{course_id}", response_model=dict)
async def update_course(course_id: str, course: CourseUpdate, admin=Depends(get_current_admin)):
    updates = {k: v for k, v in course.model_dump().items() if v is not None}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = datetime.utcnow().isoformat()
    result = await db["course"].update_one({"_id": ObjectId(course_id)}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    updated = await db["course"].find_one({"_id": ObjectId(course_id)})
    updated["id"] = str(updated.pop("_id"))
    return updated


@app.delete("/courses/{course_id}")
async def delete_course(course_id: str, admin=Depends(get_current_admin)):
    result = await db["course"].delete_one({"_id": ObjectId(course_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"deleted": True}


# Admin: list users
@app.get("/admin/users", response_model=List[dict])
async def admin_list_users(admin=Depends(get_current_admin)):
    docs = await get_documents("user", {}, 200)
    return docs
