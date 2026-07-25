
import argparse
import sys

from game.engine import GameEngine
from game.logger import format_event
from game.rating import RatingStore
from game.rules import RuleOptions
import threading
from game.network import Network
from game.gui import GameGUI 

class ConsoleUI:
    """Antarmuka teks sederhana."""

    def __init__(self, engine):
        self.engine = engine
        engine.on_event(lambda ev: print(format_event(ev)))

    def render(self):
        e = self.engine
        print()
        for y in range(8, -1, -1):
            cells = []
            for x in range(4):
                piece = e.state.piece_at(f"n{x}_{y}")
                if piece is None:
                    cells.append(".")
                else:
                    ch = "a" if piece.owner == "A" else "b"
                    cells.append(ch.upper() if piece.king else ch)
            marker = ""
            if y in (0, 8):
                node = "apex_A" if y == 0 else "apex_B"
                apex = e.state.piece_at(node)
                marker = f"   {node}[{'.' if apex is None else apex.owner}]"
            print(f"  y{y}  " + " ".join(cells) + marker)
        print("       " + " ".join(f"x{x}" for x in range(4)))
        counts = e.state.counts()
        print(
            f"  giliran={e.state.turn}  A={counts['A']['pieces']} B={counts['B']['pieces']}  "
            f"status={e.state.status}"
        )
        print("  (huruf besar = raja)")

    def choose(self, moves):
        for i, m in enumerate(moves):
            print(f"  [{i:>2}] {m.describe()}")
        while True:
            try:
                raw = input(f"langkah {self.engine.state.turn} (nomor / q keluar) > ").strip()
            except EOFError:
                return None
            if raw.lower() in ("q", "quit", "keluar"):
                return None
            if raw.isdigit() and 0 <= int(raw) < len(moves):
                return moves[int(raw)]
            print("  masukan tidak dikenal")


def build_parser():
    p = argparse.ArgumentParser(
        description="Catur Jawa (Dam-daman) — 2 pemain satu komputer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--gui", action="store_true", help="pakai GUI Tkinter")
    p.add_argument("--names", nargs=2, metavar=("A", "B"), default=["pemain-A", "pemain-B"])
    p.add_argument("--no-backward", action="store_true", help="bidak biasa tidak boleh mundur")
    p.add_argument("--dam-penalty", action="store_true", help="aktifkan mode DAM sosial")
    p.add_argument("--draw-after", type=int, default=40, help="seri setelah N langkah tanpa kemajuan")
    p.add_argument("--log-dir", default="logs", help="direktori log JSONL")
    p.add_argument("--no-log", action="store_true", help="matikan penulisan log")
    p.add_argument("--ratings", default="ratings.json", help="berkas rating persisten")
    p.add_argument("--no-rating", action="store_true", help="matikan sistem rating")
    p.add_argument("--host", action="store_true")
    p.add_argument("--hostip", type=str)
    p.add_argument("--hostport", type=int)
    p.add_argument("--port", type=int)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    port = args.port
    network=Network("0.0.0.0", port)
    if args.host:
        network.recvStart()
        network.sendStart()
        player="A"
    else:
        ip2 = args.hostip
        port2 = args.hostport
        network.sendStart(ip2,port2)
        network.recvStart()
        player="B"
    engine = GameEngine(
        options=RuleOptions(
            allow_backward=not args.no_backward,
            dam_penalty=args.dam_penalty,
            draw_no_progress=args.draw_after,
        ),
        names={"A": args.names[0], "B": args.names[1]},
        log_dir=args.log_dir,
        enable_log=not args.no_log,
        rating_store=None if args.no_rating else RatingStore(args.ratings),
        player=player
    )
    engine.start()
    gui = GameGUI(engine,network)
    def receive_loop():
        while True:
            packet = network.recvmove()
            move = packet
            engine.apply_move(move)
            gui._redraw()
    receiver = threading.Thread(
        target=receive_loop,
        daemon=True
    )

    receiver.start()
    gui.run()
    if not args.no_log:
        print(f"\nlog: {engine.logger.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
