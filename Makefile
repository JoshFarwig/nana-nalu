# Color definitions
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
CYAN := \033[36m
RESET := \033[0m

.PHONY: help seed-dev seed-prod up-dev up-prod up-dev-full up-prod-full down-dev down-prod logs-dev logs-prod restart-dev restart-prod migrate-dev migrate-prod migrate-local migrate-create watch-dev

help:  ## Show this help message
	@echo "$(CYAN)Available commands:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'

# Development environment commands
up-dev:  ## Start development environment
	@echo "$(BLUE)Starting development environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev up -d 
	@echo "$(GREEN)✓ Development environment started!$(RESET)"



down-dev:  ## Stop development environment
	@echo "$(YELLOW)Stopping development environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev down
	@echo "$(GREEN)✓ Development environment stopped!$(RESET)"

restart-dev:  ## Restart development environment
	@echo "$(BLUE)Restarting development environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev restart
	@echo "$(GREEN)✓ Development environment restarted!$(RESET)"

watch-dev:  ## Start development environment with watch mode (file sync)
	@echo "$(CYAN)Starting development environment with watch mode...$(RESET)"
	@echo "$(YELLOW)Press Ctrl+C to stop watching (containers will keep running)$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev watch --no-up

logs-dev:  ## Follow logs for development environment
	@echo "$(CYAN)Following development logs (Ctrl+C to exit)...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev logs -f

seed-dev:  ## Seed development database
	@echo "$(BLUE)Seeding development database...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec api python -m scripts.seed.seed
	@echo "$(GREEN)✓ Development database seeded successfully!$(RESET)"

migrate-dev:  ## Apply latest Alembic migration to development database
	@echo "$(BLUE)Applying migrations to development database...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev exec api alembic upgrade head
	@echo "$(GREEN)✓ Migrations applied successfully!$(RESET)"

up-dev-full:  ## Start dev environment, run migrations, and seed database
	@echo "$(CYAN)Starting full development environment setup...$(RESET)"
	@$(MAKE) up-dev
	@sleep 3
	@$(MAKE) migrate-dev
	@$(MAKE) seed-dev
	@echo "$(GREEN)✓ Full development environment ready!$(RESET)"

# Production environment commands
up-prod:  ## Start production environment
	@echo "$(BLUE)Starting production environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "$(GREEN)✓ Production environment started!$(RESET)"

down-prod:  ## Stop production environment
	@echo "$(YELLOW)Stopping production environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod down
	@echo "$(GREEN)✓ Production environment stopped!$(RESET)"

restart-prod:  ## Restart production environment
	@echo "$(BLUE)Restarting production environment...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod restart
	@echo "$(GREEN)✓ Production environment restarted!$(RESET)"

logs-prod:  ## Follow logs for production environment
	@echo "$(CYAN)Following production logs (Ctrl+C to exit)...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod logs -f

seed-prod:  ## Seed production database
	@echo "$(BLUE)Seeding production database...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod exec api python -m scripts.seed.seed
	@echo "$(GREEN)✓ Production database seeded successfully!$(RESET)"

migrate-prod:  ## Apply latest Alembic migration to production database
	@echo "$(BLUE)Applying migrations to production database...$(RESET)"
	@docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.prod exec api alembic upgrade head
	@echo "$(GREEN)✓ Migrations applied successfully!$(RESET)"

up-prod-full:  ## Start prod environment, run migrations, and seed database
	@echo "$(CYAN)Starting full production environment setup...$(RESET)"
	@$(MAKE) up-prod
	@sleep 3
	@$(MAKE) migrate-prod
	@$(MAKE) seed-prod
	@echo "$(GREEN)✓ Full production environment ready!$(RESET)"

# Local Alembic commands (run from host machine)
migrate-local:  ## Apply migrations from host machine (requires .env.local)
	@echo "$(BLUE)Applying migrations from local machine...$(RESET)"
	@if [ ! -f .env.local ]; then \
		echo "$(RED)Error: .env.local not found. Copy .env.local.sample and configure it.$(RESET)"; \
		exit 1; \
	fi
	@cd backend && set -a && . ../.env.local && set +a && uv run alembic upgrade head
	@echo "$(GREEN)✓ Migrations applied successfully!$(RESET)"

migrate-create:  ## Create new migration (use: make migrate-create MSG="description")
	@echo "$(BLUE)Creating new migration...$(RESET)"
	@if [ ! -f .env.local ]; then \
		echo "$(RED)Error: .env.local not found. Copy .env.local.sample and configure it.$(RESET)"; \
		exit 1; \
	fi
	@if [ -z "$(MSG)" ]; then \
		echo "$(RED)Error: MSG is required. Usage: make migrate-create MSG=\"your migration description\"$(RESET)"; \
		exit 1; \
	fi
	@cd backend && set -a && . ../.env.local && set +a && uv run alembic revision --autogenerate -m "$(MSG)"
	@echo "$(GREEN)✓ Migration file created in ./backend/alembic/versions/$(RESET)"
