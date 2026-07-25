"""GUI Tkinter.

GUI hanya **menggambar** state dan mengirim langkah pilihan user ke engine —
tidak ada aturan permainan di sini. Papan digambar dari `board.py`
(node + edge), jadi mengganti papan otomatis mengganti tampilan.

Interaksi:
  - Klik-1 pada bidak yang sedang giliran -> tujuan legal disorot.
  - Klik-2 pada tujuan -> langkah diterapkan.
  - Untuk rantai lompatan, klik pendaratan berikutnya satu per satu sampai
    rantai lengkap (rantai wajib diselesaikan).
"""


from .logger import format_event
from .rules import IllegalMove

CELL = 58
MARGIN = 42
PIECE_R = 19

COLORS = {
    "bg": "#14100c",
    "board": "#c8a165",
    "line": "#6b4a24",
    "node": "#f0dcb4",
    "A": "#f5f2ec",
    "A_edge": "#8a8580",
    "B": "#26221d",
    "B_edge": "#000000",
    "sel": "#1f8fff",
    "target": "#2fbf5f",
    "capture": "#e0483c",
    "king": "#e8b32a",
    "text": "#f0e6d2",
    "muted": "#a89880",
}


class GameGUI:
    """Jendela permainan (dua pemain bergantian di satu layar)."""

    def __init__(self, engine, network,title="Catur Jawa — Dam-daman"):
        import tkinter as tk  # diimpor lokal agar modul lain tetap headless
        self.network=network
        self.tk = tk
        self.engine = engine
        self.board = engine.board

        self.selected = None
        self.partial = []
        self.status_text = "siap"

        self._layout(title)
        engine.on_event(self.on_event)
        self._redraw()

    # -- tata letak ---------------------------------------------------------
    def _layout(self, title):
        tk = self.tk
        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg=COLORS["bg"])

        xs = [p[0] for p in self.board.positions.values()]
        ys = [p[1] for p in self.board.positions.values()]
        self.min_x, self.max_x = min(xs), max(xs)
        self.min_y, self.max_y = min(ys), max(ys)
        width = int((self.max_x - self.min_x) * CELL) + 2 * MARGIN
        height = int((self.max_y - self.min_y) * CELL) + 2 * MARGIN

        left = tk.Frame(self.root, bg=COLORS["bg"])
        left.pack(side="left", padx=8, pady=8)
        self.canvas = tk.Canvas(
            left, width=width, height=height, bg=COLORS["board"], highlightthickness=0
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)

        right = tk.Frame(self.root, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=8)

        self.info = tk.Label(
            right, text="", justify="left", anchor="nw",
            font=("TkDefaultFont", 10), bg=COLORS["bg"], fg=COLORS["text"],
        )
        self.info.pack(fill="x")

        self.hint = tk.Label(
            right, text="", justify="left", anchor="nw", wraplength=330,
            font=("TkDefaultFont", 9), bg=COLORS["bg"], fg=COLORS["muted"],
        )
        self.hint.pack(fill="x", pady=(4, 8))

        tk.Label(right, text="LOG", bg=COLORS["bg"], fg=COLORS["muted"], anchor="w").pack(fill="x")
        self.log = tk.Text(
            right, width=46, height=22, bg="#0d0a07", fg=COLORS["text"],
            font=("TkFixedFont", 8), wrap="none", state="disabled",
        )
        self.log.pack(fill="both", expand=True)

        buttons = tk.Frame(right, bg=COLORS["bg"])
        buttons.pack(fill="x", pady=(8, 0))
        tk.Button(buttons, text="Batal pilih", command=self._clear_selection).pack(side="left", padx=2)
        tk.Button(buttons, text="Menyerah", command=self._resign).pack(side="left", padx=2)

    # -- koordinat ----------------------------------------------------------
    def _xy(self, node):
        x, y = self.board.positions[node]
        # y dibalik supaya rumah A (y kecil) ada di bawah layar.
        return MARGIN + (x - self.min_x) * CELL, MARGIN + (self.max_y - y) * CELL

    def _node_at(self, px, py):
        best, best_d = None, PIECE_R + 8
        for node in self.board.nodes:
            nx, ny = self._xy(node)
            d = ((nx - px) ** 2 + (ny - py) ** 2) ** 0.5
            if d < best_d:
                best, best_d = node, d
        return best

    # -- penggambaran -------------------------------------------------------
    def _redraw(self):
        c = self.canvas
        c.delete("all")

        drawn = set()
        for node, nbrs in self.board.neighbors.items():
            x1, y1 = self._xy(node)
            for nb, _ in nbrs:
                key = tuple(sorted((node, nb)))
                if key in drawn:
                    continue
                drawn.add(key)
                x2, y2 = self._xy(nb)
                c.create_line(x1, y1, x2, y2, fill=COLORS["line"], width=2)

        for node in self.board.nodes:
            x, y = self._xy(node)
            c.create_oval(x - 5, y - 5, x + 5, y + 5, fill=COLORS["node"], outline=COLORS["line"])

        # Sorotan tujuan legal berikutnya.
        candidates = self._candidates()
        depth = len(self.partial)
        for node in self._next_targets(candidates):
            x, y = self._xy(node)
            is_capture = any(
                m.captures and len(m.path) > depth and m.path[depth] == node for m in candidates
            )
            color = COLORS["capture"] if is_capture else COLORS["target"]
            c.create_oval(x - 14, y - 14, x + 14, y + 14, outline=color, width=3)

        # Jejak rantai lompatan yang sudah dipilih.
        if self.selected:
            trail = [self.selected] + self.partial
            for a, b in zip(trail, trail[1:]):
                x1, y1 = self._xy(a)
                x2, y2 = self._xy(b)
                c.create_line(x1, y1, x2, y2, fill=COLORS["sel"], width=3, dash=(6, 3))

        for node, piece in self.engine.state.board.items():
            if piece is None:
                continue
            x, y = self._xy(node)
            c.create_oval(
                x - PIECE_R, y - PIECE_R, x + PIECE_R, y + PIECE_R,
                fill=COLORS[piece.owner], outline=COLORS[f"{piece.owner}_edge"], width=2,
            )
            if piece.king:
                c.create_text(x, y, text="★", fill=COLORS["king"], font=("TkDefaultFont", 15, "bold"))
            if node == self.selected:
                c.create_oval(
                    x - PIECE_R - 4, y - PIECE_R - 4, x + PIECE_R + 4, y + PIECE_R + 4,
                    outline=COLORS["sel"], width=3,
                )

        for node in ("apex_A", "apex_B"):
            if self.board.has_node(node):
                x, y = self._xy(node)
                c.create_text(
                    x, y - PIECE_R - 12, text=node, fill=COLORS["line"], font=("TkDefaultFont", 7)
                )

        self._update_info()

    def _update_info(self):
        e = self.engine
        counts = e.state.counts()
        lines = [
            f"A : {e.names['A']}    B : {e.names['B']}",
            f"You: {e.player}",
            f"giliran : {e.state.turn}" if not e.state.is_over() else f"HASIL   : {e.state.status}",
            f"bidak   : A={counts['A']['pieces']} (raja {counts['A']['kings']})   "
            f"B={counts['B']['pieces']} (raja {counts['B']['kings']})",
            f"langkah : {e.state.move_no}   tanpa kemajuan: {e.state.since_progress}",
        ]
        self.info.config(text="\n".join(lines))

        if e.state.is_over():
            hint = f"Permainan selesai: {e.state.status}."
        elif self.selected is None:
            hint = "Pilih bidak. " + (
                "WAJIB MAKAN: hanya bidak yang bisa melompat yang bisa dipilih."
                if e.has_capture() and not e.opts.dam_penalty
                else "Klik bidak untuk melihat tujuan legal."
            )
        else:
            hint = f"Terpilih {self.selected}. Klik lingkaran tujuan."
            if self.partial:
                hint += f" Rantai: {' -> '.join(self.partial)} (wajib dilanjutkan)."
        self.hint.config(text=f"{hint}\n{self.status_text}")

    # -- interaksi ----------------------------------------------------------
    def _candidates(self):
        """Langkah yang masih cocok dengan rantai yang sudah diklik."""
        if self.selected is None:
            return []
        depth = len(self.partial)
        return [
            m
            for m in self.engine.legal_moves_from(self.selected)
            if tuple(m.path[:depth]) == tuple(self.partial)
        ]

    def _next_targets(self, candidates):
        """Node yang boleh diklik berikutnya pada kedalaman rantai saat ini."""
        depth = len(self.partial)
        return {m.path[depth] for m in candidates if len(m.path) > depth}

    def _on_click(self, event):
        node = self._node_at(event.x, event.y)
        if node is None or self.engine.state.is_over():
            return

        side = self.engine.state.turn
        piece = self.engine.state.piece_at(node)
        if side!=self.engine.player:
            self._set_status(f"sekarang giliran {side}")
            self._redraw()
            return
        if self.selected is None:
            if piece is None or piece.owner != side:
                self._set_status(f"sekarang giliran {side}")
                self._redraw()
                return
            if not self.engine.legal_moves_from(node):
                self._set_status(f"{node} tidak punya langkah legal")
                self._redraw()
                return
            self.selected, self.partial = node, []
            self._set_status("")
            self._redraw()
            return

        # Klik bidak sendiri lagi = ganti pilihan (selama rantai belum dimulai).
        if not self.partial and piece is not None and piece.owner == side:
            if node == self.selected:
                self._clear_selection()
            elif self.engine.legal_moves_from(node):
                self.selected = node
                self._set_status("")
                self._redraw()
            return

        candidates = self._candidates()
        if node not in self._next_targets(candidates):
            self._set_status("tujuan tidak legal")
            self._redraw()
            return

        self.partial.append(node)
        exact = [m for m in candidates if tuple(m.path) == tuple(self.partial)]
        if exact:
            self._play(exact[0])
        else:
            self._set_status("rantai lompatan wajib dilanjutkan")
            self._redraw()

    def _play(self, move):
        try:
            result = self.engine.apply_move(move)
        except IllegalMove as exc:
            self._set_status(f"ditolak: {exc}")
            self._clear_selection()
            return
        self.network.sendmove(move)
        self.selected, self.partial = None, []
        self.status_text = (
            f"SELESAI — pemenang {result.winner} ({result.reason})" if result.game_over else ""
        )
        self._redraw()

    def _clear_selection(self):
        self.selected, self.partial = None, []
        self._redraw()

    def _resign(self):
        loser = self.engine.state.turn
        result = self.engine.resign()
        if result.game_over:
            self.status_text = f"{loser} menyerah — pemenang {result.winner}"
        self._clear_selection()

    def _set_status(self, text):
        self.status_text = text

    # -- callback engine ----------------------------------------------------
    def on_event(self, event):
        self.log.config(state="normal")
        self.log.insert("end", format_event(event) + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def run(self):
        self.root.mainloop()
