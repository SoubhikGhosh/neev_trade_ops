import os
import zipfile
import tempfile
import asyncio
import re
import json
import json5
from pathlib import Path
import pandas as pd
from collections import defaultdict
from typing import Dict, List, Tuple, Any, Type

from pydantic import BaseModel, ValidationError

from config import (
    DOCUMENT_FIELDS, TEMP_DIR,
    SUPPORTED_FILE_EXTENSIONS, EXCEL_COLUMN_ORDER, JSON_CORRECTION_ATTEMPTS
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

def _parse_llm_json_response(raw_text: str, context: str, schema: Type[BaseModel], expected_field_names: List[str]) -> Dict:
    """Parses and validates a JSON-like response, normalizing keys before validation."""
    processed_text = raw_text.strip()
    if processed_text.startswith("```json"):
        processed_text = processed_text[7:-3].strip()
    elif processed_text.startswith("```"):
        processed_text = processed_text[3:-3].strip()

    try:
        data_dict = json5.loads(processed_text)

        def sanitize_key(key: str) -> str:
            """Converts a key to a sanitized 'fingerprint'."""
            s = re.sub(r'[^a-zA-Z0-9]+', '_', key)
            return s.strip('_').upper()

        sanitized_key_map = {sanitize_key(name): name for name in expected_field_names}

        normalized_dict = {}
        for llm_key, value in data_dict.items():
            sanitized_llm_key = sanitize_key(llm_key)
            original_key = sanitized_key_map.get(sanitized_llm_key, llm_key)
            normalized_dict[original_key] = value

        validated_data = schema.model_validate(normalized_dict)
        return validated_data.model_dump()
        
    except ValidationError as e:
        log.error(f"Pydantic validation failed for {context}. Errors:\n{e.errors()}")
        return {"error": "Pydantic Validation Error", "details": e.errors(), "raw_response": processed_text}
    except Exception as e:
        log.error(f"Failed to parse or validate for {context}: {e}")
        return {"error": "Parsing/Validation Error", "details": str(e), "raw_response": processed_text}


async def _correct_json_with_llm(
    malformed_json_text: str, parsing_error: str, original_prompt: str, 
    context: str, schema: Type[BaseModel], correction_attempts_left: int, expected_field_names: List[str]
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
        parsed_data = _parse_llm_json_response(corrected_text, f"{context} (Correction Attempt)", schema, expected_field_names)

        if "error" in parsed_data:
            return await _correct_json_with_llm(
                corrected_text, str(parsed_data.get("details")), original_prompt, 
                context, schema, correction_attempts_left - 1, expected_field_names
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
    classification_fields = ["classified_type", "confidence", "reasoning"]
    return _parse_llm_json_response(response_text, context, ClassificationResponse, classification_fields)

async def _extract_data_from_document(
    job_id: str, case_id: str, base_name: str, document_files: List[Dict], classified_doc_type: str, 
    fields_to_extract: List[Dict], extraction_schema: Type[BaseModel]
) -> Dict[str, Any]:
    """
    Performs an extraction with an intelligent, targeted re-ask for missing fields.
    """
    context = f"Job:{job_id}|Case:{case_id}|Group:'{base_name}'(Extraction)"
    log.info(f"Starting initial extraction attempt for {context}")

    sorted_docs = _prepare_document_files(document_files)
    initial_field_list_str = "\n".join([f"- **{f['name']}**: {f['description']}" for f in fields_to_extract])
    initial_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        doc_type=classified_doc_type, case_id=case_id, num_pages=len(sorted_docs), field_list_str=initial_field_list_str
    )
    
    expected_field_names = [f['name'] for f in fields_to_extract]

    # --- Step 1: Initial Extraction Attempt ---
    response_text = await api_client.call_llm_api(initial_prompt, sorted_docs)
    extraction_result = _parse_llm_json_response(response_text, context, extraction_schema, expected_field_names)

    if "error" in extraction_result:
        if "Validation Error" in extraction_result.get("error", "") or "Decode Error" in extraction_result.get("error", ""):
            log.warning(f"Initial parsing/validation failed for {context}. Attempting LLM-based correction.")
            corrected_data, _ = await _correct_json_with_llm(
                extraction_result.get("raw_response", ""), str(extraction_result.get("details")), initial_prompt,
                context, extraction_schema, JSON_CORRECTION_ATTEMPTS, expected_field_names
            )
            extraction_result = corrected_data
        
        if "error" in extraction_result:
             log.error(f"Initial extraction for {context} failed after parsing/correction. Error: {extraction_result.get('error')}")
             return {"_overall_status": extraction_result}

    # --- Step 2: Identify Missing Fields ---
    missing_fields = []
    for field_name, value in extraction_result.items():
        if value is None and field_name in expected_field_names:
            missing_fields.append(field_name)

    # --- Step 3: Targeted Re-Ask (if necessary) ---
    if missing_fields:
        log.warning(f"{len(missing_fields)} fields were missing for {context}. Performing a targeted re-ask.")
        
        missing_fields_definitions = [f for f in fields_to_extract if f['name'] in missing_fields]
        reask_field_list_str = "\n".join([f"- **{f['name']}**: {f['description']}" for f in missing_fields_definitions])
        
        reask_prompt = f"""
        You are an AI assistant helping to complete a data extraction task.
        In a previous step for Case ID '{case_id}', the following fields were missed or not found in the provided document.
        Please re-examine the document pages ({len(sorted_docs)} pages) and extract ONLY the following fields.
        It is critical that you return a value for every field listed below, even if it is null.

        **Fields to Extract:**
        {reask_field_list_str}

        **Output Requirements (Strict):**
        - Return ONLY a single, valid JSON object.
        - The JSON object must have keys that correspond EXACTLY to the field names listed above.
        - Each value must be an object with "value", "confidence", and "reasoning".
        """
        
        reask_response_text = await api_client.call_llm_api(reask_prompt, sorted_docs)
        reask_result = _parse_llm_json_response(reask_response_text, f"{context} (Re-ask)", extraction_schema, missing_fields)

        if "error" not in reask_result:
            log.info(f"Successfully merged results from targeted re-ask for {context}.")
            for field_name, value in reask_result.items():
                if value is not None:
                    extraction_result[field_name] = value
        else:
            log.error(f"Targeted re-ask for {context} also failed. Proceeding with incomplete data.")

    extraction_result["_extraction_status"] = "Success" if not missing_fields else "Partial Success (After Re-ask)"
    return extraction_result


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

    if "_overall_status" in extraction_result and extraction_result["_overall_status"].get("error"):
        result_row["Processing_Status"] = f"Extraction Failed: {extraction_result['_overall_status'].get('error')}"
    else:
        result_row["Processing_Status"] = extraction_result.get("_extraction_status", "Success")
        for field in fields_to_extract:
            field_name = field['name']
            field_data = extraction_result.get(field_name)
            prefix = f"{classified_type}_{field_name}"
            if field_data:
                result_row[f"{prefix}_Value"] = str(field_data.get('value')) if field_data.get('value') is not None else None
                result_row[f"{prefix}_Confidence"] = field_data.get('confidence')
                result_row[f"{prefix}_Reasoning"] = field_data.get('reasoning')
            else:
                result_row[f"{prefix}_Value"] = None
                result_row[f"{prefix}_Confidence"] = 0.0
                result_row[f"{prefix}_Reasoning"] = "Field was not returned by the LLM."
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

        log.info(f"Job {job_id}: Recursively searching for case folders...")
        
        all_doc_files = []
        for ext in SUPPORTED_FILE_EXTENSIONS:
            all_doc_files.extend(temp_dir.rglob(f"*{ext.lower()}"))
            all_doc_files.extend(temp_dir.rglob(f"*{ext.upper()}"))

        valid_doc_files = [f for f in all_doc_files if '__MACOSX' not in str(f.parent)]
        case_folders = sorted(list(set(f.parent for f in valid_doc_files)))
        
        if not case_folders:
            raise ValueError("No case folders with processable documents (.pdf, .jpg, etc.) found in the zip file.")

        log.info(f"Job {job_id}: Found {len(case_folders)} case folder(s): {[cf.name for cf in case_folders]}")

        tasks = []
        acceptable_types = list(DOCUMENT_FIELDS.keys()) + ["UNKNOWN"]
        
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