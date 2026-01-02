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
- Types de journee: travail, absence, conge sans solde, jour ferie
- Parametres: chaque sauvegarde cree un snapshot date (champ "Application des parametres a partir du")

## Import assmat-tracker
- Script: `scripts/import_assmat_tracker.py`
- Import: `--month-file` ou `--months-dir` (avec `settings.json` optionnel)
- Jours feries: charge `holidays-YYYY.json` dans le meme dossier (ou via `--holidays-file` / `--holidays-dir`) et force le statut `ferie` lors de l'import
 - Statuts importes: travail, conge assmat, conge parent (absence), conge sans solde, ferie
