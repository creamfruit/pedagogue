from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.api.deps import SessionDep
from app.services import cards, seo
from app.services.public_pages import PublicPieceService, parse_slug
from app.services.seo import site

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
CACHE = "public, max-age=300, s-maxage=3600"

router = APIRouter(prefix="/public", tags=["public"], include_in_schema=False)


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
    return render("public/listing.html", seo=seo.listing_seo(listing["count"], len(listing["groups"])), **listing)


@router.get("/music/{slug}")
async def music_page(slug: str, session: SessionDep) -> Response:
    piece_id = parse_slug(slug)
    page = await PublicPieceService(session).piece_page(piece_id) if piece_id is not None else None
    if page is None:
        return not_found()
    if slug != page["slug"]:
        return moved(f"/music/{page['slug']}")
    return render("public/piece.html", seo=seo.piece_seo(page), **page)


@router.get("/music/{slug}/card.png")
async def music_card(slug: str, session: SessionDep) -> Response:
    piece_id = parse_slug(slug)
    page = await PublicPieceService(session).piece_page(piece_id) if piece_id is not None else None
    if page is None:
        return not_found()
    if slug != page["slug"]:
        return moved(f"/music/{page['slug']}/card.png")
    top = page["sections"][0] if page["sections"] else None
    hardest = f"{top['label'] or 'Bars'} · {top['measure_span']}" if top else ""
    image = cards.piece_card(
        title=page["title"],
        composer=page["composer"].name if page["composer"] else "",
        score=page["difficulty"]["score"],
        band=page["difficulty"]["band"],
        hardest=hardest,
        techniques=[technique["name"] for technique in page["techniques"]],
        footer=urlparse(site("/")).netloc,
        seed=page["id"],
    )
    return Response(image, media_type="image/png", headers={"Cache-Control": CACHE})


@router.get("/composers")
async def composers_index(session: SessionDep) -> Response:
    listing = await PublicPieceService(session).listing()
    return render("public/composers.html", seo=seo.composers_seo(listing["groups"]), **listing)


@router.get("/composers/{slug}")
async def composer_page(slug: str, session: SessionDep) -> Response:
    composer_id = parse_slug(slug)
    page = await PublicPieceService(session).composer_page(composer_id) if composer_id is not None else None
    if page is None:
        return not_found()
    if slug != page["slug"]:
        return moved(f"/composers/{page['slug']}")
    return render("public/composer.html", seo=seo.composer_seo(page), **page)


@router.get("/sitemap.xml")
async def sitemap(session: SessionDep) -> Response:
    entries = await PublicPieceService(session).sitemap_entries()
    return Response(seo.sitemap_xml(entries, ["/music", "/composers"]), media_type="application/xml", headers={"Cache-Control": CACHE})


@router.get("/robots.txt")
async def robots() -> Response:
    return Response(seo.robots_txt(), media_type="text/plain", headers={"Cache-Control": CACHE})
