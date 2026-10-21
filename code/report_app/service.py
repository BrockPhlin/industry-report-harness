"""Input validation and orchestration. No retries, queue or Harness yet."""
from .errors import AppError
from .generator import excerpt_report, model_report


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

    def add_source(self, data):
        return self.store.add_source({
            "title": text_field(data, "title", 160, True),
            "body": text_field(data, "body", 50000, True),
            "publisher": text_field(data, "publisher", 160),
            "published_at": text_field(data, "published_at", 40),
            "url": text_field(data, "url", 1000),
        })

    def generate(self, data):
        topic = text_field(data, "topic", 160, True)
        mode = data.get("mode", "excerpt")
        if not isinstance(mode, str) or mode not in {"excerpt", "model"}:
            raise AppError("mode必须为excerpt或model")
        ids = data.get("source_ids")
        if not isinstance(ids, list) or not 1 <= len(ids) <= 10 or any(not isinstance(i, str) or not i for i in ids):
            raise AppError("请选择1至10份资料，source_ids须为文本ID数组")
        if len(set(ids)) != len(ids):
            raise AppError("资料ID不能重复")
        sources = [self.store.get_source(i) for i in ids]
        if mode == "excerpt":
            markdown, warnings = excerpt_report(topic, sources)
        else:
            markdown, warnings = model_report(topic, sources, self.config)
        return self.store.add_report(topic, mode, markdown, sources, warnings)
