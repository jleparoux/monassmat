# monassmat
Le suivi simplifie des contrats d'assistante maternelle.

## Calendrier
- Page: `/contracts/{id}/calendar`
- API workdays: `/api/contracts/{id}/workdays?start=YYYY-MM-DD&end=YYYY-MM-DD`
- Formulaire jour: `/contracts/{id}/day_form?day=YYYY-MM-DD`
- Synthese mensuelle: `/contracts/{id}/month_summary?start=YYYY-MM-DD&end=YYYY-MM-DD`
- Synthese annuelle: `/contracts/{id}/year_summary?year=YYYY`
- Page synthese annuelle: `/contracts/{id}/summary/year?year=YYYY`
- Page liste contrats: `/contracts`
- Creation contrat: `/contracts/new`
- Types de journee: travail, absence, conge sans solde, jour ferie
- Parametres: chaque sauvegarde cree un snapshot date (champ "Application des parametres a partir du")

## Import assmat-tracker
- Script: `scripts/import_assmat_tracker.py`
- Import: `--month-file` ou `--months-dir` (avec `settings.json` optionnel)
- Jours feries: charge `holidays-YYYY.json` dans le meme dossier (ou via `--holidays-file` / `--holidays-dir`) et force le statut `ferie` lors de l'import
 - Statuts importes: travail, conge assmat, conge parent (absence), conge sans solde, ferie

## Backup / restore
- Backup (docker par defaut): `python scripts/db_backup.py`
- Restore (docker par defaut): `python scripts/db_restore.py --input backups/monassmat_YYYYMMDD_HHMMSS.dump`
- Mode local: ajouter `--mode local` et optionnellement `--db-url`
- Dump/restore partiel: `--data-only` ou `--schema-only`
- Export lisible: ajouter `--sql-output backups/monassmat_YYYYMMDD_HHMMSS.sql`
- Makefile: `make run`, `make backup`, `make restore BACKUP=backups/monassmat_YYYYMMDD_HHMMSS.dump` (optionnel: `MODE=local` et `DB_URL=...`)
- `make backup` genere maintenant aussi un `.sql` a cote du `.dump`
