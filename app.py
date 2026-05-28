from __future__ import annotations

import re
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = BASE_DIR / "storage" / "jobs"
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"}
OUTPUT_SAMPLE_RATE = "8000"
OUTPUT_CHANNELS = "1"
OUTPUT_CODEC = "pcm_mulaw"

app = FastAPI(title="Conversor de Audio para URA")


@app.get("/api/health")
def health_check() -> dict:
    return {
        "status": "ok",
        "ffmpeg_available": shutil.which("ffmpeg") is not None,
    }


def clean_name(filename: str) -> str:
    path_name = Path(filename).name
    stem = Path(path_name).stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned or "audio"


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise HTTPException(
            status_code=500,
            detail="ffmpeg nao encontrado no servidor. Instale o ffmpeg para converter os audios.",
        )


def assert_job_path(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{36}", job_id):
        raise HTTPException(status_code=404, detail="Job nao encontrado.")

    job_dir = (JOBS_DIR / job_id).resolve()
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job nao encontrado.")

    if not str(job_dir).startswith(str(JOBS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Caminho invalido.")

    return job_dir


def convert_audio(input_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ac",
        OUTPUT_CHANNELS,
        "-ar",
        OUTPUT_SAMPLE_RATE,
        "-acodec",
        OUTPUT_CODEC,
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Falha ao converter audio.")


@app.post("/api/convert")
async def convert_files(files: list[UploadFile] = File(...)) -> dict:
    ensure_ffmpeg_available()

    if not files:
        raise HTTPException(status_code=400, detail="Envie pelo menos um arquivo de audio.")

    job_id = str(uuid.uuid4())
    job_dir = JOBS_DIR / job_id
    uploads_dir = job_dir / "uploads"
    converted_dir = job_dir / "converted"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    converted_dir.mkdir(parents=True, exist_ok=True)

    converted_files = []
    errors = []
    used_names: set[str] = set()

    for index, upload in enumerate(files, start=1):
        original_name = upload.filename or f"audio_{index}"
        extension = Path(original_name).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            errors.append(
                {
                    "original_name": original_name,
                    "error": "Formato de entrada nao suportado.",
                }
            )
            continue

        base_name = clean_name(original_name)
        output_name = f"{base_name}.wav"
        suffix = 2
        while output_name.lower() in used_names:
            output_name = f"{base_name}_{suffix}.wav"
            suffix += 1
        used_names.add(output_name.lower())

        input_path = uploads_dir / f"{uuid.uuid4()}{extension}"
        output_path = converted_dir / output_name

        with input_path.open("wb") as destination:
            shutil.copyfileobj(upload.file, destination)

        try:
            convert_audio(input_path, output_path)
        except RuntimeError as exc:
            errors.append({"original_name": original_name, "error": str(exc)})
            continue

        converted_files.append(
            {
                "original_name": original_name,
                "file_name": output_name,
                "download_url": f"/api/download/{job_id}/{output_name}",
            }
        )

    if not converted_files and errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    return {
        "job_id": job_id,
        "format": {
            "container": "WAV",
            "codec": "CCITT u-Law (pcm_mulaw)",
            "channels": "Mono",
            "sample_rate_hz": 8000,
        },
        "files": converted_files,
        "zip_url": f"/api/download/{job_id}/zip",
        "errors": errors,
    }


@app.get("/api/download/{job_id}/zip")
def download_zip(job_id: str) -> FileResponse:
    job_dir = assert_job_path(job_id)
    converted_dir = job_dir / "converted"
    output_files = sorted(converted_dir.glob("*.wav"))

    if not output_files:
        raise HTTPException(status_code=404, detail="Nenhum audio convertido encontrado.")

    zip_path = job_dir / "audios_convertidos_ura.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for output_file in output_files:
            zip_file.write(output_file, arcname=output_file.name)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="audios_convertidos_ura.zip",
    )


@app.get("/api/download/{job_id}/{file_name}")
def download_file(job_id: str, file_name: str) -> FileResponse:
    job_dir = assert_job_path(job_id)
    converted_dir = (job_dir / "converted").resolve()
    file_path = (converted_dir / Path(file_name).name).resolve()

    if not str(file_path).startswith(str(converted_dir)) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado.")

    return FileResponse(file_path, media_type="audio/wav", filename=file_path.name)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
