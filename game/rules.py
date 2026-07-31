"""Aturan permainan Dam-daman (Jawa).

Mengikuti aturan Wikibooks "Permainan Tradisional Catur di Indonesia /
Dam-daman (Jawa)":

  1. Tiap giliran pemain memilih SALAH SATU: jalan satu langkah, atau
     memakan satu pion lawan di sebelahnya.
  2. Pion jalan satu langkah ke depan, samping, atau diagonal (tidak
     mundur). Yang boleh maju-mundur hanya raja.
  3. Makan = melangkahi SATU pion lawan. Tidak ada rantai lompatan.
  4. Pion yang sampai garis terakhir daerah lawan menjadi raja; raja
     bergerak satu langkah ke tetangga langsung sama seperti pion,
     hanya saja raja boleh mundur.
  5. Makan tidak wajib. Tapi kalau ada kesempatan makan dan diabaikan,
     lawan berhak mengambil 3 pion pihak yang abai secara bebas (DAM).
  6. Menang bila seluruh pion lawan habis.

Tidak ada opsi/varian — aturannya cuma satu, yang di atas.

Konvensi `Move`:
  - `frm`      : node asal.
  - `to`       : node tujuan.
  - `captured` : node korban, atau None bila langkah biasa.
  - `promote`  : True bila langkah ini mempromosikan bidak jadi raja.
"""
from dataclasses import dataclass

from .board import BOARD, other_side
from .state import status_for_winner
DAM_REMOVAL = 3

DRAW_NO_PROGRESS = 50


class IllegalMove(Exception):
    """Langkah tidak legal menurut aturan."""


class Reason:
    """Alasan permainan berakhir."""

    NO_PIECES = "no_pieces"
    NO_MOVES = "no_moves"
    RESIGN = "resign"
    NO_PROGRESS = "no_progress"


@dataclass(frozen=True)
class Move:
    """Satu aksi dalam satu giliran: jalan, atau makan satu pion."""

    frm: str
    to: str
    captured: str = None
    promote: bool = False

    def to_dict(self):
        return {
            "from": self.frm,
            "to": self.to,
            "captured": self.captured,
            "promote": self.promote,
        }

    def describe(self):
        """Deskripsi terbaca manusia (untuk log & GUI)."""
        if self.captured:
            bits = [f"{self.frm} x {self.to}", f"makan {self.captured}"]
        else:
            bits = [f"{self.frm} -> {self.to}"]
        if self.promote:
            bits.append("PROMOSI")
        return " | ".join(bits)


@dataclass
class MoveEffect:
    """Apa yang terjadi akibat sebuah langkah (bahan untuk logging)."""

    actor: str
    move: Move
    captured: list  # [{node, owner, king}] — kosong atau satu elemen
    promoted: bool
    ignored_capture: bool = False


def capture_moves(state, board=BOARD):
    """Semua langkah makan untuk pemain yang sedang giliran.

    Satu langkah = satu korban. Tidak ada rantai.
    """
    owner = state.turn
    moves = []
    for start in state.nodes_of(owner):
        piece = state.board[start]
        # Pion dan raja sama-sama melangkahi tetangga langsung, mendarat
        # tepat di baliknya. Bedanya: raja boleh makan ke segala arah,
        # pion hanya ke arah maju.
        for nb, direction in board.neighbors[start]:
            if not piece.king and not board.is_forward(owner, direction):
                continue
            victim = state.board.get(nb)
            if victim is None or victim.owner == owner:
                continue
            landing = board.step(nb, direction)
            if landing is None or state.board.get(landing) is not None:
                continue
            moves.append(
                Move(
                    frm=start,
                    to=landing,
                    captured=nb,
                    promote=(not piece.king) and board.is_promotion(owner, landing),
                )
            )
    return moves


def quiet_moves(state, board=BOARD):
    """Semua langkah biasa (tanpa makan) untuk pemain yang sedang giliran."""
    owner = state.turn
    moves = []
    for start in state.nodes_of(owner):
        piece = state.board[start]
        for nb, direction in board.neighbors[start]:
            if state.board.get(nb) is not None:
                continue
            # Pion tidak boleh mundur; raja boleh ke segala arah — tapi
            # tetap satu langkah ke tetangga langsung, sama seperti pion.
            if not piece.king and not board.is_forward(owner, direction):
                continue
            moves.append(
                Move(
                    frm=start,
                    to=nb,
                    promote=(not piece.king) and board.is_promotion(owner, nb),
                )
            )
    return moves


def _sorted(moves):
    """Urutan deterministik supaya daftar langkah selalu sama."""
    return sorted(moves, key=lambda m: (m.frm, m.to, m.captured or "", m.promote))


def legal_moves(state, board=BOARD):
    """Langkah legal untuk pemain yang sedang giliran.

    Makan TIDAK wajib: langkah biasa tetap ada di daftar meski ada
    kesempatan makan. Konsekuensinya diurus lewat hukuman DAM.
    """
    if state.is_over():
        return []
    return _sorted(capture_moves(state, board) + quiet_moves(state, board))


def moves_from(state, node, board=BOARD):
    """Langkah legal yang berawal dari `node` (dipakai GUI untuk sorotan)."""
    return [m for m in legal_moves(state, board) if m.frm == node]


def has_capture(state, board=BOARD):
    """True bila pemain yang sedang giliran punya kesempatan makan."""
    return bool(capture_moves(state, board))


def find_legal(state, move, board=BOARD):
    """Cari padanan kanonik `move` di daftar legal; None bila tidak ada.

    Flag `promote` yang dikirim pemanggil diabaikan — promosi dihitung
    sendiri oleh engine supaya tidak bisa dipalsukan.
    """
    for cand in legal_moves(state, board):
        if cand.frm == move.frm and cand.to == move.to and cand.captured == move.captured:
            return cand
    return None


def apply_move(state, move, board=BOARD):
    """Terapkan `move` ke `state` (memutasi state). Validasi penuh.

    Raise `IllegalMove` bila langkah tidak ada di `legal_moves()`.
    """
    if state.is_over():
        raise IllegalMove(f"permainan sudah selesai (status={state.status})")

    canonical = find_legal(state, move, board)
    if canonical is None:
        raise IllegalMove(
            f"langkah tidak legal untuk {state.turn}: "
            f"{move.frm} -> {move.to} makan {move.captured}"
        )

    actor = state.turn
    piece = state.board[canonical.frm]

    # Dicatat sebelum papan berubah: apakah pemain ini mengabaikan makan?
    ignored_capture = canonical.captured is None and has_capture(state, board)

    captured_info = []
    if canonical.captured is not None:
        victim = state.board[canonical.captured]
        captured_info.append(
            {"node": canonical.captured, "owner": victim.owner, "king": victim.king}
        )
        state.board[canonical.captured] = None

    state.board[canonical.frm] = None
    state.board[canonical.to] = piece
    if canonical.promote:
        piece.king = True

    # Makan atau promosi dihitung sebagai kemajuan.
    if canonical.captured is not None or canonical.promote:
        state.since_progress = 0
    else:
        state.since_progress += 1

    state.move_no += 1
    state.turn = other_side(actor)
    state.history.append({"move_no": state.move_no, "actor": actor, **canonical.to_dict()})

    return MoveEffect(
        actor=actor,
        move=canonical,
        captured=captured_info,
        promoted=canonical.promote,
        ignored_capture=ignored_capture,
    )


def apply_dam(state, offender, removed):
    """Hukuman DAM: ambil pion milik `offender` yang mengabaikan kesempatan makan.

    Maksimal 3 pion, bebas dipilih. Giliran tidak berpindah — pihak yang
    menjatuhkan DAM tetap melangkah sesudahnya.
    """
    if not removed:
        raise IllegalMove("DAM harus mengambil minimal 1 pion")
    if len(removed) > DAM_REMOVAL:
        raise IllegalMove(
            f"DAM maksimal mengambil {DAM_REMOVAL} pion, diminta {len(removed)}"
        )
    if len(set(removed)) != len(removed):
        raise IllegalMove("DAM memuat node duplikat")

    info = []
    for node in removed:
        piece = state.board.get(node)
        if piece is None or piece.owner != offender:
            raise IllegalMove(f"node {node!r} bukan pion milik {offender}")
        info.append({"node": node, "owner": piece.owner, "king": piece.king})
    for node in removed:
        state.board[node] = None

    state.since_progress = 0
    state.history.append({"move_no": state.move_no, "actor": offender, "dam": list(removed)})
    return info


def detect_outcome(state, board=BOARD):
    """Periksa kondisi akhir setelah sebuah langkah.

    Kembalikan `(pemenang, alasan)` dengan pemenang "A"/"B"/"draw", atau
    None bila permainan berlanjut. Diperiksa dari sudut pandang pemain
    yang giliran berikutnya.
    """
    if state.is_over():
        return None

    to_move = state.turn
    waiting = other_side(to_move)

    # Aturan Wikibooks: menang bila seluruh pion lawan habis.
    if state.count(to_move) == 0:
        return waiting, Reason.NO_PIECES
    # Buntu total dihitung kalah — tidak di Wikibooks, tapi permainan
    # harus punya jalan keluar.
    if not legal_moves(state, board):
        return waiting, Reason.NO_MOVES
    if state.since_progress >= DRAW_NO_PROGRESS:
        return "draw", Reason.NO_PROGRESS
    return None


def set_outcome(state, winner):
    """Tandai state sebagai selesai."""
    state.status = status_for_winner(winner)
