"""Papan Catur Jawa / Dam-daman sebagai graf node + edge.

Papan dipakai sebagai **graf**, bukan matriks, supaya kode aturan di
`rules.py` tidak perlu tahu bentuk papannya. Mau ganti papan (mis. macanan
5x5)? Ubah `_build_damdaman()` saja, aturan tidak berubah.

Papan bawaan (4 kolom x 9 baris + 2 apex segitiga):
  - Titik grid `n{x}_{y}`, x = 0..3, y = 0..8 -> 36 titik.
  - y = 0..3 rumah A (16 bidak), y = 4 netral, y = 5..8 rumah B (16 bidak).
  - Edge ortogonal selalu ada; edge diagonal hanya bila (x + y) genap
    (pola alquerque).
  - Dua apex: `apex_B` di ujung B, `apex_A` di ujung A.
  - Tiap edge menyimpan arah `(dx, dy)`. Arah inilah yang menentukan
    pendaratan lompatan: landing = tetangga korban pada arah yang sama.
"""
from dataclasses import dataclass

SIDE_A = "A"
SIDE_B = "B"
SIDES = (SIDE_A, SIDE_B)


def other_side(side):
    """Kembalikan sisi lawan."""
    if side == SIDE_A:
        return SIDE_B
    if side == SIDE_B:
        return SIDE_A
    raise ValueError(f"sisi tidak dikenal: {side!r}")


COLS = 4
ROWS = 9
NEUTRAL_ROW = 4

APEX_A = "apex_A"
APEX_B = "apex_B"


def node_id(x, y):
    """Id node grid untuk kolom `x`, baris `y`."""
    return f"n{x}_{y}"


@dataclass(frozen=True)
class Board:
    """Papan yang sudah dirakit. Dibuat sekali lalu hanya dibaca."""

    nodes: tuple
    # node -> tuple of (tetangga, arah)
    neighbors: dict
    # node -> {arah: tetangga}, untuk mencari pendaratan lompatan
    by_dir: dict
    # node -> (x, y) koordinat gambar untuk GUI (boleh pecahan)
    positions: dict
    # susunan awal: node -> pemilik bidak
    start_pieces: dict
    # pemilik -> node-node zona promosi
    promotion_zone: dict
    # pemilik -> arah maju (dy), untuk opsi `allow_backward=False`
    forward_dy: dict

    def step(self, node, direction):
        """Tetangga dari `node` pada arah `direction`, atau None."""
        return self.by_dir.get(node, {}).get(direction)

    def is_promotion(self, owner, node):
        """True bila `node` mempromosikan bidak milik `owner`."""
        return node in self.promotion_zone[owner]

    def is_forward(self, owner, direction):
        """True bila `direction` bukan arah mundur bagi `owner`."""
        return direction[1] * self.forward_dy[owner] >= 0

    def has_node(self, node):
        return node in self.by_dir


class _Builder:
    """Perakit graf; menjaga invarian satu node - satu tetangga per arah."""

    def __init__(self):
        self.nodes = []
        self.adj = {}

    def add_node(self, node):
        if node in self.adj:
            raise ValueError(f"node duplikat: {node}")
        self.nodes.append(node)
        self.adj[node] = {}

    def add_edge(self, a, b, direction):
        """Tambah edge dua arah: a -> b arah `direction`, b -> a kebalikannya."""
        back = (-direction[0], -direction[1])
        for src, dst, d in ((a, b, direction), (b, a, back)):
            if d in self.adj[src]:
                raise ValueError(
                    f"tabrakan arah pada {src}: {d} sudah menuju "
                    f"{self.adj[src][d]}, tidak bisa menuju {dst}"
                )
            self.adj[src][d] = dst

    def freeze(self, **kwargs):
        neighbors = {
            n: tuple(sorted(((dst, d) for d, dst in self.adj[n].items()), key=lambda t: t[0]))
            for n in self.nodes
        }
        return Board(
            nodes=tuple(self.nodes),
            neighbors=neighbors,
            by_dir={n: dict(self.adj[n]) for n in self.nodes},
            **kwargs,
        )


def _build_damdaman():
    b = _Builder()
    positions = {}

    for y in range(ROWS):
        for x in range(COLS):
            n = node_id(x, y)
            b.add_node(n)
            positions[n] = (float(x), float(y))

    # Apex segitiga: di luar grid, tepat di tengah kolom 1 & 2.
    b.add_node(APEX_A)
    positions[APEX_A] = (1.5, -1.0)
    b.add_node(APEX_B)
    positions[APEX_B] = (1.5, float(ROWS))

    # 1. Edge ortogonal.
    for y in range(ROWS):
        for x in range(COLS):
            if x + 1 < COLS:
                b.add_edge(node_id(x, y), node_id(x + 1, y), (1, 0))
            if y + 1 < ROWS:
                b.add_edge(node_id(x, y), node_id(x, y + 1), (0, 1))

    # 2. Edge diagonal (alquerque): hanya dari titik dengan (x + y) genap.
    #    Kedua ujung diagonal punya paritas sama, jadi menyapu ke arah +x
    #    sudah mencakup seluruh diagonal tepat sekali.
    for y in range(ROWS):
        for x in range(COLS):
            if (x + y) % 2 != 0:
                continue
            if x + 1 < COLS and y + 1 < ROWS:
                b.add_edge(node_id(x, y), node_id(x + 1, y + 1), (1, 1))
            if x + 1 < COLS and y - 1 >= 0:
                b.add_edge(node_id(x, y), node_id(x + 1, y - 1), (1, -1))

    # 3. Edge apex, arahnya mengikuti geometri segitiga (apex ada di x = 1.5)
    #    sehingga tidak bentrok dengan arah diagonal yang sudah ada.
    b.add_edge(node_id(1, ROWS - 1), APEX_B, (1, 1))
    b.add_edge(node_id(2, ROWS - 1), APEX_B, (-1, 1))
    b.add_edge(node_id(1, 0), APEX_A, (1, -1))
    b.add_edge(node_id(2, 0), APEX_A, (-1, -1))

    # Susunan awal: A di y = 0..3, B di y = 5..8, baris tengah kosong.
    start = {}
    for y in range(ROWS):
        if y == NEUTRAL_ROW:
            continue
        owner = SIDE_A if y < NEUTRAL_ROW else SIDE_B
        for x in range(COLS):
            start[node_id(x, y)] = owner

    promotion = {
        # A menuju y besar: promosi di baris terakhir atau apex_B.
        SIDE_A: frozenset({APEX_B} | {node_id(x, ROWS - 1) for x in range(COLS)}),
        # B menuju y kecil: promosi di baris 0 atau apex_A.
        SIDE_B: frozenset({APEX_A} | {node_id(x, 0) for x in range(COLS)}),
    }

    return b.freeze(
        positions=positions,
        start_pieces=start,
        promotion_zone=promotion,
        forward_dy={SIDE_A: 1, SIDE_B: -1},
    )


# Papan yang dipakai seluruh program.
BOARD = _build_damdaman()
