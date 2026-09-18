# Saarthi-MG Backend Foundation

This is the foundational backend and data layer for the AI Multigrade Classroom Orchestrator. 
Currently it implements Part 1: Core database models, migrations, CRUD APIs, and basic constraints.

## Requirements
- Docker and Docker Compose (or local Postgres + Python 3.12)

## Setup and Run

1. **Environment Setup**
   ```bash
   cp .env.example .env
   ```

2. **Start the Database**
   ```bash
   docker compose up -d db
   ```

3. **Run Migrations (Alembic)**
   Run this locally if you have the venv installed, or inside the API container once it's up.
   To run inside docker:
   ```bash
   docker compose run --rm api alembic upgrade head
   ```

4. **Seed the Database**
   ```bash
   docker compose run --rm api python -m app.db.seed
   ```

5. **Start the API Server**
   ```bash
   docker compose up -d api
   ```
   The API will be available at `http://localhost:8000`. Swagger docs are at `http://localhost:8000/docs`.

6. **Run Tests**
   ```bash
   docker compose run --rm api pytest
   ```
