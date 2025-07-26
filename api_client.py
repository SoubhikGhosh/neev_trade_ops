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
        self,
        prompt_text: str,
        document_files: List[Dict],
        response_schema: Type[BaseModel],
        context: str,
        is_correction: bool = False,
        model_override: str = None
    ) -> Union[BaseModel, Dict]:
        """
        Forces the LLM to return a specific Pydantic schema. It now manually calls the
        create method to ensure the raw response can be logged before parsing.
        """
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)

            log_message = f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s)."
            if is_correction:
                log_message += " (Correction Attempt)"
            log.info(log_message)

            start_time = time.perf_counter()
            raw_response_content = "Raw content not captured before error."

            try:
                # STEP 1: Call the standard .create method to get the raw response object.
                completion = await self._client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.0,
                    max_tokens=8192 # Keep a reasonable limit for smaller chunks
                )

                # STEP 2: Immediately get the raw string content and log it.
                raw_response_content = completion.choices[0].message.content
                log.debug(f"[{context}] RAW RESPONSE RECEIVED FROM LLM:\n---START---\n{raw_response_content}\n---END---")

                # STEP 3: Manually validate the raw string against our Pydantic schema.
                parsed_response = response_schema.model_validate_json(raw_response_content)

                duration = time.perf_counter() - start_time
                if completion.usage:
                    log.info(f"[{context}] LLM call successful. Duration: {duration:.2f}s. "
                                f"Tokens -> Prompt: {completion.usage.prompt_tokens}, "
                                f"Completion: {completion.usage.completion_tokens}, "
                                f"Total: {completion.usage.total_tokens}")
                else:
                    log.info(f"[{context}] LLM call and parsing successful. Duration: {duration:.2f}s. Usage data not available.")

                return parsed_response

            except ValidationError as e:
                # This block now catches errors from our manual .model_validate_json() call
                duration = time.perf_counter() - start_time
                log.warning(f"[{context}] Pydantic validation failed. This will trigger the correction logic. Error: {e}")
                # We return raw_response_content which we captured before the error.
                return {"error": f"Schema Validation Error: {str(e)}", "raw_response": raw_response_content}

            except (APIConnectionError, APIStatusError) as e:
                # Handle network errors separately
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] Network/API error. Duration: {duration:.2f}s: {e}")
                return {"error": f"API Error: {str(e)}", "raw_response": str(e)}

            except Exception as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] Unexpected non-recoverable error. Duration: {duration:.2f}s: {e.__class__.__name__} - {e}")
                # Return the raw content if we have it, otherwise the generic error.
                return {"error": f"Application Error: {str(e)}", "raw_response": raw_response_content}

    async def close(self):
        if self._client and not self._client.is_closed():
            await self._client.close()
            log.info("Closed OpenAI AsyncClient.")