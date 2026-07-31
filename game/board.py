"""Papan Catur Jawa / Dam-daman sebagai graf node + edge.

Papan dipakai sebagai **graf**, bukan matriks, supaya kode aturan di
`rules.py` tidak perlu tahu bentuk papannya.

Papan bawaan (grid 5x5 + segitiga 6-node di atas & bawah):
  - Grid: `n{x}_{y}` untuk x = 0..4, y = 0..4 (25 titik) — persis
    seperti sebelumnya. Ortogonal semua ada; diagonal alquerque
    (hanya dari titik (x + y) genap).
  - Segitiga A menempel di tepi bawah grid, mekar ke y negatif:
      middle    (1, -1), (2, -1), (3, -1)  -- rapat
      outer     (0, -2), (2, -2), (4, -2)  -- selebar grid
    Node grid tengah tepi (n2_0) tersambung langsung ke tiga middle
    lewat tiga edge (diagonal-kiri, lurus, diagonal-kanan). Middle
    horizontal berturut. Middle -> outer: L diagonal, M lurus, R
    diagonal. Outer horizontal berjarak 2.
  - Segitiga B: cermin di y > 4 (menempel ke n2_4).
  - Segitiga tumbuh keluar — sisi middle (dekat grid) rapat, sisi outer
    (jauh) melebar sampai lebar penuh grid.
  - Susunan awal: A menempati y = 0..1 grid + seluruh segitiga A
    (16 bidak). B menempati y = 3..4 grid + seluruh segitiga B
    (16 bidak). Baris tengah y = 2 kosong.
  - Promosi: bidak jadi raja HANYA saat mencapai salah satu dari
    tiga node outer segitiga lawan (basis segitiga). Baris terakhir
    grid tidak mempromosikan.
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


COLS = 5
ROWS = 5
NEUTRAL_ROW = 2


def node_id(x, y):
    """Id node untuk kolom `x`, baris `y`. `y` boleh di luar 0..ROWS-1
    (untuk segitiga)."""
    return f"n{x}_{y}"


# Koordinat segitiga A (di bawah grid, y negatif).
_TRIANGLE_A_MID = [(1, -1), (2, -1), (3, -1)]
_TRIANGLE_A_OUT = [(0, -2), (2, -2), (4, -2)]
_TRIANGLE_A = _TRIANGLE_A_MID + _TRIANGLE_A_OUT

# Segitiga B (di atas grid, y > ROWS-1) — cermin.
_TRIANGLE_B_MID = [(1, ROWS), (2, ROWS), (3, ROWS)]
_TRIANGLE_B_OUT = [(0, ROWS + 1), (2, ROWS + 1), (4, ROWS + 1)]
_TRIANGLE_B = _TRIANGLE_B_MID + _TRIANGLE_B_OUT


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


def _add_triangle(b, positions, mid_coords, out_coords, hub_grid_node, y_sign):
    """Rakit satu segitiga.

    `y_sign` = -1 untuk segitiga A (di bawah grid), +1 untuk B.
    Semua arah "keluar" dari grid dikalikan `y_sign`.
    """
    for (x, y) in mid_coords + out_coords:
        n = node_id(x, y)
        b.add_node(n)
        positions[n] = (float(x), float(y))

    mid_L = node_id(*mid_coords[0])
    mid_M = node_id(*mid_coords[1])
    mid_R = node_id(*mid_coords[2])
    out_L = node_id(*out_coords[0])
    out_M = node_id(*out_coords[1])
    out_R = node_id(*out_coords[2])

    # hub grid -> tiga middle (tiga edge: diagonal kiri, lurus, diagonal kanan).
    b.add_edge(hub_grid_node, mid_L, (-1, y_sign))
    b.add_edge(hub_grid_node, mid_M, (0, y_sign))
    b.add_edge(hub_grid_node, mid_R, (1, y_sign))

    # middle horizontal.
    b.add_edge(mid_L, mid_M, (1, 0))
    b.add_edge(mid_M, mid_R, (1, 0))

    # middle -> outer: L diagonal keluar, M lurus, R diagonal keluar.
    b.add_edge(mid_L, out_L, (-1, y_sign))
    b.add_edge(mid_M, out_M, (0, y_sign))
    b.add_edge(mid_R, out_R, (1, y_sign))

    # outer horizontal (jarak 2 satuan).
    b.add_edge(out_L, out_M, (2, 0))
    b.add_edge(out_M, out_R, (2, 0))


def _build_damdaman():
    b = _Builder()
    positions = {}

    # Grid 5x5 nodes.
    for y in range(ROWS):
        for x in range(COLS):
            n = node_id(x, y)
            b.add_node(n)
            positions[n] = (float(x), float(y))

    # Grid ortogonal.
    for y in range(ROWS):
        for x in range(COLS):
            if x + 1 < COLS:
                b.add_edge(node_id(x, y), node_id(x + 1, y), (1, 0))
            if y + 1 < ROWS:
                b.add_edge(node_id(x, y), node_id(x, y + 1), (0, 1))

    # Grid diagonal alquerque.
    for y in range(ROWS):
        for x in range(COLS):
            if (x + y) % 2 != 0:
                continue
            if x + 1 < COLS and y + 1 < ROWS:
                b.add_edge(node_id(x, y), node_id(x + 1, y + 1), (1, 1))
            if x + 1 < COLS and y - 1 >= 0:
                b.add_edge(node_id(x, y), node_id(x + 1, y - 1), (1, -1))

    # Dua segitiga.
    _add_triangle(
        b, positions,
        _TRIANGLE_A_MID, _TRIANGLE_A_OUT,
        hub_grid_node=node_id(2, 0),
        y_sign=-1,
    )
    _add_triangle(
        b, positions,
        _TRIANGLE_B_MID, _TRIANGLE_B_OUT,
        hub_grid_node=node_id(2, ROWS - 1),
        y_sign=+1,
    )

    # Susunan awal.
    start = {}
    # Grid: A di y=0,1; B di y=3,4; y=2 kosong.
    for y in range(ROWS):
        if y == NEUTRAL_ROW:
            continue
        owner = SIDE_A if y < NEUTRAL_ROW else SIDE_B
        for x in range(COLS):
            start[node_id(x, y)] = owner
    # Segitiga terisi penuh milik pemilik tepi terdekat.
    for (x, y) in _TRIANGLE_A:
        start[node_id(x, y)] = SIDE_A
    for (x, y) in _TRIANGLE_B:
        start[node_id(x, y)] = SIDE_B

    # Zona promosi = tiga node outer segitiga lawan (basis segitiga lawan).
    promotion = {
        SIDE_A: frozenset(node_id(x, y) for (x, y) in _TRIANGLE_B_OUT),
        SIDE_B: frozenset(node_id(x, y) for (x, y) in _TRIANGLE_A_OUT),
    }

    return b.freeze(
        positions=positions,
        start_pieces=start,
        promotion_zone=promotion,
        forward_dy={SIDE_A: 1, SIDE_B: -1},
    )


# Papan yang dipakai seluruh program.
BOARD = _build_damdaman()
