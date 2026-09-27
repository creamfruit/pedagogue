import shutil
from datetime import date

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.deps import CurrentUser, SessionDep
from app.services.tableau_export import ExportUnavailable, TableauExportService, build_file

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/tableau")
async def tableau_export(user: CurrentUser, session: SessionDep) -> FileResponse:
    tables = await TableauExportService(session).collect(user)
    try:
        path, workdir = await run_in_threadpool(build_file, tables)
    except ExportUnavailable as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error))
    return FileResponse(
        path,
        media_type="application/vnd.tableau.hyper",
        filename=f"piano-pedagogue-{date.today().isoformat()}.hyper",
        background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
    )
