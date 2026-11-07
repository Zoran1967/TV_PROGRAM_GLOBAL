"""Emisija koja je trenutno na programu ("Sada") i sledeca ("Sledece").

Racuna se nad CELOM listom emisija (ne samo nad danasnjim danom), pa u 23:50
"Sledece" moze da bude emisija posle ponoci. Oznaka se daje samo kada raspored
to potvrdjuje:

- "Sada": emisija koja je pocela i cije je vreme zavrsetka poznato i jos nije
  proslo. Ako izvor ne daje kraj, kraj je pocetak sledece emisije (oznaceno kao
  izvedeno). Poslednja emisija bez kraja se ne oznacava kao "Sada".
- Ako se emisije preklapaju, "Sada" je ona koja je poslednja pocela.
- Rupa u rasporedu: nema "Sada", a "Sledece" je prva emisija koja tek pocinje.
"""

from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional

from app.models.schedule import Programme


@dataclass(frozen=True)
class NowNext:
    current: Optional[Programme] = None
    # Kraj trenutne emisije (UTC); izveden ako izvor nije dao kraj
    current_end_utc: Optional[int] = None
    current_end_derived: bool = False
    progress: Optional[float] = None  # 0..1
    next: Optional[Programme] = None


def compute_now_next(programmes, now_utc):
    """programmes: lista Programme sortirana po pocetku; now_utc: UTC sekunde."""
    if not programmes:
        return NowNext()
    starts = [item.start_utc for item in programmes]
    index = bisect_right(starts, now_utc) - 1  # poslednja emisija koja je pocela
    following = programmes[index + 1] if index + 1 < len(programmes) else None
    if index < 0:
        return NowNext(next=following)

    candidate = programmes[index]
    end, derived = candidate.end_utc, False
    if end is None and following is not None:
        end, derived = following.start_utc, True
    if end is None or now_utc >= end:
        return NowNext(next=following)

    length = end - candidate.start_utc
    progress = (now_utc - candidate.start_utc) / length if length > 0 else None
    return NowNext(candidate, end, derived, progress, following)
