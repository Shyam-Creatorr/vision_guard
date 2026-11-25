from dataclasses import dataclass
import hashlib
import random
import re
import unicodedata

# Curated canonical aliases (synonyms, singular/plural, common scientific abbreviations)
KNOWN_ALIASES: dict[str, list[str]] = {
    "cell wall": ["plant cell wall", "cellulose wall"],
    "cell membrane": ["plasma membrane"],
    "chloroplast": ["chloroplasts"],
    "mitochondria": ["mitochondrion", "mitochondrial"],
    "central vacuole": ["vacuole", "large central vacuole"],
    "nucleus": ["cell nucleus", "nuclei"],
    "golgi apparatus": ["golgi body", "golgi complex", "golgi"],
    "endoplasmic reticulum": ["er", "rough er", "smooth er"],
    "ribosome": ["ribosomes"],
    "right atrium": ["ra", "right auricle"],
    "right ventricle": ["rv"],
    "left atrium": ["la", "left auricle"],
    "left ventricle": ["lv"],
    "aorta": ["aortic arch"],
    "evaporation": ["evaporate"],
    "condensation": ["condense"],
    "precipitation": ["precipitate", "rain"],
    "surface runoff": ["runoff", "run off"],
}

FALLBACK_DISTRACTOR_POOL = [
    "Ribosome",
    "Lysosome",
    "Cytoplasm",
    "Centriole",
    "Peroxisome",
    "Thylakoid",
    "Stomata",
    "Pulmonary Valve",
    "Tricuspid Valve",
    "Sublimation",
    "Transpiration",
    "Infiltration",
    "Aquifer",
    "Voltmeter",
    "Ammeter",
    "Resistor",
]


def normalize_label(text: str) -> str:
    """Unicode NFKC, casefold, strip punctuation/hyphens, collapse spaces, simple singularization."""
    s = unicodedata.normalize("NFKC", text or "").casefold().strip()
    s = re.sub(r"[-_/.,:;!?()'\"]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    words = s.split(" ")
    norm_words: list[str] = []
    for w in words:
        if len(w) >= 5 and w.endswith("es") and not w.endswith(("ses", "xes", "zes")):
            # e.g. classes vs leaves: keep simple trailing 's' safe stripping
            if w.endswith("s"):
                w = w[:-1]
        elif len(w) >= 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            w = w[:-1]
        norm_words.append(w)
    return " ".join(norm_words)


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def get_aliases_for_label(canonical: str) -> list[str]:
    key = canonical.strip().lower()
    aliases = list(KNOWN_ALIASES.get(key, []))
    return aliases


@dataclass
class ShuffledOption:
    option_id: str
    label: str


def build_unique_shuffled_options(
    blank_id: str,
    canonical_answer: str,
    raw_distractors: list[str],
    all_diagram_answers_and_aliases_norm: set[str],
    seed: int = 42,
) -> list[ShuffledOption]:
    """
    Builds 4 unique options (1 canonical + 3 distractors).
    Guarantees NO distractor equals any answer or alias of any blank in the same diagram.
    """
    ans_norm = normalize_label(canonical_answer)
    chosen: list[str] = [canonical_answer]
    seen_norm = {ans_norm}

    candidates = list(raw_distractors) + FALLBACK_DISTRACTOR_POOL
    for cand in candidates:
        c_clean = cand.strip()
        if not c_clean:
            continue
        c_norm = normalize_label(c_clean)
        if not c_norm or c_norm in seen_norm or c_norm in all_diagram_answers_and_aliases_norm:
            continue
        seen_norm.add(c_norm)
        chosen.append(c_clean)
        if len(chosen) == 4:
            break

    opts = [
        ShuffledOption(
            option_id=f"opt_{hashlib.sha1(f'{blank_id}:{lbl}'.encode('utf-8')).hexdigest()[:10]}",
            label=lbl,
        )
        for lbl in chosen
    ]
    rng = random.Random(f"{seed}:{blank_id}")
    rng.shuffle(opts)
    return opts


@dataclass
class GradeOutcome:
    status: str  # "correct" | "almost" | "wrong"
    credit: float
    normalized_input: str
    canonical_answer: str
    message: str


def grade_blank_answer(
    canonical_answer: str,
    accepted_aliases: list[str],
    submitted_answer: str,
    selected_option_id: str | None = None,
    option_lookup: dict[str, str] | None = None,
) -> GradeOutcome:
    """
    Pure single-source-of-truth grader.
    Compares by stable option_id (for MCQ/drag) or normalized canonical + alias text.
    """
    resolved_input = submitted_answer
    if selected_option_id and option_lookup is not None:
        resolved_input = option_lookup.get(selected_option_id, "")

    norm_in = normalize_label(resolved_input)
    norm_key = normalize_label(canonical_answer)
    norm_aliases = {normalize_label(a) for a in accepted_aliases if a.strip()}
    accepted_norms = {norm_key} | norm_aliases

    if not norm_in:
        return GradeOutcome(
            status="wrong",
            credit=0.0,
            normalized_input=norm_in,
            canonical_answer=canonical_answer,
            message=f"No answer submitted. Correct answer: {canonical_answer}.",
        )

    if norm_in in accepted_norms:
        return GradeOutcome(
            status="correct",
            credit=1.0,
            normalized_input=norm_in,
            canonical_answer=canonical_answer,
            message="Correct!",
        )

    # Typo tolerance: edit distance <= 1 for words >= 6 chars (only for typed input, not option_id mismatch)
    if not selected_option_id and len(norm_key) >= 6:
        for target in accepted_norms:
            if len(target) >= 6 and levenshtein_distance(norm_in, target) <= 1:
                return GradeOutcome(
                    status="almost",
                    credit=0.5,
                    normalized_input=norm_in,
                    canonical_answer=canonical_answer,
                    message=f"Almost, check your spelling (expected: {canonical_answer}).",
                )

    return GradeOutcome(
        status="wrong",
        credit=0.0,
        normalized_input=norm_in,
        canonical_answer=canonical_answer,
        message=f"Incorrect. Correct answer: {canonical_answer}.",
    )
