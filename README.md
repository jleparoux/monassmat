# monassmat
Le suivi simplifie des contrats d'assistante maternelle.

## Parcours utilisateur

- L'accueil `/contracts` donne la synthese du mois, l'action prioritaire et un apercu compact de chaque contrat.
- La vue `/contracts/{id}/overview` rassemble la prochaine action, l'avancement `calendrier → declaration → paiement`, les reperes du mois et les points a fiabiliser.
- Une navigation de contrat stable relie la vue d'ensemble, le calendrier, la declaration, les conges payes, la synthese, les paiements et les parametres.
- Le mois selectionne dans le calendrier est conserve lors du passage a la preparation de la declaration.
- Les parametres sont organises en informations, planning et remuneration; les paiements distinguent explicitement le versement reel des montants calcules.

## Calendrier
- Page: `/contracts/{id}/calendar`
- API workdays: `/api/contracts/{id}/workdays?start=YYYY-MM-DD&end=YYYY-MM-DD`
- Formulaire jour: `/contracts/{id}/day_form?day=YYYY-MM-DD`
- Synthese mensuelle: `/contracts/{id}/month_summary?start=YYYY-MM-DD&end=YYYY-MM-DD`
- Synthese annuelle: `/contracts/{id}/year_summary?year=YYYY`
- Page synthese annuelle: `/contracts/{id}/summary/year?year=YYYY`
- Preparation Pajemploi: `/contracts/{id}/pajemploi?month=YYYY-MM-01`
- Page liste contrats: `/contracts`
- Creation contrat: `/contracts/new`
- Types de journee: travail, absence, conge sans solde, jour ferie
- Parametres: chaque sauvegarde cree un snapshot date (champ "Application des parametres a partir du")
- Planning contractuel: les heures prevues sont renseignees pour chacun des sept jours et leur total doit correspondre aux heures hebdomadaires. Les anciens contrats restent volontairement sans planning jusqu'a leur prochaine saisie: aucune valeur n'est inventee pendant la migration.
- Semaines programmees: `/contracts/{id}/planned-weeks?year=YYYY`. Chaque semaine chevauchant l'annee est enregistree explicitement comme prevue ou non prevue; les annees historiques restent non configurees jusqu'a leur validation par l'utilisateur.
- Completude mensuelle: seuls les jours prevus par le planning contractuel doivent etre renseignes. Un mois est distingue comme planning manquant, a completer, a jour jusqu'a aujourd'hui ou complet. La preparation Pajemploi reste bloquee tant que le mois n'est pas complet.
- Synthese annuelle: les totaux agregent uniquement les mois complets. Les mois incomplets, futurs ou hors contrat ne sont jamais interpretes comme des mois reels a zero.

## Statut des calculs de remuneration

L'application est actuellement un outil de suivi, pas un logiciel de paie. Les
montants appeles "reperes de suivi" dans l'interface ne doivent pas etre
recopies tels quels dans Pajemploi.

Regles implementees et testees dans `calculations.py`:
- mensualisation: heures hebdomadaires x semaines programmees / 12 x taux;
- classification hebdomadaire: heures complementaires au-dela du contrat et
  jusqu'a 45 h, heures majorees au-dela de 45 h;
- deduction d'absence en accueil sur 52 semaines: salaire mensualise x heures
  d'absence / heures exactes du planning dans le mois.
- deduction d'absence en accueil sur 46 semaines ou moins: salaire mensualise
  x jours d'absence / jours habituels du planning dans le mois;
- champs Pajemploi sans absence: heures normales arrondies au plus proche et
  jours d'activite mensualises arrondis au-dessus;
- mois avec absence non remuneree: heures normales recalculees a partir de la
  remuneration due et jours d'activite reels.

La classification hebdomadaire et les deux formules de deduction sont branchees
au recapitulatif. Conformement a l'article 111, les semaines de non-accueil et
les jours feries chomes correspondant a un jour habituel restent comptes dans
le denominateur mensuel; la programmation annuelle ne modifie donc pas ce
calcul. L'interface signale tout planning contractuel manquant au lieu de
produire une approximation. L'ancien compteur de conges payes, fonde sur une
heuristique de jours saisis, a ete remplace par un compteur explicite. Aucun
solde n'est affiche tant que les faits necessaires ne permettent pas de le
calculer.

Le compteur de conges payes est disponible sur
`/contracts/{id}/paid-leave?year=YYYY` et dans la synthese annuelle. Il couvre:
- la periode d'acquisition du 1er juin au 31 mai;
- la premiere periode, de la date d'embauche au 31 mai suivant;
- l'acquisition de 2,5 jours ouvrables par equivalent de quatre semaines,
  arrondie au jour superieur et plafonnee a 30 jours de base;
- les jours supplementaires pour enfants a charge selon la tranche d'age;
- le decompte des jours pris du premier jour normalement travaille jusqu'a la
  veille de la reprise, hors dimanches et jours feries;
- l'imputation explicite sur droits acquis, par anticipation ou sans solde;
- les regularisations financieres qui rendent des jours au solde;
- la vue `acquis / pris / anticipes / regularises / restant`, sans persister
  ces totaux derives.

Le calcul automatique exige un planning stable et un calendrier complet. Une
base manuelle en mois complets ou en semaines et jours permet de reprendre un
decompte anterieur verifie. Ce mode est aussi a utiliser en cas de maladie,
suspension ou autre situation dont l'application ne peut pas determiner seule
l'assimilation. Quelle que soit la methode, le solde reste « a confirmer » tant
que l'utilisateur n'a pas atteste la base et la saisie de toutes les periodes
de conge. Les conges deja marques au calendrier mais non imputes sont signales.
Les anciens paiements restent conserves, mais leurs nombres de jours derives ne
sont pas reutilises comme un solde fiable.

Le taux net des heures complementaires est un fait contractuel explicite et
historise. Les contrats existants ne sont pas completes automatiquement: le
taux peut etre identique au taux de base ou avoir ete majore par accord ecrit.
Le coefficient de majoration des heures au-dela de 45 h/semaine est optionnel,
mais doit etre au minimum de 1,10 lorsqu'il est renseigne.

## Preparation Pajemploi

La fiche mensuelle rassemble les champs a recopier: periode, heures normales,
heures complementaires et majorees, jours d'activite, conges payes, salaire net,
entretien et repas. Un export dedie est disponible via
`/contracts/{id}/export/pajemploi.csv?month=YYYY-MM-01`.

La fiche distingue:
- les blocages qui empechent un calcul fiable (planning ou taux manquant,
  changement de parametres dans le mois, deduction d'absence incomplete);
- les controles manuels qui restent necessaires (conges
  payes en accueil sur 46 semaines ou moins, indemnites kilometriques).

Le parcours mensuel suit trois faits distincts: calendrier complet, declaration
Pajemploi confirmee, puis paiement enregistre. La confirmation de declaration
conserve uniquement le mois et la date declares; le statut du parcours est
toujours recalcule et n'est pas stocke. Elle peut etre annulee en cas d'erreur.
Apres paiement, l'utilisateur revient automatiquement sur le recapitulatif du
mois. Les valeurs fiables disposent d'un bouton de copie compatible avec le
serveur local HTTP du NAS.

Les conges payes verses sont ajoutes au salaire net lorsqu'un paiement de type
`paid_leave` couvre le mois. Leur nombre de jours doit encore etre verifie
manuellement. Les contrats prevoyant plus de 45 heures par semaine ne sont pas
encore pris en charge par la fiche. Le recapitulatif historique conserve son
libelle « repere de suivi » et ne remplace pas cette preparation declarative.

Sources officielles:
- [Convention collective, articles 96.4 et 108 a 111](https://www.legifrance.gouv.fr/conv_coll/id/KALIARTI000043942282)
- [Calcul et declaration de la remuneration](https://www.urssaf.fr/accueil/particulier/particulier-employeur/embaucher-un-salarie/remunerer-salarie-domicile.html)
- [Gestion des conges payes](https://www.urssaf.fr/accueil/particulier/particulier-employeur/gerer-les-absences/gestion-conges-payes.html)
- [Guide de declaration Pajemploi](https://www.urssaf.fr/accueil/services/services-particuliers/service-pajemploi/declarer-service-pajemploi.html)
- [Declaration par enfant depuis janvier 2026](https://www.urssaf.fr/accueil/actualites/pajemploi-declaration-par-enfant.html)

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
