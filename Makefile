.PHONY: up down logs rebuild

up:
	docker compose up --build -d

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

rebuild:
	docker compose build --no-cache
