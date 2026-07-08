"""Unified API response envelope: {success, data, message}."""

from typing import Any


def ok(data: Any = None, message: str = "") -> dict[str, Any]:
    return {"success": True, "data": data if data is not None else {}, "message": message}


def fail(code: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "data": {"code": code, "detail": detail or {}},
        "message": message,
    }
