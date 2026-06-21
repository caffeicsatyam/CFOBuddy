import asyncio
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Security,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse as FastAPIFileResponse
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from build_index import build_index
from cfobuddy_logging import configure_logging
from load_data import load_csvs_to_neon
from core.user_scope import user_storage_key

load_dotenv()

logger = configure_logging()


LEGACY_API_KEY = os.getenv("CFO_BUDDY_API_KEY", "").strip()
JWT_SECRET = os.getenv("CFO_BUDDY_JWT_SECRET", "").strip() or LEGACY_API_KEY
AUTH_USERNAME = os.getenv("CFO_BUDDY_AUTH_USERNAME", "admin").strip()
AUTH_PASSWORD = os.getenv("CFO_BUDDY_AUTH_PASSWORD", "").strip() or LEGACY_API_KEY
JWT_EXPIRES_IN_SECONDS = int(os.getenv("CFO_BUDDY_JWT_EXPIRES_IN_SECONDS", "43200"))

if not JWT_SECRET:
    logger.error("Neither CFO_BUDDY_JWT_SECRET nor CFO_BUDDY_API_KEY is configured.")
    raise RuntimeError("Authentication is not configured")

if not AUTH_PASSWORD:
    logger.error("No login password configured. Set CFO_BUDDY_AUTH_PASSWORD or CFO_BUDDY_API_KEY.")
    raise RuntimeError("Login password is not configured")

app = FastAPI(
    title="CFOBuddy AI",
    description="AI Powered Financial Assistant API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
    ],
    allow_origin_regex=(
        r"https?://("
        r"localhost|127\.0\.0\.1|"
        r"192\.168\.\d+\.\d+|"
        r"10\.\d+\.\d+\.\d+|"
        r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+"
        r")(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


DATA_FOLDER = Path("data")
CHARTS_FOLDER = Path("static/charts")
ALLOWED_EXTENSIONS = {"csv", "pdf", "xlsx", "xls", "docx"}
MAX_UPLOAD_BYTES = int(os.getenv("CFO_BUDDY_MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))

from core.auth import create_access_token, decode_access_token, get_password_hash, verify_password, LEGACY_API_KEY
from core.database import connect_to_mongo, close_mongo_connection, get_db
from models.user import UserCreate, UserInDB, UserResponse as UserResponseModel

def verify_legacy_api_key_login(username: str, password: str) -> bool:
    return (
        bool(LEGACY_API_KEY)
        and secrets.compare_digest(username, "legacy-api-key")
        and secrets.compare_digest(password, LEGACY_API_KEY)
    )

def require_auth(token: Optional[str] = Security(oauth2_scheme)) -> dict[str, Any]:
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if LEGACY_API_KEY and secrets.compare_digest(token, LEGACY_API_KEY):
        return {"sub": "legacy-api-key", "auth_type": "api_key"}
    payload = decode_access_token(token)
    payload["auth_type"] = "jwt"
    return payload

# Schemas
class ChatRequest(BaseModel):
    message: str
    thread_id: str = "main"

class ChatResponse(BaseModel):
    response: str
    thread_id: str
    chart: Optional[dict] = None

class ThreadInfo(BaseModel):
    id: str
    name: str

class ThreadHistoryMessage(BaseModel):
    role: str
    content: str
    chart: Optional[dict[str, Any]] = None

class ThreadResponse(BaseModel):
    threads: list[ThreadInfo]

class ThreadHistoryResponse(BaseModel):
    thread_id: str
    messages: list[ThreadHistoryMessage]

class FileInfo(BaseModel):
    name: str
    type: str
    size: str

class FileResponse(BaseModel):
    files: list[FileInfo]

class UploadResponse(BaseModel):
    message: str
    filename: str
    thread_id: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str

class UserResponse(BaseModel):
    username: str
    auth_type: str

# Status tracking
indexing_status = {"status": "ready", "message": "Idle"}

def build_index_with_status(file_path: str | None = None, username: str | None = None) -> None:
    global indexing_status
    target = Path(file_path).name if file_path else "documents"
    indexing_status = {"status": "indexing", "message": f"Indexing {target}"}
    try:
        indexed_count = build_index([file_path] if file_path else None, username=username)
        try:
            from tools.search import reload_index

            reload_index()
        except Exception:
            logger.warning("Search index cache reload failed", exc_info=True)

        if indexed_count == 0:
            message = "Document is already indexed"
        else:
            message = f"Indexed {indexed_count} document section(s)"
        indexing_status = {"status": "ready", "message": message}
    except Exception as exc:
        logger.exception("Index build failed")
        indexing_status = {"status": "error", "message": str(exc)}


def remember_upload_in_thread(thread_id: str | None, filename: str, username: str) -> None:
    """Persist upload context so follow-up chat turns can refer to the file."""
    if not thread_id:
        return

    try:
        from core.graph import CFOBuddy

        config = {"configurable": {"thread_id": thread_id, "username": username}}
        CFOBuddy.update_state(
            config,
            {
                "messages": [
                    HumanMessage(content=f"Uploaded file: {filename}"),
                    AIMessage(
                        content=(
                            f"File '{filename}' was uploaded and is available for analysis. "
                            "Use list_available_files, list_tables, sql_query, or "
                            "search_financial_docs as appropriate for follow-up questions."
                        )
                    ),
                ]
            },
        )
    except Exception:
        logger.warning("Failed to persist upload context for thread %s", thread_id, exc_info=True)

@app.on_event("startup")
async def ensure_initial_csv_load() -> None:
    await connect_to_mongo()
    # Don't block startup — load CSVs in background so the server can accept requests immediately
    asyncio.create_task(asyncio.to_thread(load_csvs_to_neon))

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()

# Routes
@app.get("/", tags=["Health"])
async def root() -> dict[str, str]:
    return {"name": "CFO Buddy API", "version": "1.0.0", "status": "running", "docs": "/docs"}

@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/auth/register", response_model=UserResponseModel, tags=["Auth"])
async def register(user_in: UserCreate):
    db = get_db()
    existing_user = await db.users.find_one({"username": user_in.username})
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = get_password_hash(user_in.password)
    user_dict = user_in.model_dump()
    del user_dict["password"]
    db_user = UserInDB(**user_dict, hashed_password=hashed_password)
    
    await db.users.insert_one(db_user.model_dump())
    
    return UserResponseModel(**db_user.model_dump(), auth_type="jwt")

@app.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    if verify_legacy_api_key_login(form_data.username, form_data.password):
        return TokenResponse(access_token=LEGACY_API_KEY, username="legacy-api-key")

    db = get_db()
    user = await db.users.find_one({"username": form_data.username})
    
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(form_data.username)
    return TokenResponse(access_token=token, username=form_data.username)

@app.get("/auth/me", response_model=UserResponseModel, tags=["Auth"])
async def read_current_user(payload: dict[str, Any] = Depends(require_auth)) -> UserResponseModel:
    username = str(payload.get("sub", AUTH_USERNAME))
    auth_type = str(payload.get("auth_type", "jwt"))
    
    if auth_type == "api_key" or username == "legacy-api-key":
        return UserResponseModel(username=username, auth_type=auth_type, created_at=datetime.utcnow(), company="Admin", full_name="Admin")
        
    db = get_db()
    user = await db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return UserResponseModel(**user, auth_type=auth_type)

def parse_chart_payload(content: str) -> Optional[dict[str, Any]]:
    for marker in ("CHART_JSON:", "CHART_DATA:"):
        if marker not in content:
            continue
        try:
            json_str = content.split(marker, maxsplit=1)[1].strip()
            brace_count = 0
            end_idx = 0
            for i, ch in enumerate(json_str):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                return json.loads(json_str[:end_idx])
            return json.loads(json_str)
        except Exception:
            logger.warning("Failed to parse chart payload")
            return None
    return None

def remove_chart_payload(content: str) -> str:
    clean = content
    for marker in ("CHART_JSON:", "CHART_DATA:"):
        if marker in clean:
            clean = clean.split(marker, maxsplit=1)[0].strip()
    return clean

def parse_response(messages: list[Any]) -> tuple[str, Optional[dict[str, Any]]]:
    text = ""
    chart = None
    for msg in messages:
        content = msg.content
        if isinstance(content, str):
            chart_payload = parse_chart_payload(content)
            if chart_payload is not None:
                chart = chart_payload
            
            if getattr(msg, "type", "") == "ai":
                text = remove_chart_payload(content)
    return text.strip(), chart

def text_from_stream_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content") or ""
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)
    return ""

def sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"

router = APIRouter(dependencies=[Depends(require_auth)])

@router.get("/threads", response_model=ThreadResponse)
async def get_threads(payload: dict[str, Any] = Depends(require_auth)) -> ThreadResponse:
    from core.memory import retrieve_threads_with_preview
    username = payload.get("sub", AUTH_USERNAME)
    auth_type = payload.get("auth_type", "jwt")
    db = get_db()
    
    try:
        all_threads = retrieve_threads_with_preview()
        if auth_type == "api_key" or username == "legacy-api-key":
            threads = all_threads
        else:
            user = await db.users.find_one({"username": username})
            user_threads = user.get("threads", []) if user else []
            threads = [t for t in all_threads if t["id"] in user_threads]
            
        if not threads:
            threads = [{"id": "main", "name": "Main Analysis"}]
            if auth_type != "api_key" and username != "legacy-api-key":
                await db.users.update_one({"username": username}, {"$addToSet": {"threads": "main"}})
                
        return ThreadResponse(threads=[ThreadInfo(**t) for t in threads])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.delete("/threads/{thread_id}")
async def remove_thread(thread_id: str) -> dict[str, str]:
    from core.memory import delete_thread
    success = delete_thread(thread_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete thread")
    return {"status": "deleted", "thread_id": thread_id}

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, payload: dict[str, Any] = Depends(require_auth)) -> ChatResponse:
    username = payload.get("sub", AUTH_USERNAME)
    auth_type = payload.get("auth_type", "jwt")
    
    if auth_type != "api_key" and username != "legacy-api-key":
        db = get_db()
        await db.users.update_one({"username": username}, {"$addToSet": {"threads": request.thread_id}})

    from core.graph import CFOBuddy
    config = {"configurable": {"thread_id": request.thread_id, "username": username}}
    try:
        response = await asyncio.to_thread(
            CFOBuddy.invoke,
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )
        text, chart = parse_response(response["messages"])
        return ChatResponse(response=text, thread_id=request.thread_id, chart=chart)
    except Exception as exc:
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/chat/stream")
async def chat_stream(request: ChatRequest, payload: dict[str, Any] = Depends(require_auth)) -> StreamingResponse:
    username = payload.get("sub", AUTH_USERNAME)
    auth_type = payload.get("auth_type", "jwt")
    
    if auth_type != "api_key" and username != "legacy-api-key":
        db = get_db()
        await db.users.update_one({"username": username}, {"$addToSet": {"threads": request.thread_id}})

    from core.graph import CFOBuddy

    config = {"configurable": {"thread_id": request.thread_id, "username": username}}

    async def event_stream():
        queue: asyncio.Queue[Any] = asyncio.Queue()
        stop = object()
        loop = asyncio.get_running_loop()

        def stream_in_thread() -> None:
            try:
                for message_chunk, _metadata in CFOBuddy.stream(
                    {"messages": [HumanMessage(content=request.message)]},
                    config=config,
                    stream_mode="messages",
                ):
                    token = text_from_stream_content(getattr(message_chunk, "content", ""))
                    if token:
                        loop.call_soon_threadsafe(
                            queue.put_nowait,
                            sse_event("token", {"token": token}),
                        )

                state = CFOBuddy.get_state(config)
                text, chart = parse_response(state.values.get("messages", []))
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    sse_event(
                        "done",
                        {"response": text, "thread_id": request.thread_id, "chart": chart},
                    ),
                )
            except Exception as exc:
                logger.exception("Streaming chat request failed")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    sse_event("error", {"detail": str(exc)}),
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, stop)

        worker = asyncio.create_task(asyncio.to_thread(stream_in_thread))
        while True:
            item = await queue.get()
            if item is stop:
                break
            yield item
        await worker

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/files", response_model=FileResponse)
async def list_files(payload: dict[str, Any] = Depends(require_auth)) -> FileResponse:
    username = payload.get("sub", AUTH_USERNAME)
    user_folder = DATA_FOLDER / user_storage_key(username)
    
    if not user_folder.exists():
        return FileResponse(files=[])
    files = []
    for path in user_folder.iterdir():
        if path.is_file() and path.suffix.lower().lstrip(".") in ALLOWED_EXTENSIONS:
            files.append(FileInfo(name=path.name, type=path.suffix.lstrip(".").upper(), size=f"{path.stat().st_size / 1024:.1f} KB"))
    return FileResponse(files=files)

@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    file: UploadFile = File(...), 
    thread_id: Optional[str] = Form(None),
    payload: dict[str, Any] = Depends(require_auth),
    background_tasks: BackgroundTasks = None
) -> UploadResponse:
    if not file.filename: raise HTTPException(status_code=400, detail="No file selected")
    username = payload.get("sub", AUTH_USERNAME)
    filename = Path(file.filename).name
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {allowed}")

    user_folder = DATA_FOLDER / user_storage_key(username)
    user_folder.mkdir(parents=True, exist_ok=True)
    
    filepath = user_folder / filename
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        max_mb = MAX_UPLOAD_BYTES / (1024 * 1024)
        raise HTTPException(status_code=413, detail=f"File is too large. Maximum size is {max_mb:.0f} MB.")
    auth_type = payload.get("auth_type", "jwt")
    if thread_id and auth_type != "api_key" and username != "legacy-api-key":
        db = get_db()
        await db.users.update_one({"username": username}, {"$addToSet": {"threads": thread_id}})
    filepath.write_bytes(content)
    remember_upload_in_thread(thread_id, filename, username)
    
    if background_tasks is None: background_tasks = BackgroundTasks()
    if filepath.suffix.lower() == ".csv": 
        background_tasks.add_task(load_csvs_to_neon, [str(filepath)], True, username)
    background_tasks.add_task(build_index_with_status, str(filepath), username)
    return UploadResponse(message=f"'{filename}' uploaded successfully", filename=filename, thread_id=thread_id)

@router.get("/threads/{thread_id}/history", response_model=ThreadHistoryResponse)
async def get_history(thread_id: str) -> ThreadHistoryResponse:
    from core.graph import CFOBuddy
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = CFOBuddy.get_state(config)
        messages = state.values.get("messages", [])
        history_messages: list[ThreadHistoryMessage] = []
        pending_chart: Optional[dict[str, Any]] = None
        last_ai_index: Optional[int] = None

        for msg in messages:
            content = msg.content if isinstance(msg.content, str) else text_from_stream_content(msg.content)
            chart_payload = parse_chart_payload(content) if content else None
            if chart_payload is not None:
                pending_chart = chart_payload

            msg_type = getattr(msg, "type", "")
            if msg_type not in ["human", "ai"]:
                continue

            clean_content = remove_chart_payload(content)
            chart = None
            if msg_type == "ai" and pending_chart is not None:
                chart = pending_chart
                pending_chart = None

            if msg_type == "ai" and not clean_content and chart is None:
                continue

            history_messages.append(
                ThreadHistoryMessage(role=msg_type, content=clean_content, chart=chart)
            )
            if msg_type == "ai":
                last_ai_index = len(history_messages) - 1

        if pending_chart is not None and last_ai_index is not None:
            history_messages[last_ai_index].chart = pending_chart

        return ThreadHistoryResponse(thread_id=thread_id, messages=history_messages)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@router.get("/indexing_status")
async def get_indexing_status() -> dict[str, str]:
    return indexing_status

@app.get("/charts/{filename}", tags=["Charts"])
async def serve_chart(filename: str) -> FastAPIFileResponse:
    chart_path = CHARTS_FOLDER / Path(filename).name
    if not chart_path.exists() or not chart_path.is_file():
        raise HTTPException(status_code=404, detail="Chart not found")
    media = "text/html" if chart_path.suffix.lower() == ".html" else "image/png"
    return FastAPIFileResponse(chart_path, media_type=media)

app.include_router(router)
