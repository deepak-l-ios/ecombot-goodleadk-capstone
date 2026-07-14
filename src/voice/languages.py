"""
languages.py — Language registry for the eComBot voice pipeline
"""

from dataclasses import dataclass, field

@dataclass(frozen=True)
class Language:
    key: str                      # short selector, e.g. "en"
    name: str                     # human name, e.g. "English"
    lang_code: str                # language hint sent to the STT model
    greeting: str                 # spoken on startup
    sample_prompts: list[str] = field(default_factory=list)

LANGUAGES: dict[str, Language] = {
    "en": Language(
        key="en",
        name="English",
        lang_code="en",
        greeting="Hello! I'm eComBot. Ask me about your order or a product.",
        sample_prompts=[
            "Where is my order ORD zero zero one?",
            "Cancel order ORD zero zero two.",
            "Recommend a noise-cancelling headphone under two hundred dollars.",
            "What is your return policy?",
        ],
    ),
    "hi": Language(
        key="hi",
        name="Hindi",
        lang_code="hi",
        greeting="नमस्ते! मैं eComBot हूँ। अपना ऑर्डर या प्रोडक्ट पूछें।",
        sample_prompts=[
            "मेरा ऑर्डर ORD शून्य शून्य एक कहाँ है?",
            "दो सौ डॉलर से कम में नॉइज़ कैंसलिंग हेडफ़ोन सुझाएं।",
        ],
    ),
}

def get_language(key: str) -> Language:
    key = (key or "en").strip().lower()
    if key not in LANGUAGES:
        valid = ", ".join(LANGUAGES)
        raise ValueError(f"Unknown language '{key}'. Choose one of: {valid}")
    return LANGUAGES[key]
