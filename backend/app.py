from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from ai import ChatMemory, get_research_result
from dataclasses import asdict
import os

app = FastAPI()

# Shared multi-turn memory
memory = ChatMemory()

class ChatRequest(BaseModel):
    message: str

@app.post("/chat")
def chat(req: ChatRequest):
    result = get_research_result(req.message, memory)
    return {"data": asdict(result)}

@app.get("/health")
def health():
    return {"status": "ok"}

# Mount the frontend at the root — must come AFTER API routes
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
