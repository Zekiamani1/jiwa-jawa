"""Aturan permainan: move generation, validasi, promosi, dan DAM.

Ini inti gamenya. Semua aturan bekerja di atas graf papan (`board.Board`),
jadi mengganti papan tidak mengubah file ini.

Konvensi `Move`:
  - `frm`      : node asal.
  - `path`     : urutan **titik henti** setelah meninggalkan `frm`
                 (langkah biasa = 1 elemen; rantai lompatan = tiap
                 pendaratan; luncuran raja = node tujuan saja).
  - `captures` : korban sesuai urutan dimakan.
  - `promote`  : True bila langkah ini mempromosikan bidak.
"""
from dataclasses import dataclass

from .board import BOARD, other_side
from .state import status_for_winner


class IllegalMove(Exception):
    """Langkah tidak legal menurut aturan."""


class Reason:
    """Alasan permainan berakhir."""

    NO_PIECES = "no_pieces"
    NO_MOVES = "no_moves"
    RESIGN = "resign"
    NO_PROGRESS = "no_progress"
    REPETITION = "repetition"


@dataclass(frozen=True)
class RuleOptions:
    """Varian aturan yang bisa dinyalakan/dimatikan."""

    # Bidak biasa boleh mundur (default: bebas segala arah).
    allow_backward: bool = True
    # Mode DAM sosial: langkah non-makan diizinkan meski ada lompatan.
    dam_penalty: bool = False
    # Jumlah bidak yang dihapus saat DAM dijatuhkan.
    dam_removal: int = 3
    # Seri bila sekian langkah tanpa makan & tanpa promosi (0 = mati).
    draw_no_progress: int = 40
    # Seri bila posisi identik berulang sekian kali (0 = mati).
    repetition_limit: int = 3
    # Raja bergerak & menangkap jarak jauh (flying king).
    flying_king: bool = True


DEFAULT_OPTIONS = RuleOptions()


@dataclass(frozen=True)
class Move:
    """Satu aksi lengkap dalam satu giliran."""

    frm: str
    path: tuple
    captures: tuple = ()
    promote: bool = False

    def to_dict(self):
        return {
            "from": self.frm,
            "path": list(self.path),
            "captures": list(self.captures),
            "promote": self.promote,
        }

    def describe(self):
        """Deskripsi terbaca manusia (untuk log & GUI)."""
        if self.captures:
            arrow = " x ".join((self.frm,) + self.path)
        else:
            arrow = f"{self.frm} -> {self.path[-1]}"
        bits = [arrow]
        if self.captures:
            bits.append(f"makan {len(self.captures)}: {', '.join(self.captures)}")
        if self.promote:
            bits.append("PROMOSI")
        return " | ".join(bits)


@dataclass
class MoveEffect:
    """Apa yang terjadi akibat sebuah langkah (bahan untuk logging)."""

    actor: str
    move: Move
    captured: list  # [{node, owner, king}, ...]
    promoted: bool
    dest: str
    ignored_capture: bool = False


def _man_capture_chains(board, occ, owner, start):
    """Semua rantai lompatan **maksimal** untuk bidak biasa.

    Korban tetap di papan selama rantai berlangsung (jadi menghalangi
    pendaratan) dan tidak boleh dimakan dua kali.
    """
    results = []
    captured = []
    path = []

    def dfs(cur):
        extended = False
        for nb, direction in board.neighbors[cur]:
            if nb in captured:
                continue
            victim = occ.get(nb)
            if victim is None or victim.owner == owner:
                continue
            landing = board.step(nb, direction)
            if landing is None or occ.get(landing) is not None:
                continue
            extended = True
            captured.append(nb)
            path.append(landing)
            dfs(landing)
            path.pop()
            captured.pop()
        if not extended and path:
            results.append((tuple(path), tuple(captured)))

    dfs(start)
    return results


def _king_capture_chains(board, occ, owner, start):
    """Rantai lompatan raja terbang."""
    results = []
    captured = []
    path = []

    def dfs(cur):
        extended = False
        for direction in board.by_dir[cur]:
            # Meluncur melewati node kosong sampai bertemu bidak pertama.
            node = board.step(cur, direction)
            while node is not None and occ.get(node) is None:
                node = board.step(node, direction)
            if node is None:
                continue
            victim = occ.get(node)
            # Korban yang sudah dimakan menghalangi: tak bisa dimakan/dilewati lagi.
            if victim is None or victim.owner == owner or node in captured:
                continue
            landing = board.step(node, direction)
            while landing is not None and occ.get(landing) is None:
                extended = True
                captured.append(node)
                path.append(landing)
                dfs(landing)
                path.pop()
                captured.pop()
                landing = board.step(landing, direction)
        if not extended and path:
            results.append((tuple(path), tuple(captured)))

    dfs(start)
    return results


def capture_moves(state, board=BOARD, opts=DEFAULT_OPTIONS):
    """Semua rantai lompatan maksimal untuk pemain yang sedang giliran."""
    owner = state.turn
    moves = []
    for start in state.nodes_of(owner):
        piece = state.board[start]
        assert piece is not None
        occ = dict(state.board)
        occ[start] = None  # bidak diangkat dari asalnya
        if piece.king and opts.flying_king:
            chains = _king_capture_chains(board, occ, owner, start)
        else:
            chains = _man_capture_chains(board, occ, owner, start)
        for path, caps in chains:
            promote = not piece.king and board.is_promotion(owner, path[-1])
            moves.append(Move(frm=start, path=path, captures=caps, promote=promote))
    return moves


def quiet_moves(state, board=BOARD, opts=DEFAULT_OPTIONS):
    """Semua langkah biasa (tanpa makan) untuk pemain yang sedang giliran."""
    owner = state.turn
    moves = []
    for start in state.nodes_of(owner):
        piece = state.board[start]
        assert piece is not None
        if piece.king and opts.flying_king:
            for direction in board.by_dir[start]:
                node = board.step(start, direction)
                while node is not None and state.board.get(node) is None:
                    moves.append(Move(frm=start, path=(node,)))
                    node = board.step(node, direction)
        else:
            for nb, direction in board.neighbors[start]:
                if state.board.get(nb) is not None:
                    continue
                if not opts.allow_backward and not board.is_forward(owner, direction):
                    continue
                promote = not piece.king and board.is_promotion(owner, nb)
                moves.append(Move(frm=start, path=(nb,), promote=promote))
    return moves


def _sorted(moves):
    """Urutan deterministik supaya daftar langkah selalu sama."""
    return sorted(moves, key=lambda m: (m.frm, m.path, m.captures, m.promote))


def legal_moves(state, board=BOARD, opts=DEFAULT_OPTIONS):
    """Langkah legal untuk pemain yang sedang giliran.

    Bila ada lompatan tersedia, HANYA lompatan yang dikembalikan (wajib
    makan) — kecuali mode DAM sosial aktif.
    """
    if state.is_over():
        return []
    caps = capture_moves(state, board, opts)
    if caps and not opts.dam_penalty:
        return _sorted(caps)
    return _sorted(caps + quiet_moves(state, board, opts))


def moves_from(state, node, board=BOARD, opts=DEFAULT_OPTIONS):
    """Langkah legal yang berawal dari `node` (dipakai GUI untuk sorotan)."""
    return [m for m in legal_moves(state, board, opts) if m.frm == node]


def has_capture(state, board=BOARD, opts=DEFAULT_OPTIONS):
    """True bila pemain yang sedang giliran punya minimal satu lompatan."""
    return bool(capture_moves(state, board, opts))


def find_legal(state, move, board=BOARD, opts=DEFAULT_OPTIONS):
    """Cari padanan kanonik `move` di daftar legal; None bila tidak ada.

    Flag `promote` yang dikirim pemanggil diabaikan — promosi dihitung
    sendiri oleh engine supaya tidak bisa dipalsukan.
    """
    for cand in legal_moves(state, board, opts):
        if cand.frm == move.frm and cand.path == move.path and cand.captures == move.captures:
            return cand
    return None



def apply_move(state, move, board=BOARD, opts=DEFAULT_OPTIONS):
    """Terapkan `move` ke `state` (memutasi state). Validasi penuh.

    Raise `IllegalMove` bila langkah tidak ada di `legal_moves()`.
    """
    if state.is_over():
        raise IllegalMove(f"permainan sudah selesai (status={state.status})")

    canonical = find_legal(state, move, board, opts)
    if canonical is None:
        raise IllegalMove(
            f"langkah tidak legal untuk {state.turn}: "
            f"{move.frm} -> {list(move.path)} makan {list(move.captures)}"
        )

    actor = state.turn
    piece = state.board[canonical.frm]
    assert piece is not None

    ignored_capture = not canonical.captures and has_capture(state, board, opts)

    captured_info = []
    for node in canonical.captures:
        victim = state.board[node]
        assert victim is not None
        captured_info.append({"node": node, "owner": victim.owner, "king": victim.king})
        state.board[node] = None

    state.board[canonical.frm] = None
    dest = canonical.path[-1]
    state.board[dest] = piece
    if canonical.promote:
        piece.king = True

    # Makan atau promosi dihitung sebagai kemajuan.
    if canonical.captures or canonical.promote:
        state.since_progress = 0
    else:
        state.since_progress += 1

    state.move_no += 1
    state.turn = other_side(actor)
    key = state.position_key()
    state.position_counts[key] = state.position_counts.get(key, 0) + 1
    state.history.append({"move_no": state.move_no, "actor": actor, **canonical.to_dict()})

    return MoveEffect(
        actor=actor,
        move=canonical,
        captured=captured_info,
        promoted=canonical.promote,
        dest=dest,
        ignored_capture=ignored_capture,
    )


def apply_dam(state, offender, removed, opts=DEFAULT_OPTIONS):
    """Hukuman DAM: hapus bidak milik `offender` yang mengabaikan lompatan.

    Giliran tidak berpindah — pihak yang menjatuhkan DAM tetap melangkah,
    jadi pihak yang abai kehilangan tempo.
    """
    if not opts.dam_penalty:
        raise IllegalMove("mode DAM sosial tidak aktif")
    if not removed:
        raise IllegalMove("DAM harus menghapus minimal 1 bidak")
    if len(removed) > opts.dam_removal:
        raise IllegalMove(
            f"DAM maksimal menghapus {opts.dam_removal} bidak, diminta {len(removed)}"
        )
    if len(set(removed)) != len(removed):
        raise IllegalMove("DAM memuat node duplikat")

    info = []
    for node in removed:
        piece = state.board.get(node)
        if piece is None or piece.owner != offender:
            raise IllegalMove(f"node {node!r} bukan bidak milik {offender}")
        info.append({"node": node, "owner": piece.owner, "king": piece.king})
    for node in removed:
        state.board[node] = None

    state.since_progress = 0
    state.history.append({"move_no": state.move_no, "actor": offender, "dam": list(removed)})
    return info


def detect_outcome(state, board=BOARD, opts=DEFAULT_OPTIONS):
    """Periksa kondisi akhir setelah sebuah langkah.

    Kembalikan `(pemenang, alasan)` dengan pemenang "A"/"B"/"draw", atau
    None bila permainan berlanjut. Diperiksa dari sudut pandang pemain yang
    giliran berikutnya.
    """
    if state.is_over():
        return None

    to_move = state.turn
    waiting = other_side(to_move)

    if state.count(to_move) == 0:
        return waiting, Reason.NO_PIECES
    if not legal_moves(state, board, opts):
        return waiting, Reason.NO_MOVES
    if opts.draw_no_progress and state.since_progress >= opts.draw_no_progress:
        return "draw", Reason.NO_PROGRESS
    if opts.repetition_limit and max(state.position_counts.values(), default=0) >= opts.repetition_limit:
        return "draw", Reason.REPETITION
    return None


def set_outcome(state, winner):
    """Tandai state sebagai selesai."""
    state.status = status_for_winner(winner)
