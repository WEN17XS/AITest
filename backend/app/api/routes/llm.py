from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.config import settings
from app.services.llm_service import get_deepseek_chat_model

router = APIRouter()


@router.get("/health")
def llm_health(_user=Depends(get_current_user)) -> dict[str, str | bool]:
    if not settings.deepseek_api_key:
        return {
            "ok": False,
            "provider": settings.llm_provider,
            "model": settings.deepseek_model,
            "message": "未配置 DEEPSEEK_API_KEY",
        }

    try:
        model = get_deepseek_chat_model(temperature=0, max_tokens=8)
        if model is None:
            return {"ok": False, "provider": "deepseek", "model": settings.deepseek_model, "message": "模型未初始化"}
        model.invoke("只回复 ok")
        return {
            "ok": True,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "message": "DeepSeek LangChain 集成可用",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": "deepseek",
            "model": settings.deepseek_model,
            "message": str(exc),
        }
