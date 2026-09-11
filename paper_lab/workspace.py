from __future__ import annotations
import json
import hashlib
from pathlib import Path
from .store import Store

REPO = Path(__file__).resolve().parents[1]


class Workspace:
    def __init__(self, directory: str):
        raw = Path(directory).expanduser()
        if not raw.is_absolute():
            raise ValueError("请选择绝对路径。")
        root = raw.resolve()
        if root == Path(root.anchor) or root == Path.home():
            raise ValueError("请选择专用于 Paper Lab 的子目录。")
        if root.is_relative_to(REPO) or any(
            (p / ".git").exists() for p in [root, *root.parents]
        ):
            raise ValueError("阅读数据目录必须位于 Git 仓库之外。")
        marker = root / "workspace.json"
        if root.exists() and not root.is_dir():
            raise ValueError("所选路径不是目录。")
        if root.exists() and any(root.iterdir()) and not marker.is_file():
            raise ValueError(
                "请选择空目录或已有 Paper Lab 工作目录，避免混入其他文件。"
            )
        if marker.exists():
            if marker.is_symlink() or json.loads(marker.read_text()) != {
                "schema_version": 1,
                "application": "paper-lab",
            }:
                raise ValueError("工作目录标记不受支持。")
        for name in (
            "pdfs",
            "cache",
            "library.sqlite3",
            "library.sqlite3-wal",
            "library.sqlite3-shm",
        ):
            if (root / name).is_symlink():
                raise ValueError("工作目录内部不支持符号链接。")
        root.mkdir(parents=True, exist_ok=True)
        for name in ("pdfs", "cache"):
            (root / name).mkdir(exist_ok=True)
        marker.write_text(
            json.dumps({"schema_version": 1, "application": "paper-lab"}, indent=2)
        )
        self.root = root
        self.store = Store(root / "library.sqlite3")

    def pdf(self, sha):
        if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("无效文档标识。")
        path = self.root / "pdfs" / f"{sha}.pdf"
        if path.is_symlink():
            raise ValueError("PDF 不支持符号链接。")
        return path

    def verified_pdf(self, sha):
        path = self.pdf(sha)
        if not path.is_file():
            raise ValueError("本地 PDF 已丢失，请恢复原文件。")
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != sha:
                raise ValueError(
                    "PDF 内容已改变，旧引用不能继续使用。请作为新版本导入。"
                )
        return path
