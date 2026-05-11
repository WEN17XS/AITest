from fastapi import APIRouter

from app.api.routes import auth, ci, environments, knowledge, llm, projects, requirements, runs, test_cases

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["登录权限"])
api_router.include_router(projects.router, prefix="/projects", tags=["项目"])
api_router.include_router(environments.router, prefix="/environments", tags=["项目环境"])
api_router.include_router(requirements.router, prefix="/requirements", tags=["需求"])
api_router.include_router(test_cases.router, prefix="/test-cases", tags=["测试用例"])
api_router.include_router(runs.router, prefix="/runs", tags=["测试执行"])
api_router.include_router(ci.router, prefix="/ci", tags=["CI/CD"])
api_router.include_router(knowledge.router, prefix="/knowledge", tags=["知识库"])
api_router.include_router(llm.router, prefix="/llm", tags=["大模型"])
