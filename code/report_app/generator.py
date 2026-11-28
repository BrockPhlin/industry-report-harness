"""Shared model configuration and Chat Completions adapter."""
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from http.client import HTTPException

from .errors import AppError


def read_config(path):
    values = {}
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return {**values, **os.environ}  # Environment wins; do not execute .env text.


def model_connection(config):
    endpoint = config.get("MODEL_ENDPOINT", "").strip()
    model = config.get("MODEL_NAME", "").strip()
    key = config.get("MODEL_API_KEY", "").strip()
    if not endpoint or not model or not key:
        raise AppError("模型模式尚未配置：请填写 MODEL_ENDPOINT、MODEL_NAME 和 MODEL_API_KEY", 400, "model_not_configured")
    url = urlsplit(endpoint)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise AppError("MODEL_ENDPOINT须为无用户名、密码、查询参数或片段的完整HTTP(S)地址")
    if url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise AppError("远程模型接口必须使用HTTPS")
    return endpoint, model, key


def chat_completion(connection, messages, opener=urlopen, *, request_timeout=60, **options):
    endpoint, model, key = connection
    payload = {"model": model, "messages": messages, **options}
    request = Request(endpoint, data=json.dumps(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with opener(request, timeout=request_timeout) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise AppError("模型响应过大", 502, "model_response_invalid")
        result = json.loads(raw)
        choice = result["choices"][0]
        if not isinstance(choice, dict) or not isinstance(choice["message"], dict):
            raise ValueError("empty completion")
        if choice.get("finish_reason") == "length":
            raise AppError("模型输出被截断，请缩小任务后重试", 502, "model_output_truncated")
        usage = result.get("usage")
        if isinstance(usage, dict):
            counts = {key: usage[key] for key in ("prompt_tokens","completion_tokens","total_tokens")
                      if type(usage.get(key)) is int and usage[key]>=0}
            if counts:
                choice = {**choice,"usage":counts}
        return choice
    except HTTPError as exc:
        # Never forward the provider response body, URL or credentials to UI.
        raise AppError(f"模型服务返回HTTP {exc.code}，请检查服务与配置", 502, "model_http_error") from None
    except (URLError, TimeoutError) as exc:
        if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
            raise AppError("等待模型响应超时", 502, "model_timeout") from None
        raise AppError("模型请求失败，请检查服务与网络", 502, "model_unavailable") from None
    except (HTTPException, ConnectionError):
        raise AppError("模型响应连接提前关闭，请检查服务与网络", 502, "model_unavailable") from None
    except (ValueError, KeyError, IndexError, TypeError, UnicodeError):
        raise AppError("模型响应不符合当前文本接口约定", 502, "model_response_invalid") from None
