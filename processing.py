import os
import zipfile
import tempfile
import asyncio
import re
import json
import json5
import random
import time
from pathlib import Path
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Type

from pydantic import BaseModel, ValidationError

from config import (
    DOCUMENT_FIELDS, TEMP_DIR, OUTPUT_FILENAME,
    SUPPORTED_FILE_EXTENSIONS, EXCEL_COLUMN_ORDER,
    DEFAULT_CONFIDENCE_THRESHOLD, EXTRACTION_MAX_ATTEMPTS, JSON_CORRECTION_ATTEMPTS
)
from prompts import EXTRACTION_PROMPT_TEMPLATE, CLASSIFICATION_PROMPT_TEMPLATE
from utils import log, parse_filename_for_grouping
from api_client import APIClient
from schemas import ClassificationResponse, create_extraction_model, JobStatus

api_client = APIClient()

def _append_to_csv(results_list: List[Dict], output_path: Path, column_order: List[str]):
    """Appends a list of result dictionaries to a CSV file, creating it with a header if needed."""
    if not results_list:
        return

    df = pd.DataFrame(results_list)
    
    for col in column_order:
        if col not in df.columns:
            df[col] = None
    
    final_ordered_cols = [col for col in column_order if col in df.columns]
    df = df[final_ordered_cols]

    file_exists = output_path.exists()
    df.to_csv(
        output_path,
        mode='a',
        header=not file_exists,
        index=False,
        encoding='utf-8'
    )
    log.info(f"Appended {len(results_list)} row(s) to {output_path}")

def _prepare_document_files(document_files: List[Dict]) -> List[Dict]:
    document_files.sort(key=lambda x: x["page"])
    return document_files

def _parse_llm_json_response(raw_text: str, context: str, schema: Type[BaseModel]) -> Dict:
    """Parses and validates a JSON-like response from the LLM against a Pydantic schema."""
    processed_text = raw_text.strip()
    if processed_text.startswith("```json"):
        processed_text = processed_text[7:-3].strip()
    elif processed_text.startswith("```"):
        processed_text = processed_text[3:-3].strip()

    try:
        data_dict = json5.loads(processed_text)
        validated_data = schema.model_validate(data_dict)
        return validated_data.model_dump()
    except ValidationError as e:
        log.error(f"Pydantic validation failed for {context}. Errors:\n{e.errors()}")
        return {"error": "Pydantic Validation Error", "details": e.errors(), "raw_response": processed_text}
    except Exception as e:
        log.error(f"Failed to parse or validate for {context}: {e}")
        return {"error": "Parsing/Validation Error", "details": str(e), "raw_response": processed_text}

async def _correct_json_with_llm(
    malformed_json_text: str, parsing_error: str, original_prompt: str, 
    context: str, schema: Type[BaseModel], correction_attempts_left: int
) -> Tuple[Dict, str]:
    """Calls the LLM via API to correct a malformed JSON response."""
    if correction_attempts_left <= 0:
        return {"error": "Max JSON correction attempts reached"}, ""

    log.info(f"Attempting JSON correction for {context}. Attempts left: {correction_attempts_left}")
    correction_prompt = f"""The following text was intended to be a JSON object but failed with this error:
--- ERROR ---
{parsing_error}
--- MALFORMED TEXT ---
{malformed_json_text}
--- END MALFORMED TEXT ---
Please correct the malformed text to be a perfectly valid JSON object matching the original instruction's schema. Output ONLY the raw, corrected JSON.
"""
    try:
        corrected_text = await api_client.call_llm_api(prompt_text=correction_prompt)
        parsed_data = _parse_llm_json_response(corrected_text, f"{context} (Correction Attempt)", schema)

        if "error" in parsed_data:
            return await _correct_json_with_llm(
                corrected_text, str(parsed_data.get("details")), original_prompt, 
                context, schema, correction_attempts_left - 1
            )
        return parsed_data, corrected_text
    except Exception as e:
        return {"error": f"Correction process error: {e}"}, ""

def _group_files_by_base_name(folder_path: Path) -> Dict[str, List[Dict]]:
    doc_groups = defaultdict(list)
    pattern = '|'.join([re.escape(ext) for ext in SUPPORTED_FILE_EXTENSIONS])
    
    for doc_file in folder_path.glob('*'):
        if doc_file.is_file() and re.search(f"({pattern})$", doc_file.name, re.IGNORECASE):
            base_name, page_number = parse_filename_for_grouping(doc_file.name)
            doc_groups[base_name].append({"path": doc_file, "page": page_number})

    for base_name in doc_groups:
        doc_groups[base_name].sort(key=lambda x: x["page"])
    return dict(doc_groups)

async def _classify_document_type(job_id: str, case_id: str, base_name: str, document_files: List[Dict], acceptable_types: List[str]):
    context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'(Classification)"
    log.info(f"Starting classification for {context}")
    sorted_docs = _prepare_document_files(document_files)
    prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
        num_pages=len(sorted_docs),
        acceptable_types_str="\n".join([f"- {atype}" for atype in acceptable_types])
    )
    response_text = await api_client.call_llm_api(prompt, sorted_docs)
    return _parse_llm_json_response(response_text, context, ClassificationResponse)

async def _extract_data_from_document(
    job_id: str, case_id: str, base_name: str, document_files: List[Dict], classified_doc_type: str, 
    fields_to_extract: List[Dict], extraction_schema: Type[BaseModel]
) -> Dict[str, Any]:
    context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'(Extraction)"
    log.info(f"Starting extraction for {context}")

    sorted_docs = _prepare_document_files(document_files)
    field_list_str = "\n".join([f"- **{f['name']}**: {f['description']}" for f in fields_to_extract])
    original_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        doc_type=classified_doc_type, case_id=case_id, num_pages=len(sorted_docs), field_list_str=field_list_str
    )

    best_field_extractions = {}
    current_attempt = 0
    while current_attempt < EXTRACTION_MAX_ATTEMPTS:
        log.info(f"Extraction attempt {current_attempt + 1}/{EXTRACTION_MAX_ATTEMPTS} for {context}")
        
        response_text = await api_client.call_llm_api(original_prompt, sorted_docs)
        extracted_data = _parse_llm_json_response(response_text, context, extraction_schema)

        if "error" in extracted_data:
            if "Validation Error" in extracted_data.get("error", "") or "Decode Error" in extracted_data.get("error", ""):
                corrected_data, _ = await _correct_json_with_llm(
                    extracted_data.get("raw_response", ""), str(extracted_data.get("details")), original_prompt,
                    context, extraction_schema, JSON_CORRECTION_ATTEMPTS
                )
                if "error" in corrected_data:
                    current_attempt += 1; continue
                extracted_data = corrected_data
            else:
                best_field_extractions["_overall_status"] = extracted_data; break

        all_fields_confident = True
        for field_name, field_data in extracted_data.items():
            if field_name not in [f['name'] for f in fields_to_extract]: continue
            if field_data['value'] is not None:
                if field_name not in best_field_extractions or field_data['confidence'] > best_field_extractions.get(field_name, {}).get('confidence', -1.0):
                    best_field_extractions[field_name] = field_data
            if field_data['value'] is None or field_data['confidence'] < DEFAULT_CONFIDENCE_THRESHOLD:
                all_fields_confident = False

        if all_fields_confident:
            best_field_extractions.update(extracted_data); break
        current_attempt += 1

    final_results = best_field_extractions
    if "_overall_status" in final_results: return final_results["_overall_status"]
    final_results["_extraction_status"] = "Success" if current_attempt < EXTRACTION_MAX_ATTEMPTS else "Partial Success"
    return final_results

async def process_case_group(job_id: str, task_args: tuple):
    case_id, base_name, document_files, acceptable_types = task_args
    class_result = await _classify_document_type(job_id, case_id, base_name, document_files, acceptable_types)
    
    result_row = {
        "CASE_ID": case_id,
        "GROUP_Basename": base_name,
        "CLASSIFIED_Type": class_result.get("classified_type"),
        "CLASSIFICATION_Confidence": class_result.get("confidence"),
        "CLASSIFICATION_Reasoning": class_result.get("reasoning"),
    }

    if "error" in class_result or result_row["CLASSIFIED_Type"] not in DOCUMENT_FIELDS:
        status = f"Classification Failed: {class_result.get('error', 'Unsupported Type')}"
        if result_row["CLASSIFIED_Type"] == "UNKNOWN": status = "Classified as UNKNOWN"
        result_row["Processing_Status"] = status
        return result_row
    
    classified_type = result_row["CLASSIFIED_Type"]
    fields_to_extract = DOCUMENT_FIELDS[classified_type]
    extraction_schema = create_extraction_model(classified_type, fields_to_extract)
    
    extraction_result = await _extract_data_from_document(
        job_id, case_id, base_name, document_files, classified_type, fields_to_extract, extraction_schema
    )

    if "error" in extraction_result:
        result_row["Processing_Status"] = f"Extraction Failed: {extraction_result.get('error')}"
    else:
        result_row["Processing_Status"] = extraction_result.get("_extraction_status", "Success")
        for field in fields_to_extract:
            field_name = field['name']
            field_data = extraction_result.get(field_name, {})
            prefix = f"{classified_type}_{field_name}"
            result_row[f"{prefix}_Value"] = str(field_data.get('value')) if field_data.get('value') is not None else None
            result_row[f"{prefix}_Confidence"] = field_data.get('confidence')
            result_row[f"{prefix}_Reasoning"] = field_data.get('reasoning')
    return result_row

async def process_zip_file_async(job_id: str, zip_file_path: str, job_statuses: Dict[str, JobStatus]) -> str:
    """Asynchronously processes the zip file, updating job status and appending results to CSV."""
    job = job_statuses[job_id]
    output_csv_path = Path(TEMP_DIR) / f"{job_id}_output.csv"
    
    if output_csv_path.exists():
        output_csv_path.unlink()

    with tempfile.TemporaryDirectory(prefix="doc_proc_", dir=TEMP_DIR) as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        log.info(f"Job {job_id}: Extracted '{zip_file_path}'")

        # Smartly determine the root directory containing case folders
        extracted_items = list(temp_dir.iterdir())
        processing_root = temp_dir
        if len(extracted_items) == 1 and extracted_items[0].is_dir():
            log.info(f"Detected a single root folder '{extracted_items[0].name}'. Using it as the processing root.")
            processing_root = extracted_items[0]
        else:
            log.info("Multiple items found at root. Using extraction root directly.")

        tasks = []
        acceptable_types = list(DOCUMENT_FIELDS.keys()) + ["UNKNOWN"]
        case_folders = [d for d in processing_root.iterdir() if d.is_dir()]
        
        if not case_folders:
            raise ValueError("No case folders found within the zip structure.")

        total_groups = sum(len(_group_files_by_base_name(cf)) for cf in case_folders)
        
        job.status = "Processing"
        job.total_groups = total_groups
        job.details = f"Found {total_groups} document groups to process."
        log.info(f"Job {job_id}: {job.details}")

        for case_folder in case_folders:
            case_id = case_folder.name
            doc_groups = _group_files_by_base_name(case_folder)
            for base_name, document_files in doc_groups.items():
                tasks.append(process_case_group(job_id, (case_id, base_name, document_files, acceptable_types)))
        
        if tasks:
            for future in asyncio.as_completed(tasks):
                try:
                    result_row = await future
                    if result_row:
                        _append_to_csv([result_row], output_csv_path, EXCEL_COLUMN_ORDER)
                    
                    job.groups_processed += 1
                    job.progress_percent = (job.groups_processed / job.total_groups) * 100 if job.total_groups > 0 else 0
                    job.details = f"Processed {job.groups_processed}/{job.total_groups}: Group '{result_row.get('GROUP_Basename', 'N/A')}'"
                    log.info(f"Job {job_id}: {job.details}")

                except Exception as e:
                    log.exception(f"Job {job_id}: A task failed: {e}")
                    job.groups_processed += 1
    
    if not output_csv_path.exists():
        pd.DataFrame([{"Status": "No data was processed."}]).to_csv(output_csv_path, index=False)
        
    return str(output_csv_path)