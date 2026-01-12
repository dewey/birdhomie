.PHONY: run dev compile-translations extract-translations update-translations init-db migrate process clean help build-base-image sync-data

# Compile translations and start the app
run: compile-translations
	uv run birdhomie

# Run with hot reloading (development mode, verbose YOLO output)
dev: compile-translations
	FLASK_DEBUG=1 YOLO_VERBOSE=true uv run flask --app src.birdhomie.app run --host 0.0.0.0 --port $${PORT:-5000} --reload

# Compile .po files to .mo files
compile-translations:
	uv run pybabel compile -d src/birdhomie/translations || true

# Extract translatable strings from source files
extract-translations:
	cd src/birdhomie && uv run pybabel extract -F babel.cfg -o messages.pot .

# Update existing translation catalogs with new strings
update-translations: extract-translations
	uv run pybabel update -i src/birdhomie/messages.pot -d src/birdhomie/translations

# Initialize database
init-db:
	uv run python -m birdhomie.database init

# Run pending migrations
migrate:
	uv run python -m birdhomie.database migrate

# Run file processor manually
process:
	uv run python -m birdhomie.processor

# Clean generated files
clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

# Build and push base image (amd64)
build-base-image:
	docker buildx build --platform linux/amd64 \
		-f Dockerfile.base \
		-t ghcr.io/dewey/birdhomie-base:latest \
		--push .

# Sync production data locally (requires SYNC_REMOTE)
sync-data:
	@if [ -z "$(SYNC_REMOTE)" ]; then \
		echo "Error: SYNC_REMOTE not set. Configure in .envrc and run 'direnv allow' or 'source .envrc'"; \
		exit 1; \
	fi
	@echo "Syncing data from $(SYNC_REMOTE) to ./data/"
	@mkdir -p data
	rsync -avz --progress \
		--exclude='logs/' \
		$(SYNC_REMOTE)/ \
		./data/

# Show help
help:
	@echo "Available targets:"
	@echo "  run                   - Compile translations and start the app"
	@echo "  dev                   - Run with hot reloading (development mode)"
	@echo "  compile-translations  - Compile .po files to .mo files"
	@echo "  extract-translations  - Extract translatable strings"
	@echo "  update-translations   - Update translation catalogs"
	@echo "  init-db               - Initialize database"
	@echo "  migrate               - Run pending migrations"
	@echo "  process               - Run file processor manually"
	@echo "  sync-data             - Sync production data locally for testing"
	@echo "  clean                 - Clean generated files"
	@echo "  build-base-image      - Build and push base image (amd64)"
