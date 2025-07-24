# main.py

import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse

from utils import log, setup_logger
from processing import process_zip_file_async
from config import TEMP_DIR
from schemas import JobStatus

# This in-memory store is suitable for a single-process server.
# For scaling to multiple workers, a shared store like Redis would be required.
job_statuses: dict[str, JobStatus] = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    from processing import api_client
    os.makedirs(TEMP_DIR, exist_ok=True)
    setup_logger()
    log.info("Application startup: Initializing API client...")
    await api_client._get_client()
    yield
    log.info("Application shutdown: Closing API client...")
    await api_client.close()

app = FastAPI(
    title="Document Processing Service",
    version="5.0.0-Progress",
    lifespan=lifespan
)

def cleanup_file(file_path: str):
    """Background task to delete a temporary file."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            log.info(f"Cleaned up temporary file: {file_path}")
    except OSError as e:
        log.error(f"Error cleaning up file {file_path}: {e}")

async def run_processing_job(job_id: str, temp_zip_path: str):
    """A wrapper function to run the processing logic and update job status."""
    try:
        output_csv_path = await process_zip_file_async(job_id, temp_zip_path, job_statuses)
        job_statuses[job_id].status = "Completed"
        job_statuses[job_id].details = "Processing finished successfully."
        job_statuses[job_id].progress_percent = 100.0
        job_statuses[job_id].result_path = output_csv_path
        log.info(f"Job {job_id} completed. Output at {output_csv_path}")
    except Exception as e:
        log.exception(f"Job {job_id} failed with an error.")
        job_statuses[job_id].status = "Failed"
        job_statuses[job_id].details = f"An error occurred: {str(e)}"
    finally:
        cleanup_file(temp_zip_path)

@app.post("/process-zip/", status_code=status.HTTP_202_ACCEPTED)
async def create_upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Accepts a ZIP file, starts a background processing job, and returns a job ID."""
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a ZIP file.")

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=TEMP_DIR) as temp_zip:
            shutil.copyfileobj(file.file, temp_zip)
            temp_zip_path = temp_zip.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not save file: {e}")
    finally:
        await file.close()

    job_id = str(uuid.uuid4())
    job_statuses[job_id] = JobStatus(
        job_id=job_id,
        status="Queued",
        details="Job has been queued for processing."
    )
    
    background_tasks.add_task(run_processing_job, job_id, temp_zip_path)

    log.info(f"Job {job_id} started for file {file.filename}.")
    return {"message": "Job started successfully.", "job_id": job_id}

@app.get("/status/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Retrieves the status of a processing job by its ID."""
    job = job_statuses.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job ID not found.")
    return job

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Document Processing API",
        "version": "5.0.0-Progress",
        "process_endpoint": "/process-zip/",
        "status_endpoint": "/status/{job_id}"
    }