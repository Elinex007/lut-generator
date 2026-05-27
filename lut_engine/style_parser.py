import os
import json
from typing import Optional
import anthropic


SYSTEM_PROMPT = """Tu es un expert en étalonnage colorimétrique et en création de LUTs (Look-Up Tables).
À partir d'une description de style et de statistiques colorimétriques d'une vidéo source et d'une image de référence,
tu dois produire des paramètres précis pour construire une LUT.

Réponds UNIQUEMENT avec un JSON valide (aucun texte avant ou après), avec cette structure exacte :
{
  "temperature_shift": float,        // -1.0 (froid/bleu) à +1.0 (chaud/orange)
  "tint_shift": float,               // -1.0 (vert) à +1.0 (magenta)
  "exposure": float,                 // stops, -2.0 à +2.0
  "contrast": float,                 // -1.0 à +1.0
  "highlights": float,               // -1.0 à +1.0
  "shadows": float,                  // -1.0 à +1.0
  "saturation": float,               // -1.0 (N&B) à +1.0 (très saturé)
  "vibrance": float,                 // boost des couleurs peu saturées, -1.0 à +1.0
  "shadow_lift": float,              // 0.0 à 0.3 (matte/fade look)
  "highlight_roll": float,           // 0.0 à 0.3 (compression hautes lumières)
  "split_tone_shadow_hue": int,      // 0-360, teinte des ombres
  "split_tone_shadow_strength": float, // 0.0 à 1.0
  "split_tone_highlight_hue": int,   // 0-360, teinte des hautes lumières
  "split_tone_highlight_strength": float, // 0.0 à 1.0
  "grain_simulation": float,         // 0.0 à 1.0 (réduction de saturation locale simulant grain)
  "reasoning": "explication courte de tes choix"
}"""


def parse_style(description: str, source_stats: dict, ref_stats: Optional[dict]) -> dict:
    """
    Use Claude to interpret the style description and return LUT parameters.
    Falls back to rule-based defaults if API key not set.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _rule_based_fallback(description)

    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""Description du style demandé : "{description}"

Statistiques Lab de la vidéo source :
- Moyenne L/a/b : {source_stats['mean'].tolist()}
- Écart-type L/a/b : {source_stats['std'].tolist()}

{"Statistiques Lab de l'image de référence :" if ref_stats else "Pas d'image de référence fournie."}
{f"- Moyenne L/a/b : {ref_stats['mean'].tolist()}" if ref_stats else ""}
{f"- Écart-type L/a/b : {ref_stats['std'].tolist()}" if ref_stats else ""}

Génère les paramètres LUT optimaux pour atteindre ce style."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code blocks if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


def _rule_based_fallback(description: str) -> dict:
    """Simple keyword-based fallback when no API key is available."""
    desc = description.lower()
    params = {
        "temperature_shift": 0.0,
        "tint_shift": 0.0,
        "exposure": 0.0,
        "contrast": 0.0,
        "highlights": 0.0,
        "shadows": 0.0,
        "saturation": 0.0,
        "vibrance": 0.0,
        "shadow_lift": 0.0,
        "highlight_roll": 0.0,
        "split_tone_shadow_hue": 210,
        "split_tone_shadow_strength": 0.0,
        "split_tone_highlight_hue": 35,
        "split_tone_highlight_strength": 0.0,
        "grain_simulation": 0.0,
        "reasoning": "Fallback règles basiques (pas de clé API)"
    }

    if "chaud" in desc or "warm" in desc or "orange" in desc:
        params["temperature_shift"] = 0.4
    if "froid" in desc or "cold" in desc or "cool" in desc or "bleu" in desc:
        params["temperature_shift"] = -0.4
    if "cinéma" in desc or "cinema" in desc or "filmic" in desc:
        params["contrast"] = 0.2
        params["saturation"] = -0.1
        params["shadow_lift"] = 0.05
        params["highlight_roll"] = 0.1
    if "vintage" in desc or "rétro" in desc or "retro" in desc:
        params["temperature_shift"] = 0.2
        params["saturation"] = -0.2
        params["shadow_lift"] = 0.1
        params["split_tone_shadow_strength"] = 0.15
        params["split_tone_highlight_hue"] = 35
        params["split_tone_highlight_strength"] = 0.1
    if "noir" in desc or "noir et blanc" in desc or "black and white" in desc:
        params["saturation"] = -1.0
    if "contraste" in desc or "contrast" in desc:
        params["contrast"] = 0.4
    if "teal" in desc and ("orange" in desc):
        params["split_tone_shadow_hue"] = 195
        params["split_tone_shadow_strength"] = 0.25
        params["split_tone_highlight_hue"] = 35
        params["split_tone_highlight_strength"] = 0.2

    return params
