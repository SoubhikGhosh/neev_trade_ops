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

def _pydantic_to_tool_definition(model: Type[BaseModel]) -> Dict:
    """Converts a Pydantic model into a JSON Schema dictionary for OpenAI tool calling."""
    return {
        "type": "function",
        "function": {
            "name": model.__name__,
            "description": model.__doc__ or f"Extract data using the {model.__name__} schema.",
            "parameters": model.model_json_schema()
        }
    }

class APIClient:
    """A thread-safe, async client for the LLM API using the official Tool Calling feature."""
    def __init__(self):
        # CRITICAL FIX: Removed `verify=False`. SSL verification is now ENABLED by default for security.
        # If connecting to a service with a self-signed certificate, use:
        # http_client = httpx.AsyncClient(verify='/path/to/your/ca.pem', ...)
        # The openai library's built-in retries will handle 429, 5xx, and connection errors automatically.
        http_client = httpx.AsyncClient(http2=True, timeout=API_TIMEOUT)
        
        self._client = AsyncOpenAI(
            api_key=API_KEY, base_url=API_BASE_URL, max_retries=API_MAX_RETRIES, http_client=http_client
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
        Forces the LLM to return a specific Pydantic schema using Tool Calling.
        Includes resilience for network issues and retries for recoverable application errors.
        """
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)
            tool_definition = _pydantic_to_tool_definition(response_schema)
            
            log.info(f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s) using Tool Calling.")
            start_time = time.perf_counter()
            
            # MODIFICATION: Added a retry loop for specific, recoverable errors like TypeError.
            # This handles cases where the model provides a malformed/unexpected response.
            # Network errors (504, 429, etc.) are handled automatically by the client's `max_retries`.
            for attempt in range(API_MAX_RETRIES):
                response = None # Initialize response to None for each attempt
                try:
                    response = await self._client.chat.completions.create(
                        model=model_to_use,
                        messages=messages,
                        tools=[tool_definition],
                        tool_choice={"type": "function", "function": {"name": tool_definition["function"]["name"]}},
                    )
                    
                    # Defensive check: Ensure tool_calls exists and is not empty before accessing it.
                    if not (response.choices and response.choices[0].message and response.choices[0].message.tool_calls):
                        raw_response_content = response.choices[0].message.content if response.choices and response.choices[0].message else "Empty response"
                        raise TypeError(f"Model response did not contain the expected tool call. Content: {raw_response_content}")

                    tool_call = response.choices[0].message.tool_calls[0]
                    json_string = tool_call.function.arguments

                    parsed_response = response_schema.model_validate_json(json_string)
                    
                    duration = time.perf_counter() - start_time
                    log.info(f"[{context}] LLM call and parsing successful. Duration: {duration:.2f} seconds.")
                    return parsed_response

                # Catch the specific errors that indicate a recoverable model failure
                except (ValidationError, IndexError, KeyError, TypeError) as e:
                    duration = time.perf_counter() - start_time
                    log.warning(f"[{context}] Recoverable error on attempt {attempt + 1}/{API_MAX_RETRIES}: {e}. Retrying...")
                    if attempt < API_MAX_RETRIES - 1:
                        await asyncio.sleep(EXPONENTIAL_BACKOFF_FACTOR ** attempt)  # Exponential backoff
                    else:
                        # This is the last attempt, log as error and exit loop
                        log.error(f"[{context}] Final attempt failed after {duration:.2f}s. Error: {e}")
                        raw_response_content = "Response was empty or did not contain a valid tool call."
                        if response and response.choices and response.choices[0].message:
                            raw_response_content = response.choices[0].message.content or str(response.choices[0].message.tool_calls)
                        return {"error": f"Schema Validation Error: {str(e)}", "raw_response": raw_response_content}

                except (APIStatusError, APIConnectionError) as e:
                    duration = time.perf_counter() - start_time
                    # This block will only be hit after the client's built-in retries fail.
                    log.error(f"[{context}] API call failed after all retries. Duration: {duration:.2f}s: {e}")
                    return {"error": f"API Error after retries: {str(e)}"}
                except Exception as e:
                    duration = time.perf_counter() - start_time
                    log.error(f"[{context}] Unexpected non-recoverable error after {duration:.2f}s: {e.__class__.__name__} - {e}")
                    return {"error": f"Application Error: {str(e)}"}
            
            # Fallback return statement
            return {"error": "All retry attempts failed to produce a valid response."}


    async def close(self):
        if self._client and not self._client.is_closed():
            await self._client.close()
            log.info("Closed OpenAI AsyncClient.")