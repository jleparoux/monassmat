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
## Deploiement Docker (Synology compatible)
- Build + run local:
  - `docker compose up -d --build`
  - App: `http://localhost:8000`
- Donnees Postgres persistantes:
  - Par defaut, `docker-compose.yml` monte `./data/postgres` vers `/var/lib/postgresql/data`.
  - Pour Synology, definir un chemin NAS via `POSTGRES_DATA_DIR`:
    - Exemple: `POSTGRES_DATA_DIR=/volume1/docker/monassmat/pgdata`

### Import PC -> Synology (pas a pas)
Prerequis:
- Docker fonctionne sur le NAS (Container Manager).
- Le fichier `docker-compose.yml` est copie sur le NAS (ex: `/volume1/docker/monassmat/`).
- Un dossier persistant Postgres existe sur le NAS (ex: `/volume1/docker/monassmat/pgdata`).

Etapes:
1. Sur le PC, creer un dump SQL lisible:
   - `python scripts/db_backup.py --sql-output backups/monassmat.sql`
2. Copier le fichier vers le NAS:
   - Copier `backups/monassmat.sql` vers `/volume1/docker/monassmat/monassmat.sql`.
3. Sur le NAS, definir le volume Postgres:
   - `POSTGRES_DATA_DIR=/volume1/docker/monassmat/pgdata`
4. Lancer les containers sur le NAS:
   - `docker compose up -d --build`
5. Importer dans Postgres (sur le NAS):
   - `cat /volume1/docker/monassmat/monassmat.sql | docker compose exec -T db psql -U monassmat -d monassmat`

Option alternative (copie de volume):
1. Arreter les containers sur le NAS.
2. Copier le dossier `./data/postgres` du PC vers `/volume1/docker/monassmat/pgdata`.
3. Relancer `docker compose up -d`.

### Synology - Container Manager (LAN uniquement)
1. Copier le projet sur le NAS (ex: `/volume1/docker/monassmat/`).
2. Ouvrir Container Manager > Projet > Creer.
3. Selectionner le dossier du projet et `docker-compose.yml`.
4. Ajouter la variable d'environnement:
   - Onglet "Variables d'environnement" du projet.
   - Ajouter `POSTGRES_DATA_DIR=/volume1/docker/monassmat/pgdata`.
5. Lancer le projet (Build + Run).
6. Acces LAN: `http://NAS_IP:8000`

### Migration volume Docker -> dossier `data/`
1. Sur l'ancien setup (volume `monassmat_pgdata`), faire un backup:
   - `make backup` (genere `.dump` + `.sql` dans `backups/`)
2. Arreter les containers:
   - `docker compose down`
3. Passer au bind mount (compose actuel):
   - `POSTGRES_DATA_DIR=./data/postgres` (ou par defaut `./data/postgres`)
4. Redemarrer Postgres:
   - `docker compose up -d`
5. Restaurer le dump:
   - `make restore BACKUP=backups/monassmat_YYYYMMDD_HHMMSS.dump`

### Transfert / sauvegarde des donnees
Deux options simples:
1. Copier le dossier de volume:
   - Copier `./data/postgres` vers `/volume1/docker/monassmat/pgdata` (NAS).
2. Dump SQL (recommande pour transfert):
   - Dump local:
     - `docker compose exec db pg_dump -U monassmat -d monassmat > monassmat.sql`
   - Restore sur NAS:
     - `cat monassmat.sql | docker compose exec -T db psql -U monassmat -d monassmat`
