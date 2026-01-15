.PHONY: run backup restore

RUN ?= uv run
PYTHON ?= python
PYTHONPATH ?= src
MODE ?= docker
BACKUP ?=

run:
	PYTHONPATH=$(PYTHONPATH) $(RUN) uvicorn monassmat.app:app --reload

backup:
	PYTHONPATH=$(PYTHONPATH) $(RUN) $(PYTHON) scripts/db_backup.py --mode $(MODE) --with-sql $(if $(DB_URL),--db-url $(DB_URL),)

restore:
	@if [ -z "$(BACKUP)" ]; then echo "Usage: make restore BACKUP=backups/monassmat_YYYYMMDD_HHMMSS.dump"; exit 1; fi
	PYTHONPATH=$(PYTHONPATH) $(RUN) $(PYTHON) scripts/db_restore.py --input "$(BACKUP)" --mode $(MODE) $(if $(DB_URL),--db-url $(DB_URL),)
