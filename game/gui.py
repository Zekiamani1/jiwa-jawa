"""GUI Tkinter.

GUI hanya **menggambar** state dan mengirim langkah pilihan user ke engine —
tidak ada aturan permainan di sini. Papan digambar dari `board.py`
(node + edge), jadi mengganti papan otomatis mengganti tampilan.

Interaksi:
  - Klik-1 pada bidak yang sedang giliran -> tujuan legal disorot
    (hijau = jalan biasa, merah = makan).
  - Klik-2 pada tujuan -> langkah diterapkan. Selalu satu langkah;
    tidak ada rantai lompatan.
  - Bila lawan mengabaikan kesempatan makan, GUI masuk mode DAM: klik
    sampai 3 pion lawan untuk diambil, atau tekan "Lewati DAM".
"""


from .logger import format_event
from .rules import DAM_REMOVAL, IllegalMove

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
    "dam": "#d38bff",
    "king": "#e8b32a",
    "text": "#f0e6d2",
    "muted": "#a89880",
}


class GameGUI:
    """Jendela permainan."""

    def __init__(self, engine, network=None, on_end=None, title="JAWA"):
        import tkinter as tk  # diimpor lokal agar modul lain tetap headless
        self.network = network
        self.tk = tk
        self.engine = engine
        self.board = engine.board
        self.on_end = on_end

        self.selected = None
        self.dam_picked = []
        self.status_text = "siap"
        self.end_info = None       # {"winner": ..., "reason": ...} setelah selesai
        self._closing = False
        self._after_id = None

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
        self.dam_button = tk.Button(buttons, text="Ambil DAM", command=self._take_dam)
        self.dam_button.pack(side="left", padx=2)
        tk.Button(buttons, text="Lewati DAM", command=self._skip_dam).pack(side="left", padx=2)
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

    # -- mode DAM -----------------------------------------------------------
    def _dam_korban(self):
        """Pion pihak yang abai — yang boleh diambil sebagai DAM."""
        return self.engine.state.nodes_of(self.engine.pending_dam_offender)

    def _dam_mode(self):
        """True bila pemain lokal sedang berhak mengambil DAM."""
        e = self.engine
        if e.pending_dam_offender is None or e.state.is_over():
            return False
        # Yang berhak mengambil adalah pihak yang sekarang giliran.
        return e.player is None or e.state.turn == e.player

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

        # Sorotan: target DAM, atau tujuan legal bidak terpilih.
        if self._dam_mode():
            for node in self._dam_korban():
                x, y = self._xy(node)
                c.create_oval(x - 14, y - 14, x + 14, y + 14, outline=COLORS["dam"], width=3)
        elif self.selected is not None:
            for m in self.engine.legal_moves_from(self.selected):
                x, y = self._xy(m.to)
                color = COLORS["capture"] if m.captured else COLORS["target"]
                c.create_oval(x - 14, y - 14, x + 14, y + 14, outline=color, width=3)

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
            if node == self.selected or node in self.dam_picked:
                ring = COLORS["dam"] if node in self.dam_picked else COLORS["sel"]
                c.create_oval(
                    x - PIECE_R - 4, y - PIECE_R - 4, x + PIECE_R + 4, y + PIECE_R + 4,
                    outline=ring, width=3,
                )

        for node in ("apex_A", "apex_B"):
            if self.board.has_node(node):
                x, y = self._xy(node)
                c.create_text(
                    x, y - PIECE_R - 12, text=node, fill=COLORS["line"], font=("TkDefaultFont", 7)
                )

        self._update_info()

    def _name(self, side):
        return self.engine.names.get(side, side) if side in ("A", "B") else side

    def _update_info(self):
        e = self.engine
        counts = e.state.counts()
        your_name = self._name(e.player) if e.player in ("A", "B") else "-"
        lines = [
            f"{self._name('A')}   vs   {self._name('B')}",
            f"Kamu    : {your_name}",
            (f"Giliran : {self._name(e.state.turn)}"
             if not e.state.is_over() else f"HASIL   : {e.state.status}"),
            f"{self._name('A')}: {counts['A']['pieces']} bidak (raja {counts['A']['kings']})",
            f"{self._name('B')}: {counts['B']['pieces']} bidak (raja {counts['B']['kings']})",
            f"langkah : {e.state.move_no}   tanpa kemajuan: {e.state.since_progress}",
        ]
        self.info.config(text="\n".join(lines))

        if e.state.is_over():
            hint = f"Permainan selesai: {e.state.status}."
        elif self._dam_mode():
            hint = (
                f"DAM! {self._name(e.pending_dam_offender)} mengabaikan kesempatan makan. "
                f"Klik sampai {DAM_REMOVAL} pion lawan lalu tekan 'Ambil DAM', "
                f"atau 'Lewati DAM'. Terpilih: {len(self.dam_picked)}."
            )
        elif self.selected is None:
            hint = "Klik bidak untuk melihat tujuan legal. Makan tidak wajib — "
            hint += (
                "TAPI kamu punya kesempatan makan; kalau diabaikan lawan boleh ambil 3 pionmu."
                if e.has_capture()
                else "tidak ada kesempatan makan sekarang."
            )
        else:
            hint = f"Terpilih {self.selected}. Klik lingkaran tujuan."
        self.hint.config(text=f"{hint}\n{self.status_text}")

    # -- interaksi ----------------------------------------------------------
    def _on_click(self, event):
        node = self._node_at(event.x, event.y)
        if node is None or self.engine.state.is_over():
            return

        if self._dam_mode():
            self._click_dam(node)
            return

        side = self.engine.state.turn
        piece = self.engine.state.piece_at(node)
        if self.engine.player is not None and side != self.engine.player:
            self._set_status(f"menunggu lawan ({self._name(side)})")
            self._redraw()
            return

        # Klik bidak sendiri = pilih / ganti pilihan.
        if piece is not None and piece.owner == side:
            if node == self.selected:
                self._clear_selection()
            elif not self.engine.legal_moves_from(node):
                self._set_status(f"{node} tidak punya langkah legal")
                self._redraw()
            else:
                self.selected = node
                self._set_status("")
                self._redraw()
            return

        if self.selected is None:
            self._set_status(f"sekarang giliran {self._name(side)}")
            self._redraw()
            return

        cocok = [m for m in self.engine.legal_moves_from(self.selected) if m.to == node]
        if not cocok:
            self._set_status("tujuan tidak legal")
            self._redraw()
            return
        self._play(cocok[0])

    def _click_dam(self, node):
        if node in self.dam_picked:
            self.dam_picked.remove(node)
        elif node not in self._dam_korban():
            self._set_status("itu bukan pion pihak yang abai")
        elif len(self.dam_picked) >= DAM_REMOVAL:
            self._set_status(f"maksimal {DAM_REMOVAL} pion")
        else:
            self.dam_picked.append(node)
            self._set_status("")
        self._redraw()

    def _take_dam(self):
        if not self._dam_mode() or not self.dam_picked:
            self._set_status("belum ada pion DAM yang dipilih")
            self._redraw()
            return
        diambil = list(self.dam_picked)
        try:
            result = self.engine.call_dam(diambil)
        except IllegalMove as exc:
            self._set_status(f"DAM ditolak: {exc}")
            self.dam_picked = []
            self._redraw()
            return
        self.dam_picked = []
        if self.network is not None:
            self.network.send_dam(diambil)
        self.status_text = f"DAM: mengambil {len(diambil)} pion"
        if result.game_over:
            self.status_text = f"SELESAI — pemenang {self._name(result.winner)} ({result.reason})"
            if self.network is not None:
                self.network.send_end(result.winner, result.reason)
            self._mark_end(result.winner, result.reason)
        self._redraw()

    def _skip_dam(self):
        if not self._dam_mode():
            return
        self.engine.skip_dam()
        self.dam_picked = []
        self._set_status("hak DAM dilewati")
        self._redraw()

    def _play(self, move):
        try:
            result = self.engine.apply_move(move)
        except IllegalMove as exc:
            self._set_status(f"ditolak: {exc}")
            self._clear_selection()
            return

        if self.network is not None:
            if result.game_over:
                self.network.send_end(result.winner, result.reason, move)
            else:
                self.network.send_move(move)

        self.selected = None
        self.status_text = (
            f"SELESAI — pemenang {self._name(result.winner)} ({result.reason})" if result.game_over else ""
        )
        if result.game_over:
            self._mark_end(result.winner, result.reason)
        self._redraw()

    def _clear_selection(self):
        self.selected = None
        self._redraw()

    def _resign(self):
        loser = self.engine.player or self.engine.state.turn
        result = self.engine.resign(side=loser)
        if result.game_over:
            self.status_text = f"{self._name(loser)} menyerah — pemenang {self._name(result.winner)}"
            if self.network is not None:
                self.network.send_end(result.winner, result.reason)
            self._mark_end(result.winner, result.reason)
        self._clear_selection()

    def _set_status(self, text):
        self.status_text = text

    def _mark_end(self, winner, reason):
        """Simpan info akhir permainan dan picu popup (jendela game tetap terbuka)."""
        if self.end_info is not None:
            return
        self.end_info = {"winner": winner, "reason": reason}
        if self.on_end is not None:
            self.root.after(50, lambda: self.on_end(winner, reason))

    def on_event(self, event):
        self.log.config(state="normal")
        self.log.insert("end", format_event(event, names=self.engine.names) + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def read_from_network(self):
        self._after_id = None
        if self._closing:
            return
        if self.network is not None:
            while True:
                data = self.network.read()
                if data is None:
                    break
                self.handle_remote(data)
        try:
            self._after_id = self.root.after(60, self.read_from_network)
        except self.tk.TclError:
            pass

    def _on_close(self):
        self._closing = True
        if self._after_id is not None:
            try:
                self.root.after_cancel(self._after_id)
            except self.tk.TclError:
                pass
            self._after_id = None
        try:
            self.root.destroy()
        except self.tk.TclError:
            pass

    def handle_remote(self, data):
        if data["lost"]:
            self._set_status("koneksi terputus — lawan tidak merespons")
            self._redraw()
            return
        if data.get("dam"):
            try:
                self.engine.call_dam(data["dam"])
            except IllegalMove as exc:
                self._set_status(f"DAM lawan ditolak: {exc}")
        if data["move"] is not None:
            # Lawan sudah melangkah, jadi haknya atas DAM dilepas.
            if self.engine.pending_dam_offender == self.engine.state.turn:
                self.engine.skip_dam()
            try:
                self.engine.apply_move(data["move"])
            except IllegalMove as exc:
                self._set_status(f"langkah lawan ditolak: {exc}")
        if data["end"] is not None:
            end = data["end"]
            if not self.engine.state.is_over() and end["winner"] in ("A", "B"):
                kalah = "B" if end["winner"] == "A" else "A"
                self.engine.resign(side=kalah)
            self.status_text = f"SELESAI — pemenang {self._name(end['winner'])} ({end['reason']})"
            self._mark_end(end["winner"], end["reason"])
        if data["lost"]:
            self._mark_end(None, "koneksi terputus")
        self._redraw()

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        if self.network is not None:
            self._after_id = self.root.after(60, self.read_from_network)
        self.root.mainloop()
