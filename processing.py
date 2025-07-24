# processing.py

import os
import zipfile
import tempfile
import asyncio
from pathlib import Path
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Any, Type

from pydantic import BaseModel

from config import (
    DOCUMENT_FIELDS, TEMP_DIR, SUPPORTED_FILE_EXTENSIONS, EXCEL_COLUMN_ORDER, EXTRACTION_MAX_ATTEMPTS
)
from prompts import EXTRACTION_PROMPT_TEMPLATE, CLASSIFICATION_PROMPT_TEMPLATE
from utils import log, parse_filename_for_grouping
from api_client import APIClient
from schemas import ClassificationResponse, create_extraction_model, JobStatus

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
        # This glob is intentionally not recursive, as it operates on a specific case folder.
        for doc_file in folder_path.glob(f'*{ext}'):
            base_name, page_number = parse_filename_for_grouping(doc_file.name)
            doc_groups[base_name].append({"path": doc_file, "page": page_number})
    for base_name in doc_groups: doc_groups[base_name].sort(key=lambda x: x["page"])
    return dict(doc_groups)


async def _classify_document_type(job_id: str, case_id: str, base_name: str, document_files: List[Dict], acceptable_types: List[str]):
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
    parent_context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'|Task:Extraction"
    sorted_docs = _prepare_document_files(document_files)
    extraction_result = {}
    fields_for_attempt = fields_to_extract
    for attempt in range(EXTRACTION_MAX_ATTEMPTS):
        if not fields_for_attempt: break
        field_list_str = "\n".join([f"- **{f['name']}**: {f['description']}" for f in fields_for_attempt])
        if attempt == 0:
            prompt = EXTRACTION_PROMPT_TEMPLATE.format(
                doc_type=classified_doc_type, case_id=case_id, num_pages=len(sorted_docs), field_list_str=field_list_str
            )
            schema_for_attempt = extraction_schema
            context = f"{parent_context}|Attempt:Initial"
        else:
            prompt = f"RE-ASK: For Case ID '{case_id}', re-examine the document to find the following missed fields:\n{field_list_str}"
            schema_for_attempt = create_extraction_model(f"{classified_doc_type}Reask", fields_for_attempt)
            context = f"{parent_context}|Attempt:Re-ask"
        response_data = await api_client.call_llm_with_parsing(
            prompt, sorted_docs, schema_for_attempt, context=context
        )
        if isinstance(response_data, BaseModel):
            extraction_result.update(response_data.model_dump(exclude_none=True))
        else:
            log.error(f"[{context}] Extraction attempt failed: {response_data['error']}")
            return {"_overall_status": {"error": response_data['error']}}
        missing_fields = [f['name'] for f in fields_to_extract if not extraction_result.get(f['name']) or extraction_result[f['name']].get('value') is None]
        if not missing_fields: break
        fields_for_attempt = [f for f in fields_to_extract if f['name'] in missing_fields]
    extraction_result["_extraction_status"] = "Success" if not missing_fields else "Partial Success"
    return extraction_result

async def process_case_group(job_id: str, task_args: tuple):
    case_id, base_name, document_files, acceptable_types = task_args
    class_result = await _classify_document_type(job_id, case_id, base_name, document_files, acceptable_types)
    result_row = {
        "CASE_ID": case_id, "GROUP_Basename": base_name,
        "IMAGE_Description": class_result.get("image_description"), "IMAGE_Type": class_result.get("image_type"),
        "CLASSIFIED_Type": class_result.get("classified_type"), "CLASSIFICATION_Confidence": class_result.get("confidence"),
        "CLASSIFICATION_Reasoning": class_result.get("reasoning"),
    }
    if "error" in class_result or result_row["CLASSIFIED_Type"] not in DOCUMENT_FIELDS:
        result_row["Processing_Status"] = f"Classification Failed: {class_result.get('error', 'Unsupported Type')}"
        if result_row.get("CLASSIFIED_Type") == "UNKNOWN": result_row["Processing_Status"] = "Classification OK: UNKNOWN"
        return result_row
    classified_type = result_row["CLASSIFIED_Type"]
    fields = DOCUMENT_FIELDS[classified_type]
    schema = create_extraction_model(classified_type, fields)
    extract_result = await _extract_data_from_document(
        job_id, case_id, base_name, document_files, classified_type, fields, schema
    )
    result_row["Processing_Status"] = extract_result.get("_extraction_status", "Extraction Failed")
    if "_overall_status" in extract_result:
        result_row["Processing_Status"] = f"Extraction Failed: {extract_result['_overall_status'].get('error')}"
    else:
        for field in fields:
            field_name, data = field['name'], extract_result.get(field['name'])
            prefix = f"{classified_type}_{field_name}"
            if isinstance(data, dict):
                result_row[f"{prefix}_Value"] = str(data.get('value')) if data.get('value') is not None else None
                result_row[f"{prefix}_Confidence"], result_row[f"{prefix}_Reasoning"] = data.get('confidence'), data.get('reasoning')
            else:
                result_row[f"{prefix}_Value"], result_row[f"{prefix}_Confidence"], result_row[f"{prefix}_Reasoning"] = None, 0.0, "Field not returned."
    return result_row

async def process_zip_file_async(job_id: str, zip_file_path: str, job_statuses: Dict[str, JobStatus]):
    """Recursively finds and processes document groups within the extracted zip."""
    job = job_statuses[job_id]
    output_csv_path = Path(TEMP_DIR) / f"{job_id}_output.csv"
    if output_csv_path.exists(): output_csv_path.unlink()
    
    try:
        with tempfile.TemporaryDirectory(prefix="doc_proc_", dir=TEMP_DIR) as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            log.info(f"Job {job_id}: Extracted archive and searching for documents recursively.")

            # --- NEW RECURSIVE DISCOVERY LOGIC ---
            # 1. Find all files recursively and filter them
            all_supported_files = [
                p for p in temp_dir.rglob("*")
                if p.is_file() and
                   p.suffix.lower() in SUPPORTED_FILE_EXTENSIONS and
                   '__MACOSX' not in str(p)
            ]

            if not all_supported_files:
                raise ValueError("No processable document files (.pdf, .png, etc.) found in the zip.")

            # 2. Group files by their parent directory (which is the case folder)
            case_folders = defaultdict(list)
            for file_path in all_supported_files:
                case_folders[file_path.parent].append(file_path)

            log.info(f"Job {job_id}: Found {len(case_folders)} case folder(s) containing documents.")

            # 3. Build the final list of tasks to run
            tasks_to_run = []
            acceptable_types = list(DOCUMENT_FIELDS.keys()) + ["UNKNOWN"]
            for case_path in case_folders.keys():
                case_id = case_path.name
                doc_groups = _group_files_by_base_name(case_path)
                for base_name, files in doc_groups.items():
                    tasks_to_run.append((case_id, base_name, files, acceptable_types))
            # --- END NEW LOGIC ---

            if not tasks_to_run:
                raise ValueError("No processable document groups could be formed.")

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
                    log.exception(f"Job {job_id}: A processing task failed critically: {e}")

    except Exception as e:
        log.exception(f"Job {job_id} failed: {e}")
        job.status, job.details = "Failed", str(e)
        raise
        
    if not output_csv_path.exists():
        pd.DataFrame([{"Status": "No data processed."}]).to_csv(output_csv_path, index=False)
    return str(output_csv_path)