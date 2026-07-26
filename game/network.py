import json
import queue
import socket
import threading
import time
from .rules import Move
RTO = 0.3                # timeout untuk retransmisi, dalam detik
MAX_TRIES = 100          # maximal jumlah retransmisi sebelum lawan dianggap disconnect
CONNECT_TRIES = 60       # maximal jumlah percobaan handshake dari sisi klien
TICK = 0.05              # seberapa sering thread memeriksa timer
def move_from_dict(d):
    return Move(
        frm=d["from"],
        to=d["to"],
        captured=d["captured"],
        promote=bool(d["promote"]),
    )
def parse(raw):
    try:
        pkt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(pkt, dict) or "typ" not in pkt:
        return None
    return pkt

class Network:
# jadi ini tcp over udp dengan modif dikit. pas handshake ga cuman ngirim syn dan synack tapi juga data konfigurasi game. 
# teardown juga sekaligus informasi seperti pemenang dll.
# also agak disimplified dikit jadi rst psh gitu gitu ga ada.
# Format paket: {"typ": "DATA", "seq": 3, "data": {...}} or {"typ": "ACK",  "ack": 3}

    def __init__(self, port, max_tries=MAX_TRIES):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.port = port
        self.max_tries = max_tries
        self.peer = None
        self.config = None           
        self.status = "new"           # new | connected | closed | lost
        self.lock = threading.RLock()
        self.send_seq = 0           
        self.pending = {}           
        self.expected = 1            
        self.buffer = {}         #out of order buff
        self.inbox = queue.Queue() #in order
        self.running = False
        self.thread = None
        self._synack = None           
        self.stats = {"sent": 0, "resent": 0, "recv": 0, "dup": 0}
    def send_udp(self, pkt):
        if self.peer is None:
            return
        try:
            self.sock.sendto(json.dumps(pkt).encode("utf-8"), self.peer)
            self.stats["sent"] += 1
        except OSError:
            pass
    def recv_udp(self, timeout):
        try:
            self.sock.settimeout(timeout)
            raw, addr = self.sock.recvfrom(65535)
        except (socket.timeout, TimeoutError, OSError):
            return None, None
        self.stats["recv"] += 1
        return parse(raw), addr

    def send_ack(self, seq):
        self.send_udp({"typ": "ACK", "ack": seq})

    def send_reliable(self, typ, data):
        with self.lock:
            self.send_seq += 1
            pkt = {"typ": typ, "seq": self.send_seq, "data": data}
            self.pending[self.send_seq] = [pkt, time.time(), 1]
        self.send_udp(pkt)
        return pkt["seq"]

    def accept(self, config_fn):
        while True:
            pkt, addr = self.recv_udp(None)
            if pkt is not None and pkt.get("typ") == "SYN":
                self.peer = addr
                break
        hello = pkt.get("data") or {}
        self.config = config_fn(hello)
        self._synack = {"typ": "SYNACK", "seq": 0, "data": self.config}
        carry = None
        selesai = False
        for _ in range(self.max_tries):
            self.send_udp(self._synack)
            reply, _ = self.recv_udp(RTO)
            if reply is None:
                continue
            if reply.get("typ") == "ACK" and reply.get("ack") == 0:
                selesai = True
                break
            if reply.get("typ") in ("DATA", "FIN"):
                carry = reply          
                selesai = True
                break
        if not selesai:
            self.status = "lost"
            raise ConnectionError("penantang tidak menyelesaikan handshake")
        self.start()
        if carry is not None:
            self.handle(carry)
        return hello
    
    def connect(self, peer_ip, peer_port, hello):
        self.peer = (peer_ip, peer_port)
        syn = {"typ": "SYN", "seq": 0, "data": dict(hello)}
        for _ in range(CONNECT_TRIES):
            self.send_udp(syn)
            reply, addr = self.recv_udp(RTO)
            if reply is not None and reply.get("typ") == "SYNACK":
                self.peer = addr
                self.config = reply.get("data") or {}
                self.send_udp({"typ": "ACK", "ack": 0})
                self.start()
                return self.config
        self.status = "lost"
        raise ConnectionError(f"tidak bisa terhubung ke {peer_ip}:{peer_port}")

    def start(self):
        self.status = "connected"
        self.running = True
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def send_move(self, move):
        self.send_reliable("DATA", {"move": move.to_dict()})

    def send_dam(self, removed):
        self.send_reliable("DATA", {"dam": list(removed)})

    def send_end(self, winner, reason, move=None):
        data = {"winner": winner, "reason": reason}
        if move is not None:
            data["move"] = move.to_dict()
        self.send_reliable("FIN", data)

    def read(self, timeout=None):
        try:
            if timeout is None:
                return self.inbox.get_nowait()
            return self.inbox.get(timeout=timeout)
        except queue.Empty:
            return None

    def loop(self):
        while self.running:
            pkt, addr = self.recv_udp(TICK)
            if pkt is not None:
                self.handle(pkt)
            self.retransmit()

    def handle(self, pkt):
        typ = pkt.get("typ")
        if typ == "ACK":
            with self.lock:
                self.pending.pop(pkt.get("ack"), None)
            return
        if typ == "SYN":
            if self._synack is not None:
                self.send_udp(self._synack)
            return
        if typ == "SYNACK":
            self.send_udp({"typ": "ACK", "ack": 0})
            return
        if typ not in ("DATA", "FIN"):
            return
        seq = pkt.get("seq")
        if not isinstance(seq, int):
            return
        self.send_ack(seq)
        with self.lock:
            if seq < self.expected or seq in self.buffer:
                self.stats["dup"] += 1
                return
            self.buffer[seq] = pkt
            siap = []
            while self.expected in self.buffer:
                siap.append(self.buffer.pop(self.expected))
                self.expected += 1
        for p in siap:
            self.deliver(p)

    def deliver(self, pkt):
        data = pkt.get("data") or {}
        ev = {"move": None, "dam": None, "end": None, "lost": False}
        if data.get("move"):
            try:
                ev["move"] = move_from_dict(data["move"])
            except (KeyError, TypeError):
                return
        if data.get("dam"):
            ev["dam"] = list(data["dam"])
        if pkt.get("typ") == "FIN":
            ev["end"] = {"winner": data.get("winner"), "reason": data.get("reason")}
            self.status = "closed"
        self.inbox.put(ev)

    def retransmit(self):
        now = time.time()
        ulang = []
        hilang = False
        with self.lock:
            for seq, item in list(self.pending.items()):
                pkt, sent_at, tries = item
                if now - sent_at < RTO:
                    continue
                if tries >= self.max_tries:
                    hilang = True
                    break
                item[1] = now
                item[2] = tries + 1
                ulang.append(pkt)
            if hilang:
                self.pending.clear()
        if hilang:
            self.status = "lost"
            self.inbox.put({"move": None, "dam": None, "end": None, "lost": True})
            self.running = False
            return
        for pkt in ulang:
            self.send_udp(pkt)
            self.stats["resent"] += 1
    def close(self, timeout=20.0, linger=3.0):
        deadline = time.time() + timeout
        while self.running and time.time() < deadline:
            with self.lock:
                if not self.pending:
                    break
            time.sleep(TICK)
        akhir = time.time() + linger
        while self.running and time.time() < akhir:
            time.sleep(TICK)
        self.running = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.status == "connected":
            self.status = "closed"
        try:
            self.sock.close()
        except OSError:
            pass
