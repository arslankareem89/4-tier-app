import hashlib
import json
import io
import logging
import os
import threading
import time
import uuid

import boto3
import psycopg2
import redis
from botocore.exceptions import BotoCoreError, ClientError

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import OAuth2PasswordBearer

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

# --------------------------------------------------
# Configuration
# --------------------------------------------------

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("task_api")

# DATABASE_URL supports local development and tests.
# ECS can instead use DB_HOST plus the RDS-managed database secret.
IS_PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production"
DATABASE_URL = os.getenv("DATABASE_URL")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "task_manager")
DB_SECRET_ARN = os.getenv("DATABASE_SECRET_ARN")

if not DATABASE_URL and not DB_HOST:
    if IS_PRODUCTION:
        raise RuntimeError(
            "Production requires DATABASE_URL or DB_HOST plus DATABASE_SECRET_ARN"
        )
    DATABASE_URL = "sqlite:///./test.db"

if not DATABASE_URL and DB_HOST and not DB_SECRET_ARN:
    raise RuntimeError("DATABASE_SECRET_ARN is required when DB_HOST is configured")

# Never use the development fallback in production.
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError("SECRET_KEY must be configured in production")

    SECRET_KEY = "local-development-secret-change-me"
    logger.warning("Using development-only JWT secret")

TOKEN_EXPIRE_MINUTES = 60 * 24
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# Use S3 when configured (ECS); otherwise use local storage.
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_REGION = (
    os.getenv("AWS_REGION")
    or os.getenv("AWS_DEFAULT_REGION")
    or "us-east-1"
)
s3_client = boto3.client("s3", region_name=AWS_REGION) if S3_BUCKET else None

cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001",
    ).split(",")
    if origin.strip()
]

# --------------------------------------------------
# Database
# --------------------------------------------------

engine_options = {"pool_pre_ping": True}

if DATABASE_URL:
    # Local development, tests, or an explicitly provided database URL.
    if DATABASE_URL.startswith("sqlite"):
        engine_options["connect_args"] = {"check_same_thread": False}

    engine = create_engine(DATABASE_URL, **engine_options)

else:
    # Do not put the rotating RDS password into ECS environment variables.
    # Fetch the current RDS-managed secret for each newly created DB connection.
    secrets_manager = boto3.client("secretsmanager", region_name=AWS_REGION)

    def connect_to_rds():
        secret_response = secrets_manager.get_secret_value(
            SecretId=DB_SECRET_ARN
        )
        credentials = json.loads(secret_response["SecretString"])

        return psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=credentials["username"],
            password=credentials["password"],
            connect_timeout=5,
        )

    engine = create_engine(
        "postgresql+psycopg2://",
        creator=connect_to_rds,
        pool_pre_ping=True,
        pool_recycle=1800,
    )

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


# --------------------------------------------------
# Database models
# --------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = mapped_column(Integer, primary_key=True)
    email = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash = mapped_column(String(255), nullable=False)

    tasks = relationship(
        "Task",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    uploads = relationship(
        "Upload",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Task(Base):
    __tablename__ = "tasks"

    id = mapped_column(Integer, primary_key=True)
    title = mapped_column(String(200), nullable=False)
    description = mapped_column(Text, nullable=False, default="")
    status = mapped_column(String(32), nullable=False, default="PENDING")

    user_id = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner = relationship("User", back_populates="tasks")


class Upload(Base):
    __tablename__ = "uploads"

    id = mapped_column(String(36), primary_key=True)
    original_name = mapped_column(String(255), nullable=False)
    stored_name = mapped_column(String(255), nullable=False)
    content_type = mapped_column(String(255), nullable=False)
    size = mapped_column(Integer, nullable=False, default=0)
    sha256 = mapped_column(String(64), nullable=True)

    processing_status = mapped_column(
        String(32),
        nullable=False,
        default="processing",
    )

    user_id = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    created_at = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    owner = relationship("User", back_populates="uploads")


# --------------------------------------------------
# Request and response schemas
# --------------------------------------------------

class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(RegisterRequest):
    pass


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10000)
    status: str = Field(default="PENDING", max_length=32)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    status: Optional[str] = Field(default=None, max_length=32)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: str
    created_at: datetime


class UploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    content_type: str
    size: int
    sha256: Optional[str]
    processing_status: str
    created_at: datetime


# --------------------------------------------------
# In-memory task cache
# --------------------------------------------------

class TTLCache:
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self.values = {}
        self.lock = threading.Lock()

    def get(self, key):
        with self.lock:
            entry = self.values.get(key)

            if not entry or entry[0] <= time.monotonic():
                self.values.pop(key, None)
                return None

            return entry[1]

    def set(self, key, value):
        with self.lock:
            self.values[key] = (
                time.monotonic() + self.ttl_seconds,
                value,
            )

    def invalidate(self, key):
        with self.lock:
            self.values.pop(key, None)


class RedisTTLCache:
    """Shared Redis/Valkey cache; cache failures fall back to the database."""

    def __init__(self, url: str, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self.client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
            health_check_interval=30,
        )

    @staticmethod
    def _json_default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        raise TypeError(f"Cannot JSON-encode {type(value).__name__}")

    def get(self, key):
        try:
            payload = self.client.get(key)
        except redis.exceptions.RedisError:
            logger.warning(
                "shared_cache_read_failed key=%s; bypassing cache",
                key,
                exc_info=True,
            )
            return None

        if payload is None:
            return None

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            logger.warning(
                "shared_cache_invalid_payload key=%s",
                key,
                exc_info=True,
            )
            self.invalidate(key)
            return None

    def set(self, key, value):
        try:
            payload = json.dumps(
                value,
                default=self._json_default,
                separators=(",", ":"),
            )
            self.client.set(key, payload, ex=self.ttl_seconds)
        except (redis.exceptions.RedisError, TypeError, ValueError):
            logger.warning(
                "shared_cache_write_failed key=%s",
                key,
                exc_info=True,
            )

    def invalidate(self, key):
        try:
            self.client.delete(key)
        except redis.exceptions.RedisError:
            logger.warning(
                "shared_cache_invalidation_failed key=%s",
                key,
                exc_info=True,
            )


CACHE_URL = os.getenv("CACHE_URL")
if CACHE_URL:
    try:
        task_cache = RedisTTLCache(CACHE_URL)
        logger.info("shared_task_cache_enabled ttl_seconds=30")
    except (ValueError, redis.exceptions.RedisError):
        logger.exception("shared_cache_initialization_failed")
        task_cache = TTLCache()
else:
    if IS_PRODUCTION:
        logger.warning("CACHE_URL missing; using process-local task cache")
    task_cache = TTLCache()

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
app = FastAPI(title="Task Management API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# --------------------------------------------------
# Database dependency
# --------------------------------------------------

def get_db():
    with SessionLocal() as db:
        yield db


# --------------------------------------------------
# Authentication
# --------------------------------------------------

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise credentials_error

    user = db.get(User, user_id)

    if user is None:
        raise credentials_error

    return user


def create_access_token(user_id: int) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=TOKEN_EXPIRE_MINUTES
    )

    return jwt.encode(
        {"sub": str(user_id), "exp": expires},
        SECRET_KEY,
        algorithm="HS256",
    )


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def serialize_task(task: Task):
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "created_at": task.created_at,
    }


def process_upload(upload_id: str, storage_key: str):
    try:
        digest = hashlib.sha256()

        if S3_BUCKET:
            response = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=storage_key,
            )
            uploaded_file = response["Body"]

            try:
                for chunk in iter(
                    lambda: uploaded_file.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)
            finally:
                uploaded_file.close()

        else:
            with open(storage_key, "rb") as uploaded_file:
                for chunk in iter(
                    lambda: uploaded_file.read(1024 * 1024),
                    b"",
                ):
                    digest.update(chunk)

        with SessionLocal() as db:
            upload = db.get(Upload, upload_id)

            if upload:
                upload.sha256 = digest.hexdigest()
                upload.processing_status = "complete"
                db.commit()

    except Exception:
        logger.exception(
            "upload_processing_failed upload_id=%s",
            upload_id,
        )

        try:
            with SessionLocal() as db:
                upload = db.get(Upload, upload_id)

                if upload:
                    upload.processing_status = "failed"
                    db.commit()

        except Exception:
            logger.exception(
                "upload_failure_status_update_failed upload_id=%s",
                upload_id,
            )


# --------------------------------------------------
# Startup and health
# --------------------------------------------------

@app.on_event("startup")
def initialize_database():
    if not S3_BUCKET:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# --------------------------------------------------
# Authentication endpoints
# --------------------------------------------------

@app.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()

    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(
            status_code=422,
            detail="Enter a valid email address",
        )

    user = User(
        email=email,
        password_hash=password_context.hash(payload.password),
    )

    db.add(user)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists",
        )

    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))


@app.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    if user is None or not password_context.verify(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
        )

    return TokenResponse(access_token=create_access_token(user.id))


@app.get("/auth/me", response_model=UserResponse)
def current_user(user: User = Depends(get_current_user)):
    return user


# --------------------------------------------------
# Task endpoints
# --------------------------------------------------

@app.get("/tasks", response_model=list[TaskResponse])
def get_tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cache_key = f"tasks:{user.id}"
    cached_tasks = task_cache.get(cache_key)

    if cached_tasks is not None:
        return cached_tasks

    tasks = db.scalars(
        select(Task)
        .where(Task.user_id == user.id)
        .order_by(Task.id.desc())
    ).all()

    result = [serialize_task(task) for task in tasks]
    task_cache.set(cache_key, result)

    return result


@app.post(
    "/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    payload: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = Task(**payload.model_dump(), user_id=user.id)

    db.add(task)
    db.commit()
    db.refresh(task)

    task_cache.invalidate(f"tasks:{user.id}")

    return task


@app.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user.id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    task_cache.invalidate(f"tasks:{user.id}")

    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.scalar(
        select(Task).where(
            Task.id == task_id,
            Task.user_id == user.id,
        )
    )

    if task is None:
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    db.delete(task)
    db.commit()
    task_cache.invalidate(f"tasks:{user.id}")


# --------------------------------------------------
# Upload endpoints
# --------------------------------------------------

@app.get("/uploads", response_model=list[UploadResponse])
def get_uploads(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.scalars(
        select(Upload)
        .where(Upload.user_id == user.id)
        .order_by(Upload.created_at.desc())
    ).all()


@app.post(
    "/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename or not Path(file.filename).name.strip():
        raise HTTPException(
            status_code=400,
            detail="A filename is required",
        )

    upload_id = str(uuid.uuid4())
    stored_name = f"{upload_id}{Path(file.filename or 'upload').suffix[:16]}"
    stored_path = UPLOAD_DIR / stored_name
    size = 0
    s3_buffer = io.BytesIO() if S3_BUCKET else None

    try:
        if not S3_BUCKET:
            with stored_path.open("wb") as destination:
                while chunk := file.file.read(1024 * 1024):
                    size += len(chunk)

                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="File exceeds the 10 MB upload limit",
                        )

                    destination.write(chunk)

        else:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)

                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="File exceeds the 10 MB upload limit",
                    )

                s3_buffer.write(chunk)

            if size > 0:
                s3_buffer.seek(0)
                s3_client.put_object(
                    Bucket=S3_BUCKET,
                    Key=stored_name,
                    Body=s3_buffer.getvalue(),
                    ContentType=file.content_type or "application/octet-stream",
                )

    except HTTPException:
        if not S3_BUCKET:
            stored_path.unlink(missing_ok=True)
        raise

    except (OSError, BotoCoreError, ClientError):
        if not S3_BUCKET:
            stored_path.unlink(missing_ok=True)

        logger.exception(
            "upload_storage_failed filename=%s",
            Path(file.filename).name,
        )

        raise HTTPException(
            status_code=500,
            detail="File could not be stored",
        )

    finally:
        if s3_buffer is not None:
            s3_buffer.close()

    if size == 0:
        if not S3_BUCKET:
            stored_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=400,
            detail="Empty files are not accepted",
        )

    upload = Upload(
        id=upload_id,
        original_name=Path(file.filename or "upload").name[:255],
        stored_name=stored_name,
        content_type=file.content_type or "application/octet-stream",
        size=size,
        user_id=user.id,
    )

    try:
        db.add(upload)
        db.commit()
        db.refresh(upload)

    except Exception:
        db.rollback()

        if S3_BUCKET:
            try:
                s3_client.delete_object(
                    Bucket=S3_BUCKET,
                    Key=stored_name,
                )
            except Exception:
                logger.exception(
                    "upload_object_cleanup_failed upload_id=%s",
                    upload_id,
                )
        else:
            stored_path.unlink(missing_ok=True)

        logger.exception(
            "upload_record_creation_failed upload_id=%s",
            upload_id,
        )

        raise HTTPException(
            status_code=500,
            detail="Upload metadata could not be saved",
        )

    background_tasks.add_task(
        process_upload,
        upload_id,
        stored_name if S3_BUCKET else str(stored_path),
    )

    return upload


@app.get("/uploads/{upload_id}/file")
def download_file(
    upload_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    upload = db.scalar(
        select(Upload).where(
            Upload.id == upload_id,
            Upload.user_id == user.id,
        )
    )

    if upload is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    if S3_BUCKET:
        try:
            response = s3_client.get_object(
                Bucket=S3_BUCKET,
                Key=upload.stored_name,
            )
            content = response["Body"].read()

        except (BotoCoreError, ClientError) as exc:
            error_code = (
                getattr(exc, "response", {})
                .get("Error", {})
                .get("Code")
            )

            if error_code in {"NoSuchKey", "404", "NotFound"}:
                raise HTTPException(
                    status_code=404,
                    detail="Stored file is missing",
                )

            logger.exception(
                "upload_download_failed upload_id=%s",
                upload_id,
            )

            raise HTTPException(
                status_code=500,
                detail="File could not be retrieved",
            )

        return Response(
            content=content,
            media_type=upload.content_type,
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{upload.original_name}"'
                )
            },
        )

    stored_path = UPLOAD_DIR / upload.stored_name

    if not stored_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Stored file is missing",
        )

    return FileResponse(
        stored_path,
        filename=upload.original_name,
        media_type=upload.content_type,
    )