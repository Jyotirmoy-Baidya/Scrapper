# SaaS API (FastAPI + MongoDB)

## Install
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

## Run
uvicorn app.main:app --reload

## Env
Copy .env.example to .env and set values.
