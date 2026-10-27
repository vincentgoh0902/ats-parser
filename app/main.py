"""HTTP app: GET / (UI), GET /health, POST /api/parse, POST /api/check, POST /api/render."""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, ValidationError
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import guard, report
from app.edit import check as edit_check
from app.edit import model as edit_model
from app.edit import render as edit_render
from app.match import matcher

PARSE_TIMEOUT = float(os.environ.get("PARSE_TIMEOUT", "10"))
CONCURRENCY = asyncio.Semaphore(int(os.environ.get("PARSE_CONCURRENCY", "2")))
STATIC = Path(__file__).parent / "static"
MAX_EDIT_BYTES = 100_000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every URL it checks
log = logging.getLogger("ats_parser")
app = FastAPI(title="ats-parser", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def revalidate_assets(request, call_next):
    """Browsers must re-check the page and its scripts on every load (a cheap
    304 when unchanged), so an old app.js is never paired with a new editor.js."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/parse")
async def parse(file: UploadFile = File(...), check_links: bool = Form(False),
                job_description: str = Form("", max_length=20_000)):
    data = await file.read(guard.MAX_BYTES + 1)
    await file.close()
    async with CONCURRENCY:
        try:
            result = await asyncio.wait_for(run_in_threadpool(report.build, data), PARSE_TIMEOUT)
            if check_links:
                result = await asyncio.wait_for(report.add_liveness(result), PARSE_TIMEOUT)
            if job_description.strip():
                result["match"] = await run_in_threadpool(matcher.match, job_description, result)
            # The editor starts from what the parser read.
            result["resume"] = edit_model.from_fields(result["fields"]).model_dump()
        except guard.RejectedUpload as e:
            raise HTTPException(400, str(e))
        except asyncio.TimeoutError:
            raise HTTPException(504, "Parsing took too long. Is the PDF unusually complex?")
        except Exception as e:
            # Never log the document; the error type is enough to debug.
            log.error("parse failed: %s", type(e).__name__)
            raise HTTPException(500, "Something went wrong while parsing this PDF.")
    log.info("parsed pages=%s score=%s match=%s issues=%s", result["meta"]["pages"], result["score"],
             result.get("match", {}).get("score", "-"),
             ",".join(sorted({i["code"] for i in result["issues"]})) or "-")
    return result


class CheckRequest(BaseModel):
    resume: edit_model.Resume
    job_description: str = Field("", max_length=20_000)


async def _json_body(request: Request, schema):
    """Read at most MAX_EDIT_BYTES before parsing, whatever Content-Length claims."""
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_EDIT_BYTES:
            raise HTTPException(413, "That resume is too long to render.")
    try:
        return schema.model_validate_json(body)
    except ValidationError as e:
        first = e.errors()[0]
        where = ".".join(str(x) for x in first["loc"])
        raise HTTPException(422, f"{where}: {first['msg']}")


async def _run(fn, *args):
    async with CONCURRENCY:
        try:
            return await asyncio.wait_for(run_in_threadpool(fn, *args), PARSE_TIMEOUT)
        except asyncio.TimeoutError:
            raise HTTPException(504, "Rendering took too long.")
        except Exception as e:
            log.error("edit failed: %s", type(e).__name__)
            raise HTTPException(500, "Something went wrong while rendering this resume.")


@app.post("/api/check")
async def check(request: Request):
    """Render the edited resume, read it back like an ATS, and match it to the job."""
    req = await _json_body(request, CheckRequest)
    result = await _run(edit_check.check, req.resume, req.job_description)
    log.info("checked pages=%s mismatches=%s match=%s", result["pages"], len(result["mismatches"]),
             (result["match"] or {}).get("score", "-"))
    return result


@app.post("/api/render")
async def render(request: Request):
    resume = await _json_body(request, edit_model.Resume)
    pdf = await _run(edit_render.render, resume)
    log.info("rendered bytes=%s", len(pdf))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="resume.pdf"',
                             "Cache-Control": "no-store"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
