import httpx
import asyncio
import base64
import time
import random
from typing import List, Dict, Any, Optional

from utils import log, get_mime_type
from config import (
    API_URL,
    API_KEY,
    API_MODEL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_CONCURRENCY_LIMIT,
)

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
        content_parts = [{"type": "text", "text": prompt_text}]

        for file_info in document_files:
            file_path = file_info["path"]
            try:
                with open(file_path, "rb") as f:
                    file_content = f.read()
                
                base64_encoded_data = base64.b64encode(file_content).decode('utf-8')
                mime_type = get_mime_type(file_path)
                
                image_url = f"data:{mime_type};base64,{base64_encoded_data}"
                content_parts.append({"type": "image_url", "image_url": {"url": image_url}})
            except Exception as e:
                log.error(f"Failed to read and encode file {file_path}: {e}")
                continue
        
        return {"model": model, "messages": [{"role": "user", "content": content_parts}]}

    async def call_llm_api(
        self,
        prompt_text: str,
        document_files: Optional[List[Dict]] = None,
        model_override: Optional[str] = None
    ) -> str:
        """Makes a call to the LLM API with concurrency limiting and exponential backoff."""
        async with self._semaphore:
            client = await self._get_client()
            model_to_use = model_override or API_MODEL
            payload = self._prepare_request_payload(model_to_use, prompt_text, document_files or [])
            headers = {'Content-Type': 'application/json', 'x-goog-api-key': API_KEY}

            delay = 1.0
            for attempt in range(API_MAX_RETRIES):
                try:
                    log.info(f"Calling LLM API, attempt {attempt + 1}/{API_MAX_RETRIES}...")
                    response = await client.post(API_URL, headers=headers, json=payload)
                    
                    if not client.verify:
                         log.warning(f"Making unverified HTTPS request to host '{API_URL}'.")

                    response.raise_for_status()
                    response_json = response.json()
                    log.info("LLM API call successful.")

                    if response_json.get("choices") and isinstance(response_json["choices"], list) and response_json["choices"]:
                        message = response_json["choices"][0].get("message")
                        if message and "content" in message:
                            return message["content"]
                    
                    log.error(f"Invalid response structure from LLM API: {response.text}")
                    return f'{{"error": "Invalid response structure", "details": {response.text}}}'

                except httpx.HTTPStatusError as e:
                    log.error(f"HTTP error on attempt {attempt + 1}: {e.response.status_code} - {e.response.text}")
                    if e.response.status_code in [429, 500, 502, 503, 504]:
                        if attempt == API_MAX_RETRIES - 1:
                            return f'{{"error": "API returned final status {e.response.status_code}", "details": "{e.response.text}"}}'
                        time.sleep(delay * (2 ** attempt) + random.uniform(0, 0.5))
                    else:
                        return f'{{"error": "API returned client error {e.response.status_code}", "details": "{e.response.text}"}}'
                except httpx.RequestError as e:
                    log.error(f"Request error on attempt {attempt + 1}: {e}")
                    if attempt == API_MAX_RETRIES - 1:
                       return f'{{"error": "API request failed after multiple retries.", "details": "{str(e)}"}}'
                    time.sleep(delay * (2 ** attempt) + random.uniform(0, 0.5))
                except Exception as e:
                    log.exception("An unexpected error occurred in call_llm_api.")
                    return f'{{"error": "An unexpected error occurred.", "details": "{str(e)}"}}'
        return '{"error": "Exhausted all retries for LLM API call."}'

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            log.info("Closed httpx.AsyncClient.")