from datetime import datetime, timedelta, timezone


def compute_sm2_update(
    easiness_factor: float,
    interval_days: int,
    repetitions: int,
    quality: int,
) -> tuple[float, int, int, datetime]:
    """
    Standard SM-2 spaced repetition algorithm.
    quality: 0-5 (0-2 = forgotten/weak -> reset; 3-5 = recalled).
    """
    q = max(0, min(5, int(quality)))
    if q < 3:
        new_reps = 0
        new_interval = 1
    else:
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = max(1, round(interval_days * easiness_factor))
        new_reps = repetitions + 1

    new_ef = easiness_factor + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    new_ef = round(max(1.3, new_ef), 2)
    next_review = datetime.now(timezone.utc) + timedelta(days=new_interval)
    return new_ef, new_interval, new_reps, next_review
