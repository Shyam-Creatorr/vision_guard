from difflib import SequenceMatcher
from pathlib import Path

from app.core.config import get_settings
from app.schemas.analysis import CandidateSuggestion

# Closed vocabulary per diagram topic / subject (from curated OpenStax-aligned knowledge base)
CLOSED_VOCABULARIES: dict[str, list[str]] = {
    "plant_cell": [
        "Cell Wall",
        "Cell Membrane",
        "Chloroplast",
        "Mitochondria",
        "Central Vacuole",
        "Nucleus",
        "Nucleolus",
        "Golgi Apparatus",
        "Endoplasmic Reticulum",
        "Ribosome",
        "Cytoplasm",
    ],
    "animal_cell": [
        "Cell Membrane",
        "Cytoplasm",
        "Nucleus",
        "Nucleolus",
        "Mitochondria",
        "Golgi Apparatus",
        "Endoplasmic Reticulum",
        "Ribosome",
        "Lysosome",
        "Centriole",
        "Vacuole",
    ],
    "human_heart": [
        "Right Atrium",
        "Right Ventricle",
        "Left Atrium",
        "Left Ventricle",
        "Aorta",
        "Superior Vena Cava",
        "Inferior Vena Cava",
        "Pulmonary Artery",
        "Pulmonary Vein",
        "Tricuspid Valve",
        "Mitral Valve",
        "Septum",
    ],
    "water_cycle": [
        "Evaporation",
        "Transpiration",
        "Condensation",
        "Precipitation",
        "Surface Runoff",
        "Infiltration",
        "Groundwater",
        "Collection",
    ],
    "digestive_system": [
        "Mouth",
        "Esophagus",
        "Stomach",
        "Liver",
        "Gallbladder",
        "Pancreas",
        "Small Intestine",
        "Large Intestine",
        "Rectum",
    ],
    "photosynthesis": [
        "Sunlight",
        "Chlorophyll",
        "Carbon Dioxide",
        "Water",
        "Glucose",
        "Oxygen",
        "Stomata",
        "Thylakoid",
    ],
    "simple_electric_circuit": [
        "Battery",
        "Switch",
        "Resistor",
        "Ammeter",
        "Voltmeter",
        "Light Bulb",
        "Conductor Wire",
    ],
    "atom_electron_shells": [
        "Proton",
        "Neutron",
        "Electron",
        "Nucleus",
        "Electron Shell",
        "Valence Shell",
    ],
}

SUBJECT_FALLBACK_VOCAB: dict[str, list[str]] = {
    "Biology": CLOSED_VOCABULARIES["plant_cell"] + CLOSED_VOCABULARIES["human_heart"] + CLOSED_VOCABULARIES["digestive_system"],
    "Earth Science": CLOSED_VOCABULARIES["water_cycle"],
    "Physics": CLOSED_VOCABULARIES["simple_electric_circuit"] + CLOSED_VOCABULARIES["atom_electron_shells"],
    "Chemistry": CLOSED_VOCABULARIES["atom_electron_shells"] + CLOSED_VOCABULARIES["photosynthesis"],
}


def get_closed_vocabulary(subject: str, topic_hint: str | None = None) -> list[str]:
    if topic_hint:
        norm = topic_hint.lower().replace("-", "_").replace(" ", "_")
        for key, vocab in CLOSED_VOCABULARIES.items():
            if key in norm or norm in key:
                return list(dict.fromkeys(vocab))
    base = SUBJECT_FALLBACK_VOCAB.get(subject, [])
    if not base:
        for vocab in CLOSED_VOCABULARIES.values():
            base.extend(vocab)
    return list(dict.fromkeys(base))


def generate_closed_vocab_suggestions(
    subject: str,
    topic_hint: str | None,
    partial_ocr_text: str,
    already_verified_labels: set[str],
    gemini_vision_pick: str | None = None,
    crop_path: str | Path | None = None,
) -> tuple[list[CandidateSuggestion], bool]:
    """
    Ranks closed-vocabulary candidates using:
      1) Fuzzy match of partial OCR chars against the closed vocabulary
      2) Optional Gemini vision classification restricted to the closed list (+ 'none of these')
      3) Elimination prior: downweights terms already verified elsewhere in the diagram
    Returns (up to 3 CandidateSuggestions with % confidence, no_reliable_suggestion).
    """
    settings = get_settings()
    vocab = get_closed_vocabulary(subject, topic_hint)
    verified_lower = {v.strip().lower() for v in already_verified_labels if v.strip()}
    ocr_clean = " ".join(partial_ocr_text.lower().split())

    scored: list[tuple[str, float, str]] = []
    for term in vocab:
        t_low = term.lower()
        # 1. Partial OCR fuzzy score (handles characters or fragments like "Gol__ App___")
        if ocr_clean:
            seq = SequenceMatcher(None, ocr_clean, t_low).ratio()
            # Prefix / token bonus
            tokens = [tok for tok in ocr_clean.replace("_", " ").split() if len(tok) >= 2]
            tok_bonus = sum(0.18 for tok in tokens if tok in t_low)
            ocr_score = min(1.0, seq + tok_bonus)
        else:
            ocr_score = 0.08

        # 2. Vision classification pick (restricted to closed list)
        vision_score = 0.0
        if gemini_vision_pick and gemini_vision_pick.lower() != "none of these":
            if gemini_vision_pick.strip().lower() == t_low:
                vision_score = 0.85

        raw_score = 0.65 * ocr_score + 0.35 * vision_score
        if not ocr_clean and not gemini_vision_pick:
            # Pure elimination prior across unverified slot cannot reliably guess
            raw_score = 0.12

        # 3. Elimination prior: downweight already-verified terms in this diagram
        if t_low in verified_lower:
            raw_score *= 0.12

        source = "ocr+elimination" if ocr_clean else "elimination_only"
        if vision_score > 0:
            source = "vision+ocr+elimination"
        scored.append((term, raw_score, source))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_raw = scored[0][1] if scored else 0.0
    if top_raw < settings.LEGIBILITY_SUGGESTION_FLOOR:
        return [], True

    top3 = scored[:3]
    total = sum(max(0.01, s[1]) for s in top3) or 1.0
    # Convert to calibrated percentages summing to <= 95% (never 100% for a guess!)
    scale = min(0.95, max(0.35, top_raw))
    candidates = [
        CandidateSuggestion(
            label=term,
            probability_pct=round((score / total) * scale * 100.0, 1),
            source=src,
        )
        for term, score, src in top3
    ]
    return candidates, False
