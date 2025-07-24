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
        http_client = httpx.AsyncClient(http2=True, verify=False, timeout=API_TIMEOUT)
        self._client = AsyncOpenAI(
            api_key=API_KEY, base_url=API_BASE_URL, max_retries=API_MAX_RETRIES, http_client=http_client
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
        """Forces the LLM to return a specific Pydantic schema using Tool Calling."""
        async with self._semaphore:
            model_to_use = model_override or API_MODEL
            messages = self._prepare_request_messages(prompt_text, document_files)
            tool_definition = _pydantic_to_tool_definition(response_schema)
            
            log.info(f"[{context}] Calling model '{model_to_use}' with {len(document_files)} page(s) using Tool Calling.")
            start_time = time.perf_counter()
            
            try:
                response = await self._client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    tools=[tool_definition],
                    tool_choice={"type": "function", "function": {"name": tool_definition["function"]["name"]}},
                )
                
                duration = time.perf_counter() - start_time
                tool_call = response.choices[0].message.tool_calls[0]
                json_string = tool_call.function.arguments

                # Parse the JSON string from the tool's arguments into the Pydantic schema
                parsed_response = response_schema.model_validate_json(json_string)
                
                log.info(f"[{context}] LLM call and parsing successful. Duration: {duration:.2f} seconds.")
                return parsed_response

            except (ValidationError, IndexError, KeyError) as e:
                duration = time.perf_counter() - start_time
                raw_response_content = response.choices[0].message.content if response.choices[0].message.content else "Tool call failed or was empty."
                log.error(f"[{context}] Pydantic validation failed after {duration:.2f}s. The model did not return the correct tool call structure. Error: {e}")
                return {"error": f"Schema Validation Error: {str(e)}", "raw_response": raw_response_content}
            except (APIStatusError, APIConnectionError) as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] API call failed after {duration:.2f}s: {e}")
                return {"error": f"API Error: {str(e)}"}
            except Exception as e:
                duration = time.perf_counter() - start_time
                log.error(f"[{context}] Unexpected error after {duration:.2f}s: {e.__class__.__name__} - {e}")
                return {"error": f"Application Error: {str(e)}"}

    async def close(self):
        if self._client and not self._client.is_closed():
            await self._client.close()
            log.info("Closed OpenAI AsyncClient.")