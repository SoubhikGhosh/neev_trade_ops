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
    API_BASE_URL, API_KEY, API_MODEL, API_TIMEOUT, API_MAX_RETRIES, API_CONCURRENCY_LIMIT
)

class APIClient:
    """A thread-safe, async client for interacting with the LLM API using the openai library."""
    def __init__(self):
        http_client = httpx.AsyncClient(http2=True, verify=False, timeout=API_TIMEOUT)
        self._client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=API_BASE_URL,
            max_retries=API_MAX_RETRIES,
            http_client=http_client
        )
        self._semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)
        log.info("Initialized AsyncOpenAI client.")

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
        """Makes a call to the LLM API in JSON Mode and parses the response into a Pydantic model."""
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)
            log.info(f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s).")
            start_time = time.perf_counter()
            try:
                response = await self._client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                
                duration = time.perf_counter() - start_time
                json_string = response.choices[0].message.content
                
                parsed_response = response_schema.model_validate_json(json_string)
                
                log.info(f"[{context}] LLM call and parsing successful. Duration: {duration:.2f} seconds.")
                return parsed_response

            except ValidationError as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] Pydantic validation failed after {duration:.2f}s on LLM response. Error: {e}")
                return {"error": f"Pydantic Validation Error: {str(e)}", "raw_response": json_string}
            except (APIStatusError, APIConnectionError) as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] API call failed after {duration:.2f}s: {e}")
                return {"error": f"API Error: {str(e)}"}
            except Exception as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] Unexpected error after {duration:.2f}s: {e}")
                return {"error": f"Application Error: {str(e)}"}

    async def close(self):
        if self._client and not self._client.is_closed():
            await self._client.close()
            log.info("Closed OpenAI AsyncClient.")