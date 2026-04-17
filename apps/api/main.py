import logging

from fastapi import FastAPI
from dotenv import load_dotenv
from routers import chat
from routers import reports

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)

app = FastAPI(
    title="Structural Design Copilot — API",
    description="Multi-agent structural engineering design suite.",
    version="1.0.0",
)

app.include_router(chat.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
