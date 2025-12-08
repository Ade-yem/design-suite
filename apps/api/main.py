from fastapi import FastAPI
from dotenv import load_dotenv
from routers import chat

load_dotenv()

app = FastAPI()

app.include_router(chat.router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "ok"}
