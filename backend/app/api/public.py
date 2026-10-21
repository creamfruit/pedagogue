from pathlib import Path

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.api.deps import SessionDep
from app.core.config import settings
from app.services.public_pages import PublicPieceService, parse_slug

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
CACHE = "public, max-age=300, s-maxage=3600"

router = APIRouter(prefix="/public", tags=["public"], include_in_schema=False)


def site(path: str = "/") -> str:
    return f"{settings.return_base_url}{path}"


environment = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "xml"]), trim_blocks=True, lstrip_blocks=True)
environment.globals["site"] = site


def render(name: str, *, status_code: int = status.HTTP_200_OK, **context) -> HTMLResponse:
    body = environment.get_template(name).render(**context)
    headers = {"Cache-Control": CACHE if status_code == 200 else "no-store"}
    return HTMLResponse(body, status_code=status_code, headers=headers)


def not_found() -> HTMLResponse:
    return render("public/notfound.html", status_code=status.HTTP_404_NOT_FOUND)


def moved(path: str) -> RedirectResponse:
    return RedirectResponse(site(path), status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.get("/music")
async def music_index(session: SessionDep) -> Response:
    listing = await PublicPieceService(session).listing()
    seo = {"title": "Piano pieces and how hard they are · Pedagogue", "description": "", "canonical": site("/music")}
    return render("public/listing.html", seo=seo, **listing)


@router.get("/music/{slug}")
async def music_page(slug: str, session: SessionDep) -> Response:
    piece_id = parse_slug(slug)
    page = await PublicPieceService(session).piece_page(piece_id) if piece_id is not None else None
    if page is None:
        return not_found()
    if slug != page["slug"]:
        return moved(f"/music/{page['slug']}")
    seo = {"title": f"{page['full_title']} · Pedagogue", "description": "", "canonical": site(f"/music/{page['slug']}")}
    return render("public/piece.html", seo=seo, **page)


@router.get("/composers")
async def composers_index(session: SessionDep) -> Response:
    listing = await PublicPieceService(session).listing()
    seo = {"title": "Piano composers · Pedagogue", "description": "", "canonical": site("/composers")}
    return render("public/composers.html", seo=seo, **listing)


@router.get("/composers/{slug}")
async def composer_page(slug: str, session: SessionDep) -> Response:
    composer_id = parse_slug(slug)
    page = await PublicPieceService(session).composer_page(composer_id) if composer_id is not None else None
    if page is None:
        return not_found()
    if slug != page["slug"]:
        return moved(f"/composers/{page['slug']}")
    seo = {"title": f"{page['composer'].name} · Pedagogue", "description": "", "canonical": site(f"/composers/{page['slug']}")}
    return render("public/composer.html", seo=seo, **page)
