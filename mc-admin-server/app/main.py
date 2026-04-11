from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import auth, chat
from app.websocket import routes as ws_routes

app = FastAPI(title="MC Admin Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(ws_routes.router)

@app.get("/")
async def root():
    return {"message": "MC Admin Server API", "version": "1.0.0"}

@app.get("/health")
async def health():
    return {"status": "ok"}
