"""HTTP app: GET / (UI), GET /health, POST /api/parse."""

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import guard, report

PARSE_TIMEOUT = float(os.environ.get("PARSE_TIMEOUT", "10"))
CONCURRENCY = asyncio.Semaphore(int(os.environ.get("PARSE_CONCURRENCY", "2")))
STATIC = Path(__file__).parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # it logs every URL it checks
log = logging.getLogger("ats_parser")
app = FastAPI(title="ats-parser", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/parse")
async def parse(file: UploadFile = File(...), check_links: bool = Form(False)):
    data = await file.read(guard.MAX_BYTES + 1)
    await file.close()
    async with CONCURRENCY:
        try:
            result = await asyncio.wait_for(run_in_threadpool(report.build, data), PARSE_TIMEOUT)
            if check_links:
                result = await asyncio.wait_for(report.add_liveness(result), PARSE_TIMEOUT)
        except guard.RejectedUpload as e:
            raise HTTPException(400, str(e))
        except asyncio.TimeoutError:
            raise HTTPException(504, "Parsing took too long. Is the PDF unusually complex?")
        except Exception as e:
            # Never log the document; the error type is enough to debug.
            log.error("parse failed: %s", type(e).__name__)
            raise HTTPException(500, "Something went wrong while parsing this PDF.")
    log.info("parsed pages=%s score=%s issues=%s", result["meta"]["pages"], result["score"],
             ",".join(sorted({i["code"] for i in result["issues"]})) or "-")
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
