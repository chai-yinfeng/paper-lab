"""Store provider credentials in the user's macOS login Keychain."""

from __future__ import annotations

import hashlib
import platform
import subprocess
from urllib.parse import urlparse

SERVICE = "com.chai-yinfeng.paper-lab.api-key"


def _account(provider: str, base_url: str) -> str:
    normalized = base_url.rstrip("/")
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    host = urlparse(normalized).hostname or "api"
    return f"{provider}:{host}:{digest}"


def get_key(provider: str, base_url: str) -> str | None:
    if platform.system() != "Darwin":
        return None
    result = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            SERVICE,
            "-a",
            _account(provider, base_url),
            "-w",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode == 0:
        value = result.stdout.rstrip("\n")
        return value or None
    if result.returncode == 44 or "could not be found" in result.stderr:
        return None
    raise ValueError("无法读取 macOS Keychain 中的 API key。")


def set_key(provider: str, base_url: str, secret: str) -> None:
    if platform.system() != "Darwin":
        raise ValueError("当前系统暂不支持 Keychain，请使用环境变量配置 API key。")
    value = secret.strip()
    if not value:
        raise ValueError("API key 不能为空。")
    host = urlparse(base_url).hostname or "API"
    result = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-s",
            SERVICE,
            "-a",
            _account(provider, base_url),
            "-l",
            f"Paper Lab — {provider} @ {host}",
            "-U",
            "-w",
        ],
        # `security -w` prompts twice when creating a new item. Supplying both
        # lines over stdin keeps the secret out of the process argument list.
        input=value + "\n" + value + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("无法将 API key 保存到 macOS Keychain。")
