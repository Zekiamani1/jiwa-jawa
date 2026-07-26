
import argparse
import sys
import uuid

from game.engine import GameEngine
from game.logger import format_event
from game.rating import RatingStore
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
    p.add_argument("--log-dir", default="logs", help="direktori log JSONL")
    p.add_argument("--no-log", action="store_true", help="matikan penulisan log")
    p.add_argument("--ratings", default="ratings.json", help="berkas rating persisten")
    p.add_argument("--no-rating", action="store_true", help="matikan sistem rating")
    p.add_argument("--host", action="store_true", help="jadi host (dapat sisi A, jalan duluan)")
    p.add_argument("--hostip", type=str, help="IP host (untuk penantang)")
    p.add_argument("--hostport", type=int, help="port host (untuk penantang)")
    p.add_argument("--port", type=int, required=True, help="port lokal untuk mendengar")

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    network = Network(args.port)
    if args.host:
        def buat_config(hello):
            return {
                "game_id": str(uuid.uuid4()),
                "first_turn": "A",
                "names": {"A": args.names[0], "B": hello.get("name", args.names[1])},
            }
        print(f"menunggu penantang di port {args.port} ...")
        hello = network.accept(buat_config)
        player = "A"
        print(f"terhubung dengan {hello.get('name')} dari {network.peer[0]}")
    else:
        if not args.hostip or not args.hostport:
            raise SystemExit("penantang butuh --hostip dan --hostport")
        print(f"menghubungi {args.hostip}:{args.hostport} ...")
        network.connect(args.hostip, args.hostport, {"name": args.names[1]})
        player = "B"
        print("terhubung")
    config = network.config
    engine = GameEngine(
        names=config["names"],
        log_dir=args.log_dir,
        enable_log=not args.no_log,
        rating_store=None if args.no_rating else RatingStore(args.ratings),
        first_turn=config["first_turn"],
        player=player,
    )
    engine.game_id = config["game_id"]      
    engine.start()
    gui = GameGUI(engine, network)
    gui.run()
    network.close()
    if not args.no_log:
        print(f"\nlog: {engine.logger.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
