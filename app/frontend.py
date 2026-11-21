from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, Response

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
ASSET_TYPES = {
    "campus.css": "text/css",
    "campus.js": "text/javascript",
    "login.js": "text/javascript",
    "vendor/bootstrap.min.css": "text/css",
}
PAGE_HEADERS = {"Cache-Control": "no-store"}
router = APIRouter(include_in_schema=False)


def asset_revision(content: bytes) -> str:
    return sha256(content).hexdigest()[:16]


def frontend_page(page_name: str) -> HTMLResponse:
    html = (APP_DIR / page_name).read_text(encoding="utf-8")
    for file_path in ASSET_TYPES:
        reference = f'"/static/{file_path}"'
        if reference in html:
            revision = asset_revision((STATIC_DIR / file_path).read_bytes())
            html = html.replace(reference, f'"/assets/{revision}/{file_path}"')
    return HTMLResponse(html, headers=PAGE_HEADERS)


@router.get("/assets/{revision}/{file_path:path}")
def versioned_asset(revision: str, file_path: str) -> Response:
    media_type = ASSET_TYPES.get(file_path)
    if media_type is None:
        raise HTTPException(404)
    content = (STATIC_DIR / file_path).read_bytes()
    if asset_revision(content) != revision:
        raise HTTPException(404)
    return Response(content, media_type=media_type,
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})
