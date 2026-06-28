import json
import litellm
from app.models import Settings

SYSTEM_PROMPT = """Du bist ein Assistent, der Rezepttexte in ein strukturiertes JSON-Format
für die Rezeptverwaltungssoftware Tandoor konvertiert.

Deine Aufgabe:
- Analysiere den eingegebenen Rezepttext (egal ob Fließtext, HTML, strukturiert oder halbfertig)
- Extrahiere alle relevanten Informationen
- Gib AUSSCHLIESSLICH valides JSON zurück, kein Markdown, keine Erklärungen, keine Codeblöcke

Das JSON muss exakt diesem Schema entsprechen:

{
  "name": "Rezeptname",
  "description": "Kurze Beschreibung (falls vorhanden, sonst leer)",
  "servings": 4,
  "servings_text": "Personen",
  "working_time": 20,
  "waiting_time": 40,
  "source_url": "",
  "keywords": [],
  "steps": [
    {
      "name": "Name des Abschnitts (leer lassen wenn nur ein Abschnitt)",
      "instruction": "Zubereitungstext des Abschnitts",
      "order": 0,
      "time": 0,
      "ingredients": [
        {
          "food": {"name": "Zutatname"},
          "unit": {"name": "g"},
          "amount": 100,
          "note": "z.B. gehackt",
          "no_amount": false,
          "order": 0
        }
      ]
    }
  ]
}

Regeln:
- working_time: Aktive Zubereitungszeit in Minuten (Schätzung ok)
- waiting_time: Passivzeit (Backen, Kochen, Kühlen) in Minuten
- Gibt es mehrere Komponenten (z.B. Sauce + Hauptgericht + Beilage), trenne sie in eigene steps mit aussagekräftigem name
- Gibt es nur einen logischen Abschnitt, ein steps-Element mit name ""
- Zutaten ohne Mengenangabe: amount=0, no_amount=true, unit=null
- Einheiten immer ausschreiben: "g", "ml", "EL", "TL", "Stück", "Pkt."
- Behalte die Formulierungen des Nutzers im instruction-Text soweit möglich bei – nur offensichtliche Tippfehler korrigieren
- source_url: nur befüllen wenn eine URL im Text vorkommt
- keywords: immer leeres Array []
- Schreibe den instruction-Text mit Leerzeilen zwischen Absätzen (\\n\\n)
- Gib NUR das JSON zurück, sonst nichts"""


def build_model_string(settings: Settings) -> str:
    provider = settings.ai_provider.lower()
    model = settings.ai_model
    mapping = {
        "anthropic": f"anthropic/{model}",
        "openai": model,
        "google gemini": f"gemini/{model}",
        "mistral": f"mistral/{model}",
        "groq": f"groq/{model}",
        "ollama": f"ollama/{model}",
    }
    return mapping.get(provider, model)


async def analyze_recipe(recipe_text: str, settings: Settings) -> dict:
    model_string = build_model_string(settings)
    kwargs = {
        "model": model_string,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": recipe_text},
        ],
        "temperature": 0.1,
    }
    if settings.ai_provider.lower() == "ollama":
        kwargs["api_base"] = settings.ollama_base_url
    elif settings.ai_api_key:
        kwargs["api_key"] = settings.ai_api_key

    response = await litellm.acompletion(**kwargs)
    raw = response.choices[0].message.content.strip()

    # Strip Markdown code fences if the AI wraps the output anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    return json.loads(raw)
