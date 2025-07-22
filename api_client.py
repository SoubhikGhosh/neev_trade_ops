import httpx
import asyncio
import base64
import time
import random
from typing import List, Dict, Any, Optional

from pydantic import BaseModel, Field

from utils import log, get_mime_type
from config import (
    API_URL,
    API_KEY,
    API_MODEL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_CONCURRENCY_LIMIT,
    API_BACKOFF_FACTOR
)

# Pydantic models to define the exact structure of the API request and response bodies
class APIRequestImageURL(BaseModel):
    url: str

class APIRequestMessageContent(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[APIRequestImageURL] = None

class APIRequestMessage(BaseModel):
    role: str
    content: List[APIRequestMessageContent]

class APIRequestBody(BaseModel):
    model: str
    messages: List[APIRequestMessage]

class APIResponseMessage(BaseModel):
    role: str
    content: str

class APIResponseChoice(BaseModel):
    index: int
    message: APIResponseMessage

class APIResponseBody(BaseModel):
    choices: List[APIResponseChoice]


class APIClient:
    """A thread-safe, asynchronous client for interacting with the LLM API."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore = asyncio.Semaphore(API_CONCURRENCY_LIMIT)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=API_TIMEOUT, verify=False)
            log.info("Initialized new httpx.AsyncClient.")
        return self._client

    def _prepare_request_payload(self, model: str, prompt_text: str, document_files: List[Dict]) -> Dict:
        """Prepares the JSON payload for the API using Pydantic models."""
        content_parts = [APIRequestMessageContent(type="text", text=prompt_text)]

        for file_info in document_files:
            file_path = file_info["path"]
            try:
                with open(file_path, "rb") as f:
                    file_content = f.read()
                
                base64_encoded_data = base64.b64encode(file_content).decode('utf-8')
                mime_type = get_mime_type(file_path)
                image_url = APIRequestImageURL(url=f"data:{mime_type};base64,{base64_encoded_data}")
                content_parts.append(APIRequestMessageContent(type="image_url", image_url=image_url))
            except Exception as e:
                log.error(f"Failed to read and encode file {file_path}: {e}")
                continue
        
        messages = [APIRequestMessage(role="user", content=content_parts)]
        api_request = APIRequestBody(model=model, messages=messages)
        return api_request.model_dump(exclude_none=True)

    async def call_llm_api(
        self,
        prompt_text: str,
        document_files: Optional[List[Dict]] = None,
        model_override: Optional[str] = None
    ) -> str:
        """Makes a call to the LLM API with robust, concurrency-limited retry logic."""
        async with self._semaphore:
            client = await self._get_client()
            model_to_use = model_override or API_MODEL
            payload = self._prepare_request_payload(model_to_use, prompt_text, document_files or [])
            headers = {'Content-Type': 'application/json', 'x-goog-api-key': API_KEY}
            
            delay = 1.5  # Initial delay
            for attempt in range(API_MAX_RETRIES):
                try:
                    log.info(f"Calling LLM API, attempt {attempt + 1}/{API_MAX_RETRIES}...")
                    response = await client.post(API_URL, headers=headers, json=payload)
                    response.raise_for_status()

                    api_response = APIResponseBody.model_validate(response.json())

                    if api_response.choices and api_response.choices[0].message.content:
                        log.info("LLM API call successful.")
                        return api_response.choices[0].message.content
                    
                    raise ValueError("API response is valid but missing expected content.")

                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    is_server_error = isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                    is_rate_limit_error = isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 429
                    is_network_error = isinstance(e, httpx.RequestError)

                    if not (is_server_error or is_rate_limit_error or is_network_error):
                        log.error(f"Non-retryable client error: {e}")
                        return f'{{"error": "Non-retryable client error", "details": "{str(e)}"}}'

                    log.warning(f"API call failed (Attempt {attempt + 1}/{API_MAX_RETRIES}): {e}.")
                    if attempt == API_MAX_RETRIES - 1:
                        log.error("Max retries exceeded.")
                        return f'{{"error": "Max retries exceeded", "details": "{str(e)}"}}'

                    wait_time = delay
                    if is_rate_limit_error:
                        retry_after = e.response.headers.get('Retry-After')
                        if retry_after:
                            try:
                                wait_time = float(retry_after)
                                log.info(f"Rate limit hit. Honoring 'Retry-After' header, waiting {wait_time}s.")
                            except (ValueError, TypeError):
                                log.warning(f"Could not parse 'Retry-After' header: '{retry_after}'. Using exponential backoff.")
                    
                    total_wait = wait_time + random.uniform(0, 1)
                    log.info(f"Retrying in {total_wait:.2f} seconds.")
                    await asyncio.sleep(total_wait)
                    delay *= API_BACKOFF_FACTOR

                except (ValueError, Exception) as e:
                    log.error(f"Non-retryable application error: {e}")
                    return f'{{"error": "Application error during API call", "details": "{str(e)}"}}'

        return '{"error": "Exhausted all retries for LLM API call."}'

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            log.info("Closed httpx.AsyncClient.")