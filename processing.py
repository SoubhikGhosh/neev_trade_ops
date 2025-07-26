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
    DOCUMENT_FIELDS, TEMP_DIR, SUPPORTED_FILE_EXTENSIONS, EXCEL_COLUMN_ORDER, JSON_CORRECTION_ATTEMPTS
)
from prompts import EXTRACTION_PROMPT_TEMPLATE, CLASSIFICATION_PROMPT_TEMPLATE, CORRECTION_PROMPT_TEMPLATE
from utils import log, parse_filename_for_grouping
from api_client import APIClient
from schemas import ClassificationResponse, create_extraction_model, JobStatus

api_client = APIClient()
PROCESSING_SEMAPHORE = asyncio.Semaphore(10)

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

    if isinstance(class_result, ClassificationResponse):
        return class_result.model_dump()
    else:
        return {"error": class_result.get("error", "Unknown classification failure.")}

async def _extract_data_from_document(
    job_id: str, case_id: str, base_name: str, document_files: List[Dict], classified_doc_type: str
) -> Dict[str, Any]:
    """
    Extracts data by iterating through logical field groups, with a self-correction retry
    loop implemented for each individual group.
    """
    context_prefix = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'|Task:Extraction"
    sorted_docs = _prepare_document_files(document_files)

    field_groups = DOCUMENT_FIELDS.get(classified_doc_type)
    if not isinstance(field_groups, dict):
        return {"_error": f"Field groups for doc type '{classified_doc_type}' are not defined in config."}

    final_extraction_results = {}

    for group_name, fields_to_extract in field_groups.items():
        group_context = f"{context_prefix}({group_name})"
        log.info(f"[{group_context}] Starting extraction for field group.")

        field_list_str = "\n".join([f"- {f['name']}: {f['description']}" for f in fields_to_extract])
        extraction_schema = create_extraction_model(f"{classified_doc_type}{group_name}", fields_to_extract)

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            doc_type=classified_doc_type, case_id=case_id, num_pages=len(sorted_docs), field_list_str=field_list_str
        )

        # Initial API call for the current group
        response_data = await api_client.call_llm_with_parsing(
            prompt, sorted_docs, extraction_schema, group_context
        )

        # If the initial attempt fails, start the self-correction loop for this group
        if not isinstance(response_data, BaseModel):
            log.warning(f"[{group_context}] Initial extraction for group failed. Starting self-correction attempts...")
            last_error_info = response_data
            correction_successful = False

            for i in range(JSON_CORRECTION_ATTEMPTS):
                correction_context = f"{group_context}|CorrectionAttempt:{i+1}"
                log.info(f"[{correction_context}] Running correction loop.")

                failed_output = last_error_info.get("raw_response", "No raw output from previous attempt.")

                correction_prompt = CORRECTION_PROMPT_TEMPLATE.format(
                    doc_type=classified_doc_type,
                    case_id=case_id,
                    failed_output=failed_output,
                    field_list_str=field_list_str
                )

                corrected_response = await api_client.call_llm_with_parsing(
                    correction_prompt, sorted_docs, extraction_schema, correction_context, is_correction=True
                )

                if isinstance(corrected_response, BaseModel):
                    log.info(f"[{correction_context}] Self-correction successful for group.")
                    response_data = corrected_response
                    correction_successful = True
                    break  # Exit the correction loop on success

                last_error_info = corrected_response

            if not correction_successful:
                error_msg = f"Extraction failed on group '{group_name}' after all retries. Final error: {last_error_info.get('error')}"
                log.error(f"[{group_context}] {error_msg}")
                return {"_error": error_msg}

        # Update final results from either the initial success or the corrected success
        final_extraction_results.update(response_data.model_dump())
        log.info(f"[{group_context}] Successfully processed field group.")

    return final_extraction_results


async def process_case_group(job_id: str, task_args: tuple):
    async with PROCESSING_SEMAPHORE:
        case_id, base_name, document_files, acceptable_types = task_args

        class_result = await _classify_document_type(job_id, case_id, base_name, document_files, acceptable_types)
        result_row = {
            "CASE_ID": case_id, "GROUP_Basename": base_name,
            "CLASSIFIED_Type": class_result.get("classified_type"),
            "CLASSIFICATION_Confidence": class_result.get("confidence"),
            "CLASSIFICATION_Reasoning": class_result.get("reasoning"),
        }

        if "error" in class_result or result_row["CLASSIFIED_Type"] not in DOCUMENT_FIELDS:
            error_msg = class_result.get('error', f"Unsupported or Null Type: {result_row['CLASSIFIED_Type']}")
            result_row["Processing_Status"] = f"Classification Failed: {error_msg}"
            if result_row.get("CLASSIFIED_Type") == "UNKNOWN":
                 result_row["Processing_Status"] = "Classification OK: UNKNOWN"
            return result_row

        classified_type = result_row["CLASSIFIED_Type"]

        extract_result = await _extract_data_from_document(
            job_id, case_id, base_name, document_files, classified_type
        )

        if "_error" in extract_result:
            result_row["Processing_Status"] = f"Extraction Failed: {extract_result['_error']}"
        else:
            result_row["Processing_Status"] = "Success"
            # We must iterate through the original config to find all possible fields
            all_fields_for_type = [field for group in DOCUMENT_FIELDS[classified_type].values() for field in group]
            for field in all_fields_for_type:
                original_field_name = field['name']
                # Sanitize the name to match the keys in the Pydantic model dump
                sanitized_base_name = ''.join(c if c.isalnum() else '_' for c in original_field_name)

                # Populate the final result row from the combined extraction dictionary
                result_row[f"{classified_type}_{original_field_name}_Value"] = extract_result.get(f"{sanitized_base_name}_Value")
                result_row[f"{classified_type}_{original_field_name}_Confidence"] = extract_result.get(f"{sanitized_base_name}_Confidence")
                result_row[f"{classified_type}_{original_field_name}_Reasoning"] = extract_result.get(f"{sanitized_base_name}_Reasoning")

        return result_row


async def process_zip_file_async(job_id: str, zip_file_path: str, job_statuses: Dict[str, JobStatus]):
    job = job_statuses[job_id]
    output_csv_path = Path(TEMP_DIR) / f"{job_id}_output.csv"
    if output_csv_path.exists(): output_csv_path.unlink()
    try:
        with tempfile.TemporaryDirectory(prefix="doc_proc_", dir=TEMP_DIR) as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            with zipfile.ZipFile(zip_file_path, 'r') as zip_ref: zip_ref.extractall(temp_dir)
            log.info(f"Job {job_id}: Extracted archive and searching for documents recursively.")
            all_supported_files = [p for p in temp_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_FILE_EXTENSIONS and '__MACOSX' not in str(p)]
            if not all_supported_files: raise ValueError("No processable document files found in the zip.")
            case_folders = defaultdict(list)
            for file_path in all_supported_files: case_folders[file_path.parent].append(file_path)
            log.info(f"Job {job_id}: Found {len(case_folders)} case folder(s) containing documents.")
            tasks_to_run = []
            acceptable_types = list(DOCUMENT_FIELDS.keys()) + ["UNKNOWN"]
            for case_path in case_folders.keys():
                case_id = case_path.name
                for base_name, files in _group_files_by_base_name(case_path).items():
                    tasks_to_run.append((case_id, base_name, files, acceptable_types))
            if not tasks_to_run: raise ValueError("No processable document groups could be formed.")
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
                    log.info(f"Job {job_id}: {job.details} - Progress: {job.progress_percent:.2f}%")
                except Exception as e:
                    job.groups_processed += 1
                    job.progress_percent = (job.groups_processed / job.total_groups) * 100
                    log.exception(f"Job {job_id}: A processing task failed critically: {e}. Progress: {job.progress_percent:.2f}%")

    except Exception as e:
        log.exception(f"Job {job_id} failed: {e}")
        job.status, job.details = "Failed", str(e)
        raise
    if not output_csv_path.exists():
        pd.DataFrame([{"Status": "No data processed."}]).to_csv(output_csv_path, index=False)
    return str(output_csv_path)