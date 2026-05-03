#!/usr/bin/env bash
set -e

echo "=== MonAssmat — Installation ==="

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "Fichier .env créé depuis .env.example."
fi

echo ""
read -rp "Mot de passe PostgreSQL (laisser vide pour garder la valeur actuelle) : " pg_pass
if [ -n "$pg_pass" ]; then
  sed -i.bak "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$pg_pass/" .env && rm -f .env.bak
fi

read -rp "Clé secrète de l'application (laisser vide pour en générer une) : " secret_key
if [ -z "$secret_key" ]; then
  secret_key=$(python3 -c "import secrets; print(secrets.token_hex(32))")
fi
sed -i.bak "s/^SECRET_KEY=.*/SECRET_KEY=$secret_key/" .env && rm -f .env.bak

echo ""
echo "Démarrage des containers Docker..."
docker compose up -d --build

echo ""
echo "=== Installation terminée ==="
echo "Application disponible sur : http://localhost:8000"
