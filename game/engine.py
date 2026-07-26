"""GameEngine — satu pintu masuk untuk GUI / jaringan.

Engine menyimpan state, memvalidasi langkah, mencatat log, dan mendeteksi
akhir permainan. Engine tidak tahu-menahu soal jaringan: lapisan transport
memanggil `legal_moves()` / `apply_move()` yang sama seperti GUI.
"""
import uuid
from dataclasses import dataclass, field

from . import rules
from .board import BOARD, other_side
from .logger import Event, Logger
from .rules import IllegalMove, Reason
from .state import GameState


@dataclass
class MoveResult:
    """Ringkasan apa yang terjadi akibat satu aksi."""

    events: list = field(default_factory=list)
    game_over: bool = False
    winner: str = None   # "A" | "B" | "draw" | None
    reason: str = None


class GameEngine:
    """Mesin permainan Dam-daman."""

    def __init__(
        self,
        names=None,
        log_dir="logs",
        enable_log=True,
        rating_store=None,
        first_turn="A",
        player=None,
    ):
        self.board = BOARD
        self.names = names or {"A": "pemain-A", "B": "pemain-B"}
        self.rating_store = rating_store
        self.game_id = str(uuid.uuid4())
        self.player = player
        self.state = GameState.initial(self.board, first_turn=first_turn)
        self.logger = Logger(self.game_id, log_dir=log_dir, enabled=enable_log)
        self._callbacks = []
        self._started = False
        # diisi bila ada langkah non-makan padahal kesempatan makan tersedia
        self.pending_dam_offender = None

    # -- event --------------------------------------------------------------
    def on_event(self, cb):
        """Daftarkan callback yang dipanggil untuk tiap event log."""
        self._callbacks.append(cb)

    def _emit(self, actor, event, detail=None):
        ev = self.logger.emit(actor, event, detail or {})
        for cb in self._callbacks:
            try:
                cb(ev)
            except Exception:  # callback GUI tidak boleh menjatuhkan engine
                pass
        return ev

    # -- siklus permainan ---------------------------------------------------
    def start(self):
        """Tandai permainan dimulai (emit `game_start`). Idempoten."""
        res = MoveResult()
        if self._started:
            return res
        self._started = True
        res.events.append(
            self._emit(
                self.state.turn,
                Event.GAME_START,
                {"first_turn": self.state.turn, "names": self.names},
            )
        )
        return res

    # -- aturan -------------------------------------------------------------
    def legal_moves(self):
        """Langkah legal untuk pemain yang sedang giliran."""
        return rules.legal_moves(self.state, self.board)

    def legal_moves_from(self, node):
        """Langkah legal yang berawal dari `node` (dipakai GUI)."""
        return rules.moves_from(self.state, node, self.board)

    def has_capture(self):
        return rules.has_capture(self.state, self.board)

    def apply_move(self, move):
        """Terapkan langkah pemain yang sedang giliran. Validasi penuh."""
        effect = rules.apply_move(self.state, move, self.board)
        res = MoveResult()

        res.events.append(
            self._emit(
                effect.actor,
                Event.MOVE,
                {
                    "move_no": self.state.move_no,
                    **effect.move.to_dict(),
                    "text": effect.move.describe(),
                },
            )
        )
        if effect.captured:
            res.events.append(
                self._emit(
                    effect.actor,
                    Event.CAPTURE,
                    {"move_no": self.state.move_no, "captured": effect.captured},
                )
            )
        if effect.promoted:
            res.events.append(
                self._emit(
                    effect.actor,
                    Event.PROMOTION,
                    {"move_no": self.state.move_no, "node": effect.move.to},
                )
            )

        # Catat siapa yang mengabaikan kesempatan makan; lawan boleh DAM.
        self.pending_dam_offender = effect.actor if effect.ignored_capture else None

        self._finish_if_over(res)
        return res

    def resign(self, side=None):
        """Pemain `side` (default: yang sedang giliran) menyerah."""
        res = MoveResult()
        if self.state.is_over():
            return res
        loser = side or self.state.turn
        self._declare_over(res, other_side(loser), Reason.RESIGN)
        return res

    def call_dam(self, removed):
        """Ambil pion pihak yang mengabaikan kesempatan makan (maks 3)."""
        res = MoveResult()
        offender = self.pending_dam_offender
        if offender is None:
            raise IllegalMove("tidak ada kesempatan makan yang diabaikan")
        info = rules.apply_dam(self.state, offender, removed)
        self.pending_dam_offender = None
        res.events.append(
            self._emit(
                other_side(offender),
                Event.DAM,
                {"offender": offender, "removed": list(removed), "pieces": info},
            )
        )
        self._finish_if_over(res)
        return res

    def skip_dam(self):
        """Lepaskan hak DAM tanpa mengambil pion."""
        self.pending_dam_offender = None

    # -- akhir permainan ----------------------------------------------------
    def _finish_if_over(self, res):
        outcome = rules.detect_outcome(self.state, self.board)
        if outcome is not None:
            self._declare_over(res, *outcome)

    def _declare_over(self, res, winner, reason):
        rules.set_outcome(self.state, winner)
        res.game_over = True
        res.winner = winner
        res.reason = reason
        res.events.append(
            self._emit(winner, Event.GAME_OVER, {"winner": winner, "reason": reason})
        )
        self._update_rating(res)

    def _update_rating(self, res):
        if self.rating_store is None or res.winner is None:
            return
        result = self.rating_store.apply_result(
            self.names["A"], self.names["B"], res.winner
        )
        res.events.append(
            self._emit(
                res.winner,
                Event.RATING_UPDATE,
                {
                    "names": self.names,
                    "ratings": result.ratings,
                    "delta": result.delta,
                    "expected": result.expected,
                    "formula": "elo-logistic",
                },
            )
        )
