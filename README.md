# SportBi

**SportBi** est une plateforme de Business Intelligence sportive combinant :

* collecte de données sportives automatisée
* stockage dans une base PostgreSQL
* API d’analyse et de visualisation
* interface d’exploration
* requêtes en langage naturel (NLP → SQL)

Le projet est entièrement conteneurisé avec **Docker Compose** et conçu pour des démonstrations de data engineering, BI et IA appliquées au sport.

---

## Fonctionnalités principales

* Scraping de données sportives (football, NBA, etc.)
* Stockage structuré dans PostgreSQL
* API REST pour requêtes analytiques et graphiques
* Interface d’exploration des données
* Requêtes en langage naturel converties en SQL
* Architecture modulaire et conteneurisée

---

## Architecture du projet

```
SportBi
│
├── api/          → API REST + NLP
├── db/           → Initialisation de la base PostgreSQL
├── explorer/     → Interface d’exploration (Streamlit)
├── scraper/      → Collecte et ingestion des données
├── docker-compose.yml
```

### Composants

| Service           | Description                                     |
| ----------------- | ----------------------------------------------- |
| **db**            | Base PostgreSQL contenant les données sportives |
| **scraper**       | Scrapers et scripts d’ingestion                 |
| **lbwl_api**      | API REST + moteur NLP                           |
| **lbwl_explorer** | Interface web d’exploration                     |

---

## Stack technique

### Backend

* Python
* FastAPI (API)
* SQLAlchemy
* PostgreSQL

### Data & Scraping

* Scripts Python de scraping
* Ingestion automatisée

### NLP

* OpenAI (LLM pour requêtes naturelles)
* Sentence Transformers (index sémantique)

### Frontend

* Streamlit (explorateur de données)

### Infra

* Docker
* Docker Compose

---

## Installation

### Prérequis

* Docker
* Docker Compose

---

## Lancement du projet

Depuis la racine du projet :

```bash
docker-compose up --build
```

### Services exposés

| Service    | URL                   | Port |
| ---------- | --------------------- | ---- |
| API        | http://localhost:8080 | 8080 |
| Explorer   | http://localhost:8501 | 8501 |
| PostgreSQL | localhost:5432        | 5432 |

---

## Base de données

La base est initialisée automatiquement via :

```
db/init.sql
```

Configuration par défaut :

| Variable    | Valeur    |
| ----------- | --------- |
| DB_NAME     | lbwl      |
| DB_USER     | lbwl_user |
| DB_PASSWORD | lbwl_pass |

---

## API REST

### Endpoint principal

#### Charts

```
GET /charts
```

Permet de générer des graphiques à partir de requêtes analytiques.

---

### NLP Query (langage naturel)

```
POST /nlpq
```

Exemple de requête :

```json
{
  "question": "Top 10 équipes avec le plus de victoires"
}
```

Le système :

1. Analyse la question
2. Génère une requête SQL
3. Exécute la requête
4. Retourne les résultats

---

## Tests rapides

### Test API charts

```bash
./test_api.sh
```

### Test NLP

```bash
./test_nlpq.sh
```

### Test agent NLP

```bash
./test_nlpq_agent.sh
```

---

## Scraper

Le service `scraper` collecte les données sportives et les injecte dans la base.

### Sources gérées

* Football
* NBA
* Autres ligues (selon scripts)

Scripts principaux :

```
scraper/
├── main.py
├── football_data_scraper.py
├── nba_scraper.py
├── openfootball_scraper.py
```

---

## Explorer (interface BI)

Interface web basée sur **Streamlit** permettant :

* exploration des tables
* visualisation de données
* requêtes interactives

Accès :

```
http://localhost:8501
```

---

## Variables d’environnement importantes

### API

| Variable       | Description         |
| -------------- | ------------------- |
| OPENAI_API_KEY | Clé API OpenAI      |
| OPENAI_MODEL   | Modèle LLM utilisé  |
| NLP_MODEL_NAME | Modèle d’embeddings |

---

## Exemple de flux de données

```
Scraper → PostgreSQL → API → Explorer / NLP
```

1. Le scraper collecte les données sportives
2. Les données sont stockées dans PostgreSQL
3. L’API expose des endpoints analytiques
4. L’utilisateur interagit :

   * via l’explorer
   * via des requêtes en langage naturel

---

## Structure détaillée

```
api/
 ├── main.py
 ├── routes/
 │   ├── charts.py
 │   └── nlpq.py
 ├── services/
 │   ├── charts.py
 │   ├── llm_agent.py
 │   ├── nlp_pipeline.py
 │   └── query.py

db/
 └── init.sql

explorer/
 └── app.py

scraper/
 ├── main.py
 ├── nba_scraper.py
 ├── football_data_scraper.py
 └── ...
```

---

## Cas d’usage

* Démo de plateforme BI sportive
* Portfolio data / IA
* Projet de data engineering
* Prototype d’assistant analytique

---

## Roadmap possible

* Authentification utilisateur
* Tableau de bord avancé
* Ajout d’autres sports
* Caching des requêtes NLP
* Historique des analyses

---

## Contribution

1. Fork du projet
2. Création d’une branche :

```bash
git checkout -b feature/nouvelle-fonctionnalite
```

3. Commit :

```bash
git commit -m "Ajout nouvelle fonctionnalité"
```

4. Push et Pull Request

---

## Licence

Projet open source — licence à définir.
