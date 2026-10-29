#!/usr/bin/env python3
"""
Wyoming Describe probe: prints what the server actually advertises on the wire.

Uses the container's own `wyoming` library (same AsyncTcpClient + Describe +
Info.from_event sequence that Home Assistant's Wyoming integration runs), so
the framing/version skew risk of a hand-rolled protocol client is zero.

  docker exec supertonic3 python3 /opt/describe_probe.py

Prints voice count, the union of per-voice language codes, and one raw voice
object as serialized JSON - i.e. exactly the data HA turns into its
`supported_languages` attribute.
"""

import asyncio
import json
import sys


async def main() -> int:
    from wyoming.client import AsyncTcpClient
    from wyoming.info import Describe, Info

    try:
        from wyoming.version import __version__ as wyoming_version
    except ImportError:
        wyoming_version = "?"

    host, port = "127.0.0.1", 10300
    if len(sys.argv) > 1 and sys.argv[1].startswith("tcp://"):
        host, _, p = sys.argv[1][len("tcp://"):].partition(":")
        port = int(p or 10300)

    client = AsyncTcpClient(host, port)
    await client.connect()
    try:
        await client.write_event(Describe().event())
        event = await client.read_event()
    finally:
        await client.disconnect()

    if event is None:
        print("connection closed before a reply")
        return 1
    if not Info.is_type(event.type):
        print(f"expected an 'info' event, got '{event.type}'")
        return 1

    info = Info.from_event(event)
    if not info.tts:
        print("server sent no tts program in Info event!")
        return 1

    program = info.tts[0]
    voices = [v for v in program.voices if v.installed]
    langs = sorted({code for v in voices for code in v.languages})

    print(f"wyoming lib : {wyoming_version}")
    print(f"program     : {program.name} v{program.version}")
    print(f"voices      : {len(voices)} installed (of {len(program.voices)} advertised)")
    print(f"langs       : {len(langs)} -> {', '.join(langs)}")

    missing = [v.name for v in voices if not v.languages]
    if missing:
        print(f"WARNING     : {len(missing)} voices carry NO languages field, e.g. {missing[:5]}")

    if voices:
        print("sample      :", json.dumps(voices[0].to_dict()))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
