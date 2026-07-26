"""State permainan: isi papan + giliran + status."""
from dataclasses import dataclass, field

from .board import BOARD, SIDES


class Status:
    """Nilai `GameState.status`."""

    PLAYING = "playing"
    A_WIN = "A_win"
    B_WIN = "B_win"
    DRAW = "draw"


def status_for_winner(winner):
    """`"A"`/`"B"`/`"draw"` -> nilai status."""
    return {"A": Status.A_WIN, "B": Status.B_WIN, "draw": Status.DRAW}[winner]


def winner_for_status(status):
    """Kebalikannya; None bila permainan masih berjalan."""
    return {Status.A_WIN: "A", Status.B_WIN: "B", Status.DRAW: "draw"}.get(status)


@dataclass
class Piece:
    """Satu bidak. Tidak ada pangkat selain raja."""

    owner: str  # "A" | "B"
    king: bool = False


@dataclass
class GameState:
    """Seluruh keadaan permainan pada satu saat."""

    board: dict
    turn: str = "A"
    move_no: int = 0
    status: str = Status.PLAYING
    # riwayat langkah, untuk ditampilkan / ditelusuri
    history: list = field(default_factory=list)
    # langkah berturut tanpa makan & tanpa promosi (jaring pengaman seri)
    since_progress: int = 0

    @classmethod
    def initial(cls, board=BOARD, first_turn="A"):
        cells = {n: None for n in board.nodes}
        for node, owner in board.start_pieces.items():
            cells[node] = Piece(owner=owner)
        return cls(board=cells, turn=first_turn)

    # -- pembacaan ----------------------------------------------------------
    def piece_at(self, node):
        return self.board.get(node)

    def is_empty(self, node):
        return self.board.get(node) is None

    def nodes_of(self, owner):
        """Node yang ditempati `owner`, terurut agar hasilnya deterministik."""
        return sorted(n for n, p in self.board.items() if p is not None and p.owner == owner)

    def count(self, owner):
        return sum(1 for p in self.board.values() if p is not None and p.owner == owner)

    def counts(self):
        """Jumlah bidak & raja per pemain (untuk panel status)."""
        out = {s: {"pieces": 0, "kings": 0} for s in SIDES}
        for p in self.board.values():
            if p is None:
                continue
            out[p.owner]["pieces"] += 1
            if p.king:
                out[p.owner]["kings"] += 1
        return out

    def is_over(self):
        """True bila permainan sudah berakhir (menang/kalah/seri)."""
        return self.status != Status.PLAYING

    def position_key(self):
        """Ringkasan posisi: susunan bidak + giliran.

        Dipakai untuk membandingkan papan dua sisi lewat jaringan.
        """
        parts = [
            f"{n}:{p.owner}{'K' if p.king else ''}"
            for n, p in sorted(self.board.items())
            if p is not None
        ]
        return f"{self.turn}|" + ",".join(parts)
