# api_client.py

import httpx
import asyncio
import base64
import time
import re
import json
from typing import List, Dict, Type, Union

from openai import AsyncOpenAI, APIStatusError, APIConnectionError
from pydantic import BaseModel, ValidationError

from utils import log, get_mime_type
from config import (
    API_BASE_URL, API_KEY, API_MODEL, API_TIMEOUT, API_MAX_RETRIES, API_CONCURRENCY_LIMIT, EXPONENTIAL_BACKOFF_FACTOR
)

def _sanitize_llm_output(raw_response: str) -> str:
    """
    Cleans the raw string from an LLM to make it valid JSON.
    - Extracts content between the first '{' and the last '}'.
    - Removes trailing commas that cause validation errors.
    """
    if not isinstance(raw_response, str):
        return "" # Return empty string if input is not a string

    # Find the first opening brace and the last closing brace
    try:
        start_index = raw_response.find('{')
        end_index = raw_response.rfind('}')
        if start_index == -1 or end_index == -1 or start_index > end_index:
            return raw_response # Return original if no valid JSON object is found

        json_block = raw_response[start_index : end_index + 1]

        # Use regex to remove trailing commas before closing braces/brackets
        # This finds a comma, optional whitespace, and then a } or ]
        # and replaces it with just the } or ]
        cleaned_json = re.sub(r",\s*([}\]])", r"\1", json_block)
        
        return cleaned_json
    except Exception:
        return raw_response # Failsafe in case of unexpected errors

class APIClient:
    """A thread-safe, async client for the LLM API using the response_format feature."""
    def __init__(self):
        http_client = httpx.AsyncClient(http2=True, verify=False, timeout=API_TIMEOUT)
        
        self._client = AsyncOpenAI(
            api_key=API_KEY, base_url=API_BASE_URL, max_retries=0, http_client=http_client
        )
        self._semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)
        log.info(f"Initialized AsyncOpenAI client with concurrency limit of {API_CONCURRENCY_LIMIT}.")


    def _prepare_request_messages(self, prompt_text: str, document_files: List[Dict]) -> List[Dict]:
        """Prepares the 'messages' payload for the OpenAI API."""
        content_parts = [{"type": "text", "text": prompt_text}]
        for file_info in document_files:
            try:
                with open(file_info["path"], "rb") as f:
                    base64_data = base64.b64encode(f.read()).decode('utf-8')
                mime_type = get_mime_type(file_info["path"])
                content_parts.append({
                    "type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}
                })
            except Exception as e:
                log.error(f"Failed to encode file {file_info['path']}: {e}")
                continue
        return [{"role": "user", "content": content_parts}]

    async def call_llm_with_parsing(
        self, 
        prompt_text: str, 
        document_files: List[Dict], 
        response_schema: Type[BaseModel],
        context: str, 
        is_correction: bool = False, # Parameter to indicate a correction call
        model_override: str = None
    ) -> Union[BaseModel, Dict]:
        """
        Forces the LLM to return a specific Pydantic schema using the response_format parameter.
        Includes resilience with a custom retry loop for network and recoverable application errors.
        """
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)
            
            log_message = f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s) using response_format."
            if is_correction:
                log_message += " (Correction Attempt)"
            log.info(log_message)

            start_time = time.perf_counter()
            
            for attempt in range(API_MAX_RETRIES if not is_correction else 1):
                response = None
                try:
                    response = await self._client.beta.chat.completions.parse(
                        model=model_to_use,
                        messages=messages,
                        response_format=response_schema,
                        temperature=0.1, # Reduces verbosity and improves consistency
                    )
                    
                    if not (response.choices and response.choices[0].message and response.choices[0].message.parsed):
                         raise TypeError("Model response did not contain the expected parsed object.")

                    parsed_response = response.choices[0].message.parsed
                    
                    duration = time.perf_counter() - start_time

                    if response.usage:
                        log.info(f"[{context}] LLM call successful. Duration: {duration:.2f}s. "
                                 f"Tokens -> Prompt: {response.usage.prompt_tokens}, "
                                 f"Completion: {response.usage.completion_tokens}, "
                                 f"Total: {response.usage.total_tokens}")
                    else:
                         log.info(f"[{context}] LLM call and parsing successful. Duration: {duration:.2f} seconds. Usage data not available.")

                    return parsed_response

                except (APIConnectionError, APIStatusError) as e:
                    log.warning(f"[{context}] Network/API error on attempt {attempt + 1}: {e}. Retrying...")
                    if attempt == (API_MAX_RETRIES if not is_correction else 1) - 1:
                        duration = time.perf_counter() - start_time
                        log.error(f"[{context}] API call failed after all retries. Duration: {duration:.2f}s: {e}")
                        return {"error": f"API Error after retries: {str(e)}", "raw_response": str(e)}

                except ValidationError as e:
                    duration = time.perf_counter() - start_time
                    log.warning(f"[{context}] Initial Pydantic validation failed: {e}.")
                    raw_response_content = "Could not retrieve raw response."
                    if hasattr(e, 'json_data'):
                         raw_response_content = e.json_data

                    # --- Programmatic Sanitization Attempt ---
                    log.info(f"[{context}] Attempting programmatic sanitization of the failed JSON.")
                    sanitized_output = _sanitize_llm_output(raw_response_content)
                    
                    try:
                        # Retry parsing with the cleaned output
                        parsed_model = response_schema.model_validate_json(sanitized_output)
                        log.info(f"[{context}] Programmatic sanitization successful!")
                        return parsed_model
                    except (ValidationError, json.JSONDecodeError) as sanitize_error:
                        log.warning(f"[{context}] Programmatic sanitization failed: {sanitize_error}. This will trigger correction logic.")
                        # This return will trigger the self-correction logic in processing.py
                        return {"error": f"Schema Validation Error after sanitization: {str(e)}", "raw_response": raw_response_content}

                except Exception as e:
                    duration = time.perf_counter() - start_time
                    log.error(f"[{context}] Unexpected non-recoverable error. Duration: {duration:.2f}s: {e.__class__.__name__} - {e}")
                    return {"error": f"Application Error: {str(e)}"}
                
                await asyncio.sleep(EXPONENTIAL_BACKOFF_FACTOR ** attempt)
            
            return {"error": "All retry attempts failed."}

    async def close(self):
        if self._client and not self._client.is_closed():
            await self._client.close()
            log.info("Closed OpenAI AsyncClient.")