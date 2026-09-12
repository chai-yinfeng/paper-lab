"""Provider boundary; the workflow never depends on Codex or an SDK agent runtime."""

from __future__ import annotations
import json
from typing import AsyncIterator
import httpx
from pydantic import BaseModel, Field, model_validator
from urllib.parse import urlparse


class ProviderSettings(BaseModel):
    provider: str = "deepseek"
    base_url: str = "https://api.deepseek.com"
    model: str = Field(default="deepseek-flash", min_length=1, max_length=150)
    supports_images: bool = True
    effort: str = "none"
    max_tokens: int = Field(default=4096, ge=256, le=16384)

    @model_validator(mode="after")
    def check(self):
        if self.provider not in ("deepseek", "openai-compatible"):
            raise ValueError("不支持的 provider。")
        if self.effort not in ("none", "low", "high"):
            raise ValueError("不支持的推理强度。")
        url = urlparse(self.base_url)
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("API 地址必须为不含凭据的 HTTPS URL。")
        if self.provider == "deepseek" and self.base_url.rstrip("/") not in (
            "https://api.deepseek.com",
            "https://api.deepseek.com/v1",
        ):
            raise ValueError(
                "DeepSeek provider 仅向官方 API 发送 key。自定义接口请选择兼容 provider。"
            )
        return self


def payload(settings, messages):
    body = {
        "model": settings.model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "max_tokens": settings.max_tokens,
    }
    if settings.provider == "deepseek":
        body["thinking"] = {
            "type": "disabled" if settings.effort == "none" else "enabled"
        }
        if settings.effort != "none":
            body["reasoning_effort"] = settings.effort
    return body


async def stream_completion(
    settings: ProviderSettings, key: str, messages: list
) -> AsyncIterator[dict]:
    # No automatic retries: repeating a billable request requires a user action.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(120, connect=20), follow_redirects=False
    ) as client:
        async with client.stream(
            "POST",
            settings.base_url.rstrip("/") + "/chat/completions",
            headers={"Authorization": "Bearer " + key},
            json=payload(settings, messages),
        ) as response:
            if response.status_code != 200:
                # Do not persist upstream error bodies, which can contain request data.
                hint = {
                    400: "模型拒绝了请求；全文输入可能超过该模型的 context window，或请求参数不被支持。",
                    401: "API key 无效或已失效。",
                    402: "API 余额不足。",
                    429: "API 请求受限，请稍后重试。",
                }.get(response.status_code, "模型服务返回错误。")
                raise ValueError(f"{hint}（HTTP {response.status_code}）")
            finished = False
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    if not finished:
                        raise ValueError("模型流未提供完成状态。")
                    return
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise ValueError("模型返回了无法解析的流。") from exc
                if chunk.get("error"):
                    raise ValueError("模型流返回错误。")
                if chunk.get("model"):
                    yield {"type": "model", "model": chunk["model"]}
                if chunk.get("usage"):
                    yield {"type": "usage", "usage": chunk["usage"]}
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta.get("content"):
                        yield {"type": "delta", "text": delta["content"]}
                    if delta.get("reasoning_content"):
                        yield {"type": "thinking"}
                    if choice.get("finish_reason"):
                        finished = True
                        yield {"type": "finish", "reason": choice["finish_reason"]}
            if not finished:
                raise ValueError("模型连接提前断开，回答尚未完成。")
