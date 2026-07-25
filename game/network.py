import socket
import json
from .rules import Move
class Network:
    def __init__(self, ip, port,ip2=None,port2=None):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))
        self.port = port
        self.ip=ip
        self.ip2=ip2
        self.port2=port2
    def sendStart(self,ip2=None,port2=None):
        if not port2:
            port2=self.port2
            ip2=self.ip2
        self.sock.sendto("START".encode(), (ip2, port2))

    def recvStart(self):
        data, addr = self.sock.recvfrom(4096)
        while data.decode() != "START":
            data, addr = self.sock.recvfrom(4096)
        self.port2 = addr[1]
        self.ip2=addr[0]    
        return
    def sendmove(self, data):
        self.sock.sendto(json.dumps(data.to_dict()).encode(), (self.ip, self.port2))

    def recvmove(self):
        data, _ = self.sock.recvfrom(4096)
        d = json.loads(data.decode())
        move = Move(
            frm=d["from"],
            path=tuple(d["path"]),
            captures=tuple(d["captures"]),
            promote=d["promote"],
        )
        return move
