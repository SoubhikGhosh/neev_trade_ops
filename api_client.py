# api_client.py

import httpx
import asyncio
import base64
import time
from typing import List, Dict, Type, Union

from openai import AsyncOpenAI, APIStatusError, APIConnectionError
from pydantic import BaseModel, ValidationError

from utils import log, get_mime_type
from config import (
    API_BASE_URL, API_KEY, API_MODEL, API_TIMEOUT, API_MAX_RETRIES, API_CONCURRENCY_LIMIT, EXPONENTIAL_BACKOFF_FACTOR
)

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
        self, prompt_text: str, document_files: List[Dict], response_schema: Type[BaseModel],
        context: str, model_override: str = None
    ) -> Union[BaseModel, Dict]:
        """
        Forces the LLM to return a specific Pydantic schema using the response_format parameter.
        Includes resilience with a custom retry loop for network and recoverable application errors.
        """
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)
            
            log.info(f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s) using response_format.")
            start_time = time.perf_counter()
            
            for attempt in range(API_MAX_RETRIES):
                response = None
                try:
                    response = await self._client.beta.chat.completions.parse(
                        model=model_to_use,
                        messages=messages,
                        response_format=response_schema,
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
                    log.warning(f"[{context}] Network/API error on attempt {attempt + 1}/{API_MAX_RETRIES}: {e}. Retrying...")
                    if attempt == API_MAX_RETRIES - 1:
                        duration = time.perf_counter() - start_time
                        log.error(f"[{context}] API call failed after all retries. Duration: {duration:.2f}s: {e}")
                        return {"error": f"API Error after retries: {str(e)}", "raw_response": str(e)}

                except (ValidationError, IndexError, KeyError, TypeError) as e:
                    log.warning(f"[{context}] Recoverable parsing/validation error on attempt {attempt + 1}/{API_MAX_RETRIES}: {e}. Retrying...")
                    if attempt == API_MAX_RETRIES - 1:
                        duration = time.perf_counter() - start_time
                        log.error(f"[{context}] Final attempt failed with validation error. Duration: {duration:.2f}s: {e}")
                        raw_response_content = "Response was empty or did not contain valid content."
                        if response and response.choices and response.choices[0].message:
                           raw_response_content = response.choices[0].message.content
                        return {"error": f"Schema Validation Error: {str(e)}", "raw_response": raw_response_content}
                
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