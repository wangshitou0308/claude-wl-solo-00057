"""uvicorn 入口：python -m app.main 或 uvicorn app.main:app"""
from __future__ import annotations

from .api import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
