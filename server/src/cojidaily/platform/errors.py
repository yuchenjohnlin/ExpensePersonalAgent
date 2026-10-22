"""Every error answers {"error": message} or {"error": message, "fields": {field: [messages]}}.

Request bodies are Pydantic models; their errors are turned into the same shape, with the few
kinds of messages that can happen said in Chinese like the rest of the app.
"""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

CHECK = "請檢查輸入內容。"


class ApiError(Exception):
    def __init__(self, status: int, error: str, fields: dict[str, list[str]] | None = None, **extra):
        super().__init__(error)
        self.status, self.error, self.fields, self.extra = status, error, fields, extra


def invalid(fields: dict[str, list[str]]) -> ApiError:
    return ApiError(400, CHECK, fields)


def not_found(what: str = "資料") -> ApiError:
    return ApiError(404, f"找不到這筆{what}。")


# Pydantic's error types -> what the user reads. A validator's own ValueError keeps its message.
MESSAGES = {
    "missing": "此為必需欄位。",
    "extra_forbidden": "不支援的欄位。",
    "string_type": "請使用文字。",
    "bool_type": "請使用 true 或 false。",
    "int_type": "請使用整數。",
    "int_parsing": "請使用整數。",
    "list_type": "請使用陣列。",
    "model_type": "請提供 JSON 物件。",
    "dict_type": "請提供 JSON 物件。",
    "json_invalid": "不是有效的 JSON。",
    "string_too_long": "內容太長。",
}


def field_errors(errors) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for error in errors:
        # ("body", "amount") -> "amount"; the whole body -> "__all__".
        location = [str(part) for part in error["loc"] if part not in ("body", "query", "path")]
        name = ".".join(location) or "__all__"
        if error["type"] == "value_error":
            message = str(error.get("ctx", {}).get("error", error["msg"]))
        else:
            message = MESSAGES.get(error["type"], error["msg"])
        fields.setdefault(name, []).append(message)
    return fields


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        body = {"error": exc.error, **exc.extra}
        if exc.fields is not None:
            body["fields"] = exc.fields
        return JSONResponse(body, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse({"error": CHECK, "fields": field_errors(exc.errors())}, 400)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        error = {404: "找不到資源。", 405: "不支援這個方法。"}.get(exc.status_code, str(exc.detail))
        return JSONResponse({"error": error}, exc.status_code, headers=exc.headers)
