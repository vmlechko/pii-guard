# Воспроизводимый пайплайн одной командой на каждый шаг.
.PHONY: install test run docker smoke

install:
	pip install -r requirements.txt

test:
	pytest -q

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

docker:
	docker compose up --build

# Проверка развёрнутого сервиса: make smoke URL=http://localhost:8000
URL ?= http://localhost:8000
smoke:
	python scripts/smoke.py $(URL)
