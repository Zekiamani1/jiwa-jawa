import sys
import uuid
from game.engine import GameEngine
from game.network import Network
from game.gui import GameGUI
from game.rating import RatingStore
from game.launcher import run_launcher, wait_for_handshake, show_end, show_error


def main():
    while True:
        cfg = run_launcher()
        if cfg is None:
            return 0
        network = Network(cfg["port"])
        if cfg["mode"] == "host":
            task = lambda: network.accept(lambda hello: {
                "game_id": str(uuid.uuid4()),
                "first_turn": "A",
                "names": {"A": cfg["name"], "B": hello.get("name", "pemain-B")},
            })
        else:
            task = lambda: network.connect(
                cfg["host_ip"], cfg["host_port"], {"name": cfg["name"]}
            )
        error = wait_for_handshake(cfg, task)
        if error is not None:
            show_error("Gagal", f"Handshake gagal: {error}")
            network.close()
            continue

        config = network.config
        rating_store = RatingStore()
        engine = GameEngine(
            names=config["names"],
            first_turn=config["first_turn"],
            player="A" if cfg["mode"] == "host" else "B",
            rating_store=rating_store,
        )
        engine.game_id = config["game_id"]
        rating_info = {}

        def _capture_rating(ev):
            if ev.get("event") == "rating_update":
                rating_info.update(ev.get("detail", {}))

        engine.on_event(_capture_rating)
        engine.start()

        def _on_end(_winner, _reason):
            show_end(engine, gui.end_info, rating_info or None, parent=gui.root)

        gui = GameGUI(engine, network, on_end=_on_end)
        gui.run()
        network.close()
        print(f"\nlog: {engine.logger.path}")


if __name__ == "__main__":
    sys.exit(main() or 0)
