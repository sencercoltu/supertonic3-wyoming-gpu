#!/usr/bin/env python3
"""
Raw Wyoming-protocol probe: asks the server what it actually advertises.

Prints the voice count, the union of per-voice language codes, and one raw
voice JSON object (so you can see the exact field names on the wire). This is
what Home Assistant's Wyoming integration receives on its `Describe` handshake,
so it settles any "HA only shows English" dispute:

  docker exec supertonic3 python3 /opt/describe_probe.py

Exit code 0 always (informational), non-zero only on connection failure.
"""

import json
import socket
import struct
import sys

URI = sys.argv[1] if len(sys.argv) > 1 else "tcp://127.0.0.1:10300"


def main() -> int:
    host, _, port = URI.removeprefix("tcp://").partition(":")
    sock = socket.create_connection((host, int(port or 10300)), timeout=10)

    def send(event: dict) -> None:
        body = json.dumps(event).encode()
        sock.sendall(struct.pack(">I", len(body)) + body)

    def recv() -> dict:
        (size,) = struct.unpack(">I", recv_exact(4))
        return json.loads(recv_exact(size))

    def recv_exact(n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise EOFError("connection closed mid-frame")
            buf += chunk
        return buf

    # wyoming.event.Event wire format: 4-byte big-endian length + JSON
    send(
        {
            "type": "describe",
            "data": [],
            "id": "",
            "created_at": "2026-01-01T00:00:00+00:00",
            "origin": "",
        }
    )
    info = recv()

    programs = info.get("tts", [])
    if not programs:
        print("server sent no tts program in Info event!")
        print(json.dumps(info, indent=2)[:2000])
        return 0

    program = programs[0]
    voices = program.get("voices", [])
    langs = sorted({code for v in voices for code in v.get("languages", [])})

    print(f"program : {program.get('name')} v{program.get('version')}")
    print(f"voices  : {len(voices)}")
    print(f"langs   : {len(langs)} -> {', '.join(langs)}")

    missing = [v.get("name") for v in voices if not v.get("languages")]
    if missing:
        print(f"WARNING : {len(missing)} voices carry NO languages field, e.g. {missing[:5]}")

    print("sample  :", json.dumps(voices[0]) if voices else "(none)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
