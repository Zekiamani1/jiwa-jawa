"""Rating pemain — Elo (non-linear).

Ekspektasi skor memakai fungsi **logistik**, jadi perubahan rating
bergantung pada selisih kekuatan kedua pemain, bukan penambahan tetap
(+10/-10):

    E_A = 1 / (1 + 10^((R_B - R_A) / 400))
    R_A' = R_A + K * (S_A - E_A),   S_A in {1, 0.5, 0}

Faktor K juga adaptif (pemain baru bergerak cepat, pemain mapan lambat),
sehingga perubahan rating ikut non-linear terhadap pengalaman.
"""
import json
import os
from dataclasses import dataclass, field

DEFAULT_RATING = 400
DEFAULT_STORE = "ratings.json"


def expected_score(rating_a, rating_b):
    """Ekspektasi skor A melawan B (fungsi logistik — non-linear)."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def k_factor(rating, games):
    """K adaptif ala FIDE."""
    if games < 10:
        return 40.0
    if rating >= 2000.0:
        return 16.0
    return 24.0


@dataclass
class PlayerRating:
    name: str
    rating: float = DEFAULT_RATING
    games: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0

    def to_dict(self):
        return {
            "rating": round(self.rating, 2),
            "games": self.games,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
        }

    @classmethod
    def from_dict(cls, name, d):
        return cls(
            name=name,
            rating=float(d.get("rating", DEFAULT_RATING)),
            games=int(d.get("games", 0)),
            wins=int(d.get("wins", 0)),
            losses=int(d.get("losses", 0)),
            draws=int(d.get("draws", 0)),
        )


@dataclass
class RatingResult:
    """Hasil satu perhitungan, per sisi ("A"/"B")."""

    ratings: dict = field(default_factory=dict)   # sisi -> rating baru
    delta: dict = field(default_factory=dict)     # sisi -> perubahan
    expected: dict = field(default_factory=dict)  # sisi -> ekspektasi skor


class RatingStore:
    """Penyimpanan rating persisten (`ratings.json`)."""

    def __init__(self, path=DEFAULT_STORE):
        self.path = path
        self.players = {}
        self.load()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, OSError):
            return
        self.players = {name: PlayerRating.from_dict(name, d) for name, d in raw.items()}

    def save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {name: p.to_dict() for name, p in sorted(self.players.items())},
                fh,
                indent=2,
                sort_keys=True,
            )
        os.replace(tmp, self.path)

    def get(self, name):
        if name not in self.players:
            self.players[name] = PlayerRating(name=name)
        return self.players[name]

    def rating_of(self, name):
        return self.get(name).rating

    def compute(self, name_a, name_b, winner):
        """Hitung rating baru tanpa menyimpan (murni, mudah diuji)."""
        pa, pb = self.get(name_a), self.get(name_b)
        score_a = {"A": 1.0, "B": 0.0, "draw": 0.5}[winner]

        exp_a = expected_score(pa.rating, pb.rating)
        exp_b = 1.0 - exp_a
        delta_a = k_factor(pa.rating, pa.games) * (score_a - exp_a)
        delta_b = k_factor(pb.rating, pb.games) * ((1.0 - score_a) - exp_b)

        return RatingResult(
            ratings={"A": pa.rating + delta_a, "B": pb.rating + delta_b},
            delta={"A": delta_a, "B": delta_b},
            expected={"A": exp_a, "B": exp_b},
        )

    def apply_result(self, name_a, name_b, winner, save=True):
        """Hitung lalu terapkan hasil ke store."""
        result = self.compute(name_a, name_b, winner)
        pa, pb = self.get(name_a), self.get(name_b)
        pa.rating = result.ratings["A"]
        pb.rating = result.ratings["B"]
        pa.games += 1
        pb.games += 1
        if winner == "A":
            pa.wins += 1
            pb.losses += 1
        elif winner == "B":
            pb.wins += 1
            pa.losses += 1
        else:
            pa.draws += 1
            pb.draws += 1
        if save:
            self.save()
        return result


def main(argv=None):  # pragma: no cover - utilitas CLI kecil
    import argparse

    parser = argparse.ArgumentParser(description="Papan peringkat Catur Jawa")
    parser.add_argument("--store", default=DEFAULT_STORE)
    args = parser.parse_args(argv)

    store = RatingStore(args.store)
    if not store.players:
        print(f"(belum ada rating di {args.store})")
        return 0
    print(f"{'PEMAIN':<20}{'RATING':>9}{'MAIN':>6}{'M':>4}{'K':>4}{'S':>4}")
    for p in sorted(store.players.values(), key=lambda p: -p.rating):
        print(f"{p.name:<20}{p.rating:>9.1f}{p.games:>6}{p.wins:>4}{p.losses:>4}{p.draws:>4}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
