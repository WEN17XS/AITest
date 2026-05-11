from __future__ import annotations

from langchain_deepseek import ChatDeepSeek

from app.core.config import settings


def get_deepseek_chat_model(temperature: float = 0.2, max_tokens: int | None = None) -> ChatDeepSeek | None:
    """创建 DeepSeek 聊天模型。

    返回 None 表示当前没有配置 DeepSeek API Key，调用方应走本地兜底逻辑。
    """

    if not settings.deepseek_api_key:
        return None

    kwargs = {
        "api_key": settings.deepseek_api_key,
        "base_url": settings.deepseek_base_url,
        "model": settings.deepseek_model,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatDeepSeek(**kwargs)
