from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

TEMPLATES = Path(__file__).parent / "templates"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home():
    return (TEMPLATES / "index.html").read_text(encoding="utf-8")
