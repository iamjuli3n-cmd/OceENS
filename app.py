import os
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

def create_app():
    app = FastAPI()

    # Secret key n'est pas utilisé directement sans middleware dans FastAPI
    # Si besoin de sessions, vous pouvez utiliser SessionMiddleware de starlette

    # ─── Configuration Static & Templates ─────────────────
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")

    # ─── Pages ────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html")

    @app.get("/parametrage", response_class=HTMLResponse)
    async def parametrage(request: Request):
        return templates.TemplateResponse(request=request, name="parametrage.html")

    # ─── Futur : ajouter ici les routers API ──────────────
    # from routes.xxx import xxx_router
    # app.include_router(xxx_router, prefix="/api")

    return app

app = create_app()

if __name__ == '__main__':
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=True)
