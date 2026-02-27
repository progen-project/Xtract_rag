
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from python_client_app.routers import client_router
from python_client_app.routers import public_router

app = FastAPI(
    title="PetroRAG Python Client Proxy",
    description="A strongly-typed FastAPI client acting as a gateway to the main PetroRAG API.",
    version="1.0.0"
)

# CORS (Allow all for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ── Routers ──────────────────────────────────────────────────────
app.include_router(client_router.router, prefix="/client-api")
app.include_router(public_router.router)           # root-level /documents/...

# ── Static file mounts (images accessible without /client-api) ───
_extracted = Path("/app/extracted_images")
_chat_imgs = Path("/app/chat_images")

if _extracted.is_dir():
    app.mount("/extracted_images", StaticFiles(directory=str(_extracted)), name="extracted_images")
if _chat_imgs.is_dir():
    app.mount("/chat_images", StaticFiles(directory=str(_chat_imgs)), name="chat_images")

if __name__ == "__main__":
    import uvicorn
    # Run on a different port than the main API (8080)
    uvicorn.run("python_client_app.main:app", host="0.0.0.0", port=8001, reload=True)
