"""Dialog launcher, jendela tunggu koneksi, dan popup akhir permainan."""

import sys
import threading
import tkinter as tk

from .gui import COLORS as G

BG      = G["bg"]
PANEL   = "#1e1812"
TEXT    = G["text"]
MUTED   = G["muted"]
ACCENT  = G["king"]
BOARD   = G["board"]
LINE    = G["line"]
ENTRY   = "#0d0a07"
BTN_BG  = BOARD
BTN_FG  = "#2a1e10"
ERROR   = G["capture"]  # merah


def show_error(title, msg):
    root = tk.Tk()
    root.title(title)
    root.configure(bg=BG)
    root.resizable(False, False)
    frame = tk.Frame(root, bg=BG, padx=24, pady=18)
    frame.pack()
    tk.Label(frame, text=title, bg=BG, fg=ERROR,
             font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 6))
    tk.Label(frame, text=msg, bg=BG, fg=TEXT,
             font=("TkDefaultFont", 10), justify="left", wraplength=340).pack(anchor="w")
    tk.Button(frame, text="OK", width=10, command=root.destroy,
              bg=BTN_BG, fg=BTN_FG, activebackground=ACCENT,
              activeforeground=BTN_FG, relief="flat", bd=0).pack(pady=(14, 0))
    root.bind("<Return>", lambda _e: root.destroy())
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.eval("tk::PlaceWindow . center")
    root.mainloop()


def run_launcher():
    cfg = {"mode": "host", "name": "pemain", "port": 5000,
           "host_ip": "127.0.0.1", "host_port": 5000, "ok": False}
    root = tk.Tk()
    root.title("JAWA")
    root.configure(bg=BG)
    root.resizable(False, False)

    mode_var = tk.StringVar(value=cfg["mode"])
    name_var = tk.StringVar(value=cfg["name"])
    port_var = tk.StringVar(value=str(cfg["port"]))
    host_ip_var = tk.StringVar(value=cfg["host_ip"])
    host_port_var = tk.StringVar(value=str(cfg["host_port"]))

    frm = tk.Frame(root, padx=18, pady=14, bg=BG)
    frm.pack()
    tk.Label(frm, text="JAWA", bg=BG, fg=ACCENT,
             font=("TkDefaultFont", 13, "bold")).pack(anchor="w")
    tk.Label(frm, text="Pilih mode dan atur koneksi.", bg=BG, fg=MUTED,
             font=("TkDefaultFont", 9)).pack(anchor="w", pady=(0, 8))

    modef = tk.LabelFrame(frm, text="Mode", bg=BG, fg=TEXT,
                          padx=8, pady=6, bd=1, relief="groove")
    modef.pack(fill="x", pady=6)
    peer_entries = []

    def on_mode_change():
        state = "normal" if mode_var.get() == "join" else "disabled"
        for e in peer_entries:
            e.config(state=state)

    for text, val in (("Host", "host"), ("Join", "join")):
        tk.Radiobutton(modef, text=text, variable=mode_var, value=val,
                       command=on_mode_change, bg=BG, fg=TEXT,
                       selectcolor=PANEL, activebackground=BG,
                       activeforeground=ACCENT).pack(anchor="w")

    def row(parent, label, var):
        r = tk.Frame(parent, bg=BG)
        r.pack(fill="x", pady=2)
        tk.Label(r, text=label, width=12, anchor="w", bg=BG, fg=TEXT).pack(side="left")
        e = tk.Entry(r, textvariable=var, width=22, bg=ENTRY, fg=TEXT,
                     insertbackground=TEXT, relief="flat",
                     disabledbackground=PANEL, disabledforeground=MUTED)
        e.pack(side="left", fill="x", expand=True)
        return e

    idf = tk.LabelFrame(frm, text="Identitas", bg=BG, fg=TEXT,
                        padx=8, pady=6, bd=1, relief="groove")
    idf.pack(fill="x", pady=6)
    row(idf, "Nama", name_var)
    row(idf, "Port lokal", port_var)

    peerf = tk.LabelFrame(frm, text="Host tujuan (mode Join)", bg=BG, fg=TEXT,
                          padx=8, pady=6, bd=1, relief="groove")
    peerf.pack(fill="x", pady=6)
    peer_entries.append(row(peerf, "IP host", host_ip_var))
    peer_entries.append(row(peerf, "Port host", host_port_var))
    on_mode_change()

    def on_start():
        try:
            cfg["port"] = int(port_var.get())
            cfg["host_port"] = int(host_port_var.get())
        except ValueError:
            show_error("Setup", "Port harus angka.")
            return
        cfg["mode"] = mode_var.get()
        cfg["name"] = name_var.get().strip() or "pemain"
        cfg["host_ip"] = host_ip_var.get().strip()
        if cfg["mode"] == "join" and not cfg["host_ip"]:
            show_error("Setup", "IP host wajib diisi.")
            return
        cfg["ok"] = True
        root.destroy()

    btns = tk.Frame(frm, bg=BG)
    btns.pack(fill="x", pady=(8, 0))
    tk.Button(btns, text="Mulai", width=10, command=on_start,
              bg=BTN_BG, fg=BTN_FG, activebackground=ACCENT,
              activeforeground=BTN_FG, relief="flat", bd=0
              ).pack(side="right", padx=(6, 0))
    tk.Button(btns, text="Batal", width=10, command=root.destroy,
              bg=PANEL, fg=TEXT, activebackground=LINE,
              activeforeground=TEXT, relief="flat", bd=0
              ).pack(side="right")
    root.bind("<Return>", lambda _e: on_start())
    root.eval("tk::PlaceWindow . center")
    root.mainloop()
    return cfg if cfg["ok"] else None


def wait_for_handshake(cfg, task_fn):
    state = {"done": False, "error": None}

    def worker():
        try:
            task_fn()
        except BaseException as exc:  # noqa: BLE001
            state["error"] = exc
        finally:
            state["done"] = True

    threading.Thread(target=worker, daemon=True).start()

    wait = tk.Tk()
    wait.title("Menunggu")
    wait.configure(bg=BG)
    wait.resizable(False, False)
    msg = (f"Sedang menunggu koneksi di port {cfg['port']}"
           if cfg["mode"] == "host"
           else f"Menyambung ke {cfg['host_ip']}:{cfg['host_port']}")
    wait_frame = tk.Frame(wait, bg=BG, padx=32, pady=24)
    wait_frame.pack()
    tk.Label(wait_frame, text=msg, bg=BG, fg=TEXT,
             font=("TkDefaultFont", 11, "bold")).pack()
    tk.Label(wait_frame, text="mohon tunggu…", bg=BG, fg=ACCENT,
             font=("TkDefaultFont", 10)).pack(pady=(8, 0))

    def poll():
        if state["done"]:
            try:
                wait.destroy()
            except tk.TclError:
                pass
            return
        wait.after(200, poll)

    wait.protocol("WM_DELETE_WINDOW", lambda: sys.exit(0))
    wait.after(100, poll)
    wait.eval("tk::PlaceWindow . center")
    wait.mainloop()
    return state["error"]


def show_end(engine, end_info, rating_info=None, parent=None):
    end = end_info or {"winner": None, "reason": "jendela ditutup"}
    winner = end.get("winner")
    reason = end.get("reason") or "-"
    name_a = engine.names.get("A", "A")
    name_b = engine.names.get("B", "B")
    juara = name_a if winner == "A" else name_b if winner == "B" else "-"

    text = (
        f"Pemenang : {juara}\n"
        f"Alasan    : {reason}\n\n"
        f"Pemain 1 : {name_a}\n"
        f"Pemain 2 : {name_b}\n"
        f"Langkah total : {engine.state.move_no}"
    )
    if rating_info:
        ratings = rating_info.get("ratings", {})
        delta = rating_info.get("delta", {})
        text += "\n\nRating akhir:\n"
        for side, nm in (("A", name_a), ("B", name_b)):
            r = ratings.get(side, 0.0)
            d = delta.get(side, 0.0)
            text += f"  {nm} : {r:.1f}  ({d:+.1f})\n"

    if parent is not None:
        root = tk.Toplevel(parent)
        root.transient(parent)
        close_target = parent
    else:
        root = tk.Tk()
        close_target = root

    root.title("Permainan Selesai")
    root.configure(bg=BG)
    root.resizable(False, False)
    frame = tk.Frame(root, bg=BG, padx=28, pady=20)
    frame.pack()
    tk.Label(frame, text="Permainan Selesai", bg=BG, fg=ACCENT,
             font=("TkDefaultFont", 13, "bold")).pack(anchor="w", pady=(0, 6))
    tk.Label(frame, text=text, justify="left", bg=BG, fg=TEXT,
             font=("TkDefaultFont", 10)).pack(anchor="w")

    def _exit():
        try:
            close_target.destroy()
        except tk.TclError:
            pass

    tk.Button(frame, text="Exit", width=10, command=_exit,
              bg=BTN_BG, fg=BTN_FG, activebackground=ACCENT,
              activeforeground=BTN_FG, relief="flat", bd=0
              ).pack(pady=(14, 0))
    root.protocol("WM_DELETE_WINDOW", _exit)
    root.bind("<Return>", lambda _e: _exit())

    if parent is None:
        root.eval("tk::PlaceWindow . center")
        root.mainloop()
    else:
        root.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() // 2 - root.winfo_width() // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2 - root.winfo_height() // 2
        root.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        root.lift()
