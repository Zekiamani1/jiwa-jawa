"""Logging permainan (kebutuhan wajib).

Setiap kejadian ditulis append-only sebagai satu baris JSON ke
`logs/game_<game_id>.jsonl`, dengan `seq` naik monoton + `ts`, sehingga
riwayat permainan bisa dibaca ulang urut.

CLI replay:
    python3 -m game.logger --list
    python3 -m game.logger --replay logs/game_<id>.jsonl
"""
import json
import os
import time
from datetime import datetime

DEFAULT_LOG_DIR = "logs"


class Event:
    """Nama-nama event log."""

    GAME_START = "game_start"
    MOVE = "move"
    CAPTURE = "capture"
    PROMOTION = "promotion"
    DAM = "dam"
    GAME_OVER = "game_over"
    RATING_UPDATE = "rating_update"


class Logger:
    """Penulis log JSONL untuk satu permainan."""

    def __init__(self, game_id, log_dir=DEFAULT_LOG_DIR, enabled=True):
        self.game_id = game_id
        self.log_dir = log_dir
        self.enabled = enabled
        self.seq = 0
        self.events = []
        self.path = os.path.join(log_dir, f"game_{game_id}.jsonl")
        if self.enabled:
            os.makedirs(log_dir, exist_ok=True)

    def emit(self, actor, event, detail=None):
        """Buat, tulis, dan kembalikan satu event."""
        self.seq += 1
        ev = {
            "seq": self.seq,
            "ts": time.time(),
            "game_id": self.game_id,
            "actor": actor,
            "event": event,
            "detail": detail or {},
        }
        self.events.append(ev)
        if self.enabled:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")
        return ev

    def tail(self, n=12):
        return self.events[-n:]


# ---------------------------------------------------------------------------
# Pembacaan & replay
# ---------------------------------------------------------------------------
def read_log(path):
    """Baca file JSONL; baris rusak ditandai, bukan menggagalkan pembacaan."""
    events = []
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                events.append({"_corrupt": True, "_line": lineno})
    return events


def _fmt_ts(ts):
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "--:--:--"


def format_event(ev):
    """Satu baris riwayat yang terbaca manusia."""
    if ev.get("_corrupt"):
        return f"[baris {ev['_line']}] <baris rusak>"

    detail = ev.get("detail", {})
    name = ev.get("event", "?")
    head = f"[{ev.get('seq', '?'):>4}] {_fmt_ts(ev.get('ts', 0))} {ev.get('actor', '?'):<6}"

    if name == Event.GAME_START:
        return f"{head} MULAI   giliran pertama={detail.get('first_turn')} {detail.get('names', {})}"
    if name == Event.MOVE:
        arrow = " -> ".join([detail.get("from", "?")] + list(detail.get("path", [])))
        extra = f" (makan {len(detail.get('captures', []))})" if detail.get("captures") else ""
        return f"{head} LANGKAH #{detail.get('move_no', '?')} {arrow}{extra}"
    if name == Event.CAPTURE:
        victims = ", ".join(
            f"{c.get('node')}{'*' if c.get('king') else ''}" for c in detail.get("captured", [])
        )
        return f"{head} MAKAN   {victims}"
    if name == Event.PROMOTION:
        return f"{head} PROMOSI bidak di {detail.get('node')} menjadi raja"
    if name == Event.DAM:
        return f"{head} DAM     menghapus {detail.get('removed')} milik {detail.get('offender')}"
    if name == Event.GAME_OVER:
        return f"{head} SELESAI pemenang={detail.get('winner')} alasan={detail.get('reason')}"
    if name == Event.RATING_UPDATE:
        ratings, delta = detail.get("ratings", {}), detail.get("delta", {})
        parts = " ".join(
            f"{s}={ratings.get(s, 0):.1f}({delta.get(s, 0):+.1f})" for s in sorted(ratings)
        )
        return f"{head} RATING  {parts}"
    return f"{head} {name.upper():<7} {json.dumps(detail, ensure_ascii=False)}"


def replay(path):
    """Ubah satu file log menjadi riwayat terbaca manusia."""
    events = read_log(path)
    lines = [f"=== replay {path} ({len(events)} event) ==="]
    lines += [format_event(ev) for ev in events]
    moves = sum(1 for e in events if e.get("event") == Event.MOVE)
    caps = sum(
        len(e.get("detail", {}).get("captured", []))
        for e in events
        if e.get("event") == Event.CAPTURE
    )
    lines.append(f"=== ringkasan: {moves} langkah, {caps} bidak dimakan ===")
    return lines


def list_logs(log_dir=DEFAULT_LOG_DIR):
    if not os.path.isdir(log_dir):
        return []
    return sorted(os.path.join(log_dir, f) for f in os.listdir(log_dir) if f.endswith(".jsonl"))


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Pembaca log Catur Jawa")
    parser.add_argument("--replay", metavar="FILE", help="cetak riwayat sebuah file log")
    parser.add_argument("--list", action="store_true", help="daftar file log tersedia")
    parser.add_argument("--dir", default=DEFAULT_LOG_DIR, help="direktori log")
    args = parser.parse_args(argv)

    if args.list or not args.replay:
        logs = list_logs(args.dir)
        if not logs:
            print(f"(tidak ada log di {args.dir}/)")
        for path in logs:
            print(path)
        if not args.replay:
            return 0

    for line in replay(args.replay):
        print(line)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
