"""Research request fields and local workspace dependencies."""
from .errors import AppError


def text_field(data, key, limit, required=False):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise AppError(f"{key}必须是文本")
    value = value.strip()
    if (required and not value) or len(value) > limit:
        raise AppError(f"{key}不能为空且不超过{limit}字符" if required else f"{key}不能超过{limit}字符")
    return value


class Service:
    def __init__(self, store, config):
        self.store = store
        self.config = config
