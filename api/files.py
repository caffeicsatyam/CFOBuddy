from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from api.main import (
    FileResponse,
    UploadResponse,
    list_files,
    require_auth,
    upload_file,
)

router = APIRouter()


@router.get("/files", response_model=FileResponse)
async def files_proxy(payload: dict[str, Any] = Depends(require_auth)) -> FileResponse:
    return await list_files(payload=payload)


@router.post("/upload", response_model=UploadResponse)
async def upload_proxy(
    file: UploadFile = File(...),
    thread_id: Optional[str] = Form(None),
    payload: dict[str, Any] = Depends(require_auth),
    background_tasks: Optional[BackgroundTasks] = None,
) -> UploadResponse:
    return await upload_file(
        file=file,
        thread_id=thread_id,
        payload=payload,
        background_tasks=background_tasks,
    )
