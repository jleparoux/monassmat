# MonAssmat — Guide d'installation

MonAssmat est une application de suivi des contrats d'assistante maternelle, déployée via Docker.

---

## 1. Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (PC, Mac) ou Docker Engine (Linux)
- Docker Compose (inclus dans Docker Desktop)

Vérifiez que Docker est bien installé :

```bash
docker --version
docker compose version
```

---

## 2. Installation rapide (PC / Mac / Linux)

1. Extrayez l'archive du projet dans un dossier de votre choix, ou clonez le dépôt :

   ```bash
   git clone <url-du-repo> monassmat
   cd monassmat
   ```

2. Lancez le script d'installation interactif :

   ```bash
   ./setup.sh
   ```

   Le script va :
   - Créer votre fichier `.env` depuis `.env.example` (si absent)
   - Vous demander un mot de passe PostgreSQL (optionnel)
   - Générer automatiquement une clé secrète sécurisée
   - Démarrer les containers Docker

3. Ouvrez votre navigateur sur :

   ```
   http://localhost:8000
   ```

---

## 3. Installation sur Synology NAS (Container Manager)

1. Copiez le dossier du projet sur le NAS, par exemple dans `/volume1/docker/monassmat/`.

2. Copiez `.env.example` en `.env` et modifiez-le si nécessaire :

   ```bash
   cp .env.example .env
   ```

3. Dans le fichier `.env`, définissez le chemin de stockage des données Postgres sur le NAS :

   ```
   POSTGRES_DATA_DIR=/volume1/docker/monassmat/pgdata
   ```

4. Ouvrez **Container Manager** sur l'interface DSM de votre Synology.

5. Allez dans **Projet** > **Créer**.

6. Sélectionnez le dossier du projet et le fichier `docker-compose.yml`.

7. Dans l'onglet **Variables d'environnement**, ajoutez :
   - `POSTGRES_DATA_DIR` = `/volume1/docker/monassmat/pgdata`

8. Lancez le projet (**Build + Run**).

9. L'application est accessible sur votre réseau local :

   ```
   http://IP_DU_NAS:8000
   ```

---

## 4. Backup et restauration

### Option A — Copier le dossier de données (simple)

Sauvegardez le dossier `./data/postgres` (ou le chemin défini par `POSTGRES_DATA_DIR`). Pour restaurer, remplacez ce dossier et redémarrez les containers.

### Option B — Dump SQL (recommandé pour transfert)

**Backup :**

```bash
python scripts/db_backup.py
```

Génère un fichier `.dump` et un fichier `.sql` dans le dossier `backups/`.

**Restore :**

```bash
python scripts/db_restore.py --input backups/monassmat_YYYYMMDD_HHMMSS.dump
```

Options avancées :
- `--mode local` — exécute en local sans Docker
- `--data-only` / `--schema-only` — dump/restore partiel
- `--sql-output backups/monassmat.sql` — export lisible en complément

Via Makefile (si disponible) :

```bash
make backup
make restore BACKUP=backups/monassmat_YYYYMMDD_HHMMSS.dump
```

---

## 5. Transfert PC → NAS (pas à pas)

### Prérequis

- Docker fonctionne sur le NAS (Container Manager).
- Le fichier `docker-compose.yml` est copié sur le NAS (ex : `/volume1/docker/monassmat/`).
- Un dossier persistant Postgres existe sur le NAS (ex : `/volume1/docker/monassmat/pgdata`).

### Étapes

1. **Sur le PC**, créez un dump SQL lisible :

   ```bash
   python scripts/db_backup.py --sql-output backups/monassmat.sql
   ```

2. **Copiez** le fichier vers le NAS (via File Station, SCP, ou clé USB) :

   ```
   backups/monassmat.sql  →  /volume1/docker/monassmat/monassmat.sql
   ```

3. **Sur le NAS**, définissez le volume Postgres dans `.env` :

   ```
   POSTGRES_DATA_DIR=/volume1/docker/monassmat/pgdata
   ```

4. **Lancez** les containers sur le NAS :

   ```bash
   docker compose up -d --build
   ```

5. **Importez** les données dans Postgres (sur le NAS) :

   ```bash
   cat /volume1/docker/monassmat/monassmat.sql | docker compose exec -T db psql -U monassmat -d monassmat
   ```

### Alternative — copie directe du volume

1. Arrêtez les containers sur le NAS.
2. Copiez le dossier `./data/postgres` du PC vers `/volume1/docker/monassmat/pgdata` sur le NAS.
3. Relancez les containers :

   ```bash
   docker compose up -d
   ```

---

## 6. Mise à jour

Pour mettre à jour l'application vers une nouvelle version :

```bash
docker compose pull
docker compose up -d --build
```

Vos données sont conservées dans le dossier défini par `POSTGRES_DATA_DIR` et ne sont pas affectées par la mise à jour.

---

## 7. Import depuis assmat-tracker

Si vous utilisez l'application assmat-tracker, un script d'import est disponible :

```bash
python scripts/import_assmat_tracker.py --months-dir <dossier-des-mois>
```

Options :
- `--month-file` — importer un seul fichier mensuel
- `--months-dir` — importer tous les fichiers d'un dossier (avec `settings.json` optionnel)
- Les jours fériés sont automatiquement détectés depuis les fichiers `holidays-YYYY.json`

Consultez le script pour les options avancées.
