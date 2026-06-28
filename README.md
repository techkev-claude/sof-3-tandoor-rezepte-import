# Tandoor Recipe Importer

KI-gestützter Rezept-Importer für Tandoor. Rezepttext einfügen, per KI analysieren lassen, direkt in Tandoor importieren.

## Deployment via Portainer

1. Repository klonen oder als Stack-URL angeben
2. `.env.example` → `.env` kopieren und Werte anpassen
3. In Portainer: Stacks → Add Stack → Repository-URL eintragen
4. Stack deployen

## Lokales Setup

```bash
cp .env.example .env
# .env anpassen
mkdir -p data
docker-compose up -d
```

Aufruf: `http://localhost:${PORT}` (Standard: 8080)

## Erste Schritte

1. Mit `ADMIN_USER` / `ADMIN_PASSWORD` anmelden
2. Einstellungen: Tandoor-URL, API Key und KI-Provider konfigurieren
3. Rezepttext einfügen → Analysieren → JSON prüfen/bearbeiten → Übertragen

## Unterstützte KI-Provider

| Provider | Beispiel-Modell |
|---|---|
| OpenAI | `gpt-4o` |
| Anthropic | `claude-sonnet-4-6` |
| Google Gemini | `gemini-1.5-pro` |
| Mistral | `mistral-large-latest` |
| Groq | `llama-3.3-70b-versatile` |
| Ollama (lokal) | `llama3.1` |

## Umgebungsvariablen

| Variable | Beschreibung | Pflicht |
|---|---|---|
| `ADMIN_USER` | Benutzername | ja |
| `ADMIN_PASSWORD` | Passwort (wird gehasht gespeichert) | ja |
| `SECRET_KEY` | Signier-Key für Session-Tokens | ja |
| `DB_PATH` | Pfad zur SQLite-Datei im Container | ja |
| `PORT` | Externer Port | ja |
| `DATA_PATH` | Host-Pfad für Datenpersistenz | ja |
