# PostgreSQL Setup Guide

Follow the steps below to run the web scraper project with a PostgreSQL database instead of the default SQLite file. The instructions assume you are working on a local development machine.

## 1. Install PostgreSQL and client tools

Install PostgreSQL for your operating system:

- **Ubuntu / Debian**
  ```bash
  sudo apt update
  sudo apt install postgresql postgresql-contrib libpq-dev
  ```
- **macOS (Homebrew)**
  ```bash
  brew update
  brew install postgresql
  brew services start postgresql
  ```
- **Windows**
  Download the installer from [postgresql.org/download](https://www.postgresql.org/download/) and follow the guided setup. Be sure to include the `psql` command-line tool.

## 2. Install Python dependencies

The project relies on `psycopg2-binary` to communicate with PostgreSQL. Install the dependencies after activating your virtual environment:

```bash
pip install -r requirements.txt psycopg2-binary
```

> `psycopg2-binary` is convenient for local development. For production deployments you should switch to `psycopg2` and compile it against your system libraries.

## 3. Create the database and user

Log in to PostgreSQL as the superuser (`postgres` by default) and create a dedicated database and user for the app:

```bash
sudo -u postgres psql
```

Inside the `psql` prompt run:

```sql
CREATE DATABASE web_scraper;
CREATE USER web_scraper WITH PASSWORD 'change-me';
ALTER ROLE web_scraper SET client_encoding TO 'UTF8';
ALTER ROLE web_scraper SET default_transaction_isolation TO 'read committed';
ALTER ROLE web_scraper SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE web_scraper TO web_scraper;
\q
```

If you are on Windows or macOS with Homebrew, open a terminal and use `psql` without the `sudo` prefix:

```bash
psql -U postgres
```

## 4. Configure environment variables

Copy the example environment file and update it with your PostgreSQL credentials:

```bash
cp .env.example .env
```

Then edit `.env` to include:

```bash
DB_ENGINE=django.db.backends.postgresql
DB_NAME=web_scraper
DB_USER=web_scraper
DB_PASSWORD=change-me
DB_HOST=127.0.0.1
DB_PORT=5432
```

Additional optional settings:

- `DB_CONN_MAX_AGE`: keep database connections open for the given number of seconds (defaults to 60).
- `DB_SSLMODE`: set to `require` when connecting to managed Postgres services that enforce SSL.

The Django settings automatically load `.env`, so no further code changes are needed.

## 5. Run migrations

Apply the database schema to your PostgreSQL instance:

```bash
python manage.py migrate
```

If you already ran migrations using SQLite, Django will handle applying them to PostgreSQL as long as the database is empty.

## 6. Verify the connection

Start the development server and ensure the crawler can persist data:

```bash
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` and perform a crawl. Check the database to confirm rows were saved:

```bash
psql -U web_scraper -d web_scraper -c "SELECT id, target_url, created_at FROM crawler_crawlrun ORDER BY created_at DESC LIMIT 5;"
```

If you see recent runs listed, PostgreSQL is connected correctly.

## 7. Troubleshooting tips

- **Authentication failures**: ensure the credentials in `.env` match the PostgreSQL user and that the server is running.
- **Firewall or network errors**: confirm that the database host and port are reachable from your machine.
- **SSL related errors**: adjust `DB_SSLMODE` (e.g., `require`, `disable`) depending on your environment.
- **Package installation issues on macOS**: install the PostgreSQL libraries via Homebrew (`brew install postgresql`) before installing `psycopg2`.

With these steps, the application will store crawl history and downloaded document metadata in PostgreSQL.
