"""Minimal fal.ai queue client (standard library only).

  POST https://queue.fal.run/<model>      {inputs}   -> {request_id, status_url, response_url}
  GET  <status_url>                                  -> {status: IN_QUEUE | IN_PROGRESS | COMPLETED}
  GET  <response_url>                                -> model output, e.g. {images: [{url, ...}]}
Auth header: "Authorization: Key $FAL_KEY". Images are sent inline as data URIs.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class FalError(Exception):
    pass


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


class FalClient:
    def __init__(self, key: str | None = None, base_url: str = "https://queue.fal.run", timeout: float = 120):
        self.key = key or os.environ.get("FAL_KEY")
        if not self.key:
            raise FalError("FAL_KEY is not set. Create a key at fal.ai (Dashboard > Keys) and add it to the environment.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _call(self, url: str, payload: Any | None = None, auth: bool = True) -> bytes:
        headers = {"Authorization": f"Key {self.key}"} if auth else {}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers),
                                        timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            raise FalError(f"fal.ai {e.code} for {url.split('?')[0]}: {e.read().decode(errors='replace')[:500]}") from None
        except urllib.error.URLError as e:
            raise FalError(f"cannot reach {url.split('/')[2]} ({e.reason}). Is the domain allowed in network settings?") from None

    def run(self, model: str, inputs: dict[str, Any], timeout: float = 900, poll: float = 2.0) -> dict[str, Any]:
        sub = json.loads(self._call(f"{self.base_url}/{model}", inputs))
        status_url = sub.get("status_url") or f"{self.base_url}/{model}/requests/{sub['request_id']}/status"
        response_url = sub.get("response_url") or f"{self.base_url}/{model}/requests/{sub['request_id']}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = json.loads(self._call(status_url))
            if status.get("status") == "COMPLETED":
                if status.get("error"):
                    raise FalError(f"{model} failed: {status['error']}")
                return json.loads(self._call(response_url))
            time.sleep(poll)
        raise FalError(f"{model} timed out after {timeout:.0f}s")

    def download(self, url: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        if url.startswith("data:"):
            target.write_bytes(base64.b64decode(url.split(",", 1)[1]))
        else:
            target.write_bytes(self._call(url, auth=False))
        return target
