
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from python_client_app.routers import client_router

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

app.include_router(client_router.router, prefix="/client-api")

if __name__ == "__main__":
    import uvicorn
    # Run on a different port than the main API (8000)
    uvicorn.run("python_client_app.main:app", host="0.0.0.0", port=8001, reload=True)
