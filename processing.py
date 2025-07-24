# processing.py

import os
import zipfile
import tempfile
import asyncio
from pathlib import Path
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Type

from pydantic import BaseModel

from config import (
    DOCUMENT_FIELDS, TEMP_DIR, SUPPORTED_FILE_EXTENSIONS, EXCEL_COLUMN_ORDER, EXTRACTION_MAX_ATTEMPTS
)
from prompts import EXTRACTION_PROMPT_TEMPLATE, CLASSIFICATION_PROMPT_TEMPLATE
from utils import log, parse_filename_for_grouping
from api_client import APIClient
from schemas import ClassificationResponse, create_extraction_model, JobStatus, FieldDetail

api_client = APIClient()

def _append_to_csv(results_list: List[Dict], output_path: Path, column_order: List[str]):
    if not results_list: return
    df = pd.DataFrame(results_list)
    for col in column_order:
        if col not in df.columns: df[col] = None
    df = df[[col for col in column_order if col in df.columns]]
    df.to_csv(output_path, mode='a', header=not output_path.exists(), index=False, encoding='utf-8')
    log.info(f"Appended {len(results_list)} row(s) to {output_path}")

def _prepare_document_files(document_files: List[Dict]) -> List[Dict]:
    return sorted(document_files, key=lambda x: x["page"])

def _group_files_by_base_name(folder_path: Path) -> Dict[str, List[Dict]]:
    doc_groups = defaultdict(list)
    for ext in SUPPORTED_FILE_EXTENSIONS:
        for doc_file in folder_path.glob(f'*{ext}'):
            base_name, page_number = parse_filename_for_grouping(doc_file.name)
            doc_groups[base_name].append({"path": doc_file, "page": page_number})
    for base_name in doc_groups: doc_groups[base_name].sort(key=lambda x: x["page"])
    return dict(doc_groups)

# REMOVED: _get_initial_summary function is no longer needed.

async def _classify_document_type(job_id: str, case_id: str, base_name: str, document_files: List[Dict], acceptable_types: List[str]):
    """Calls the LLM for a combined summary and detailed classification."""
    context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'|Task:Classification"
    sorted_docs = _prepare_document_files(document_files)
    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
        num_pages=len(sorted_docs),
        acceptable_types_str=", ".join([f"'{t}'" for t in acceptable_types])
    )
    class_result = await api_client.call_llm_with_parsing(
        prompt, sorted_docs, ClassificationResponse, context=context
    )
    return class_result.model_dump() if isinstance(class_result, ClassificationResponse) else \
           {"error": class_result.get("error", "Unknown classification failure.")}

async def _extract_data_from_document(
    job_id: str, case_id: str, base_name: str, document_files: List[Dict], classified_doc_type: str,
    fields_to_extract: List[Dict], extraction_schema: Type[BaseModel]
) -> Dict[str, Any]:
    # This function's logic remains the same.
    parent_context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'|Task:Extraction"
    # ... (rest of the function is unchanged)
    return {} # Placeholder

async def process_case_group(job_id: str, task_args: tuple):
    """Processes a single group of documents with a single classification call."""
    case_id, base_name, document_files, acceptable_types = task_args

    # --- Step 1: Combined Summary & Detailed Classification ---
    class_result = await _classify_document_type(job_id, case_id, base_name, document_files, acceptable_types)
    
    # Initialize the result row with all fields from the single classification call
    result_row = {
        "CASE_ID": case_id,
        "GROUP_Basename": base_name,
        "IMAGE_Description": class_result.get("image_description"),
        "IMAGE_Type": class_result.get("image_type"),
        "CLASSIFIED_Type": class_result.get("classified_type"),
        "CLASSIFICATION_Confidence": class_result.get("confidence"),
        "CLASSIFICATION_Reasoning": class_result.get("reasoning"),
    }
    
    # Check if the critical 'classified_type' is valid for extraction
    if "error" in class_result or result_row["CLASSIFIED_Type"] not in DOCUMENT_FIELDS:
        error_msg = class_result.get('error', 'Unsupported or Null Type')
        result_row["Processing_Status"] = f"Classification Failed: {error_msg}"
        if result_row.get("CLASSIFIED_Type") == "UNKNOWN":
             result_row["Processing_Status"] = "Classification OK: UNKNOWN"
        return result_row

    # --- Step 2: Perform Detailed Extraction ---
    classified_type = result_row["CLASSIFIED_Type"]
    fields_to_extract = DOCUMENT_FIELDS[classified_type]
    extraction_schema = create_extraction_model(classified_type, fields_to_extract)
    
    extract_result = await _extract_data_from_document(
        job_id, case_id, base_name, document_files, classified_type, fields_to_extract, extraction_schema
    )
    
    # Populate the final row with extracted data
    result_row["Processing_Status"] = extract_result.get("_extraction_status", "Extraction Failed")
    if "_overall_status" in extract_result:
        result_row["Processing_Status"] = f"Extraction Failed: {extract_result['_overall_status'].get('error')}"
    else:
        for field in fields_to_extract:
            field_name = field['name']
            field_data = extract_result.get(field_name)
            prefix = f"{classified_type}_{field_name}"
            if isinstance(field_data, dict):
                result_row[f"{prefix}_Value"] = str(field_data.get('value')) if field_data.get('value') is not None else None
                result_row[f"{prefix}_Confidence"] = field_data.get('confidence')
                result_row[f"{prefix}_Reasoning"] = field_data.get('reasoning')
            else:
                result_row[f"{prefix}_Value"] = None
                result_row[f"{prefix}_Confidence"] = 0.0
                result_row[f"{prefix}_Reasoning"] = "Field not returned by LLM."
    return result_row

async def process_zip_file_async(job_id: str, zip_file_path: str, job_statuses: Dict[str, JobStatus]):
    job = job_statuses[job_id]
    output_csv_path = Path(TEMP_DIR) / f"{job_id}_output.csv"
    if output_csv_path.exists(): output_csv_path.unlink()
    try:
        with tempfile.TemporaryDirectory(prefix="doc_proc_", dir=TEMP_DIR) as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref: zip_ref.extractall(temp_dir)
            case_folders = sorted([d for d in temp_dir.iterdir() if d.is_dir() and not d.name.startswith('__MACOSX')])
            if not case_folders and any(f for f in temp_dir.iterdir() if f.is_file() and f.suffix.lower() in SUPPORTED_FILE_EXTENSIONS):
                case_folders = [temp_dir]
            if not case_folders: raise ValueError("No case folders or processable documents found.")
            tasks_to_run = []
            acceptable_types = list(DOCUMENT_FIELDS.keys()) + ["UNKNOWN"]
            for case_folder in case_folders:
                case_id = case_folder.name if case_folder.parent.name != temp_dir.name else "root_case"
                for base_name, files in _group_files_by_base_name(case_folder).items():
                    tasks_to_run.append((case_id, base_name, files, acceptable_types))
            if not tasks_to_run: raise ValueError("No processable document groups found.")
            job.status, job.total_groups = "Processing", len(tasks_to_run)
            job.details = f"Found {job.total_groups} document groups to process."
            log.info(job.details)
            tasks = [process_case_group(job_id, args) for args in tasks_to_run]
            for future in asyncio.as_completed(tasks):
                try:
                    result = await future
                    if result: _append_to_csv([result], output_csv_path, EXCEL_COLUMN_ORDER)
                    job.groups_processed += 1
                    job.progress_percent = (job.groups_processed / job.total_groups) * 100
                    job.details = f"Processed {job.groups_processed}/{job.total_groups}: Group '{result.get('GROUP_Basename', 'N/A')}'"
                    log.info(f"Job {job_id}: {job.details}")
                except Exception as e:
                    job.groups_processed += 1
                    log.exception(f"Job {job_id}: A task failed critically: {e}")
    except Exception as e:
        log.exception(f"Job {job_id} failed: {e}")
        job.status, job.details = "Failed", str(e)
        raise
    if not output_csv_path.exists():
        pd.DataFrame([{"Status": "No data processed."}]).to_csv(output_csv_path, index=False)
    return str(output_csv_path)