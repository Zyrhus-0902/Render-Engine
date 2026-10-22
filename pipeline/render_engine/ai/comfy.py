"""Minimal ComfyUI HTTP client (standard library only).

ComfyUI API used:
  POST /upload/image      multipart field "image"      -> {"name", "subfolder", "type"}
  POST /prompt            {"prompt": graph, ...}       -> {"prompt_id"} or 400 with node_errors
  GET  /history/<id>      outputs once finished
  GET  /view?filename=&subfolder=&type=               the image bytes
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any


class ComfyError(Exception):
    pass


class ComfyClient:
    def __init__(self, url: str = "http://127.0.0.1:8188", timeout: float = 30.0):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    def _request(self, path: str, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:
        req = urllib.request.Request(self.url + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise ComfyError(f"ComfyUI {path} returned {e.code}: {_describe_error(body)}") from None
        except urllib.error.URLError as e:
            raise ComfyError(f"cannot reach ComfyUI at {self.url} ({e.reason}). Is it running?") from None

    def _json(self, path: str, payload: Any | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        return json.loads(self._request(path, data, headers) or b"null")

    def ping(self) -> dict[str, Any]:
        return self._json("/system_stats")

    def upload_image(self, path: Path, name: str | None = None) -> str:
        boundary = uuid.uuid4().hex
        filename = name or path.name
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        res = json.loads(self._request("/upload/image", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
        return f"{res['subfolder']}/{res['name']}" if res.get("subfolder") else res["name"]

    def queue(self, graph: dict[str, Any]) -> str:
        return self._json("/prompt", {"prompt": graph, "client_id": self.client_id})["prompt_id"]

    def wait(self, prompt_id: str, timeout: float = 3600, poll: float = 1.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            history = self._json(f"/history/{prompt_id}")
            entry = (history or {}).get(prompt_id)
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
                    detail = msgs[0][1].get("exception_message", "") if msgs else ""
                    raise ComfyError(f"generation failed: {detail.strip()}")
                if status.get("completed", True):
                    return entry
            time.sleep(poll)
        raise ComfyError(f"timed out after {timeout:.0f}s waiting for {prompt_id}")

    def output_images(self, entry: dict[str, Any]) -> list[dict[str, str]]:
        images = []
        for node_output in entry.get("outputs", {}).values():
            images.extend(i for i in node_output.get("images", []) if i.get("type") == "output")
        return images

    def download(self, image: dict[str, str], target: Path) -> Path:
        query = urllib.parse.urlencode({"filename": image["filename"], "subfolder": image.get("subfolder", ""),
                                        "type": image.get("type", "output")})
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self._request(f"/view?{query}"))
        return target


def _describe_error(body: str) -> str:
    """Turn ComfyUI's validation error JSON into a readable line (missing model files, etc.)."""
    try:
        data = json.loads(body)
    except ValueError:
        return body[:500]
    lines = [data.get("error", {}).get("message", "")]
    for node_id, err in (data.get("node_errors") or {}).items():
        for e in err.get("errors", []):
            lines.append(f"node {node_id} ({err.get('class_type')}): {e.get('message')} - {e.get('details')}")
    return "; ".join(line for line in lines if line)
