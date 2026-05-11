Write-Host "启动 AITestHub 本地依赖：PostgreSQL + Redis"
docker compose up -d db redis

Write-Host "后端启动命令："
Write-Host "cd backend; .venv\Scripts\activate; alembic upgrade head; uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

Write-Host "Celery Worker 启动命令："
Write-Host "cd backend; .venv\Scripts\activate; celery -A app.workers.celery_app worker --loglevel=info -P solo"

Write-Host "前端启动命令："
Write-Host "cd frontend; npm install; npm run dev"

