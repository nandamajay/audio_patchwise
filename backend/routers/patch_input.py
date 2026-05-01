from __future__ import annotations

from typing import List

from fastapi import APIRouter, File, UploadFile

router = APIRouter(tags=["patch_input"])


@router.post("/api/upload-patches")
async def upload_patches(files: List[UploadFile] = File(...)):
    patches = []
    for file in files:
        content = await file.read()
        patches.append(
            {
                "filename": file.filename,
                "content": content.decode("utf-8", errors="ignore"),
            }
        )
    return {"patches": patches, "count": len(patches)}
