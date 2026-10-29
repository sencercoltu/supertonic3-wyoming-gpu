# Supertonic-3 TTS — standalone Wyoming container (RTX 3090)

Runs the Wyoming TTS server from [JulienDeveaux/HA-Supertonic-Addon](https://github.com/JulienDeveaux/HA-Supertonic-Addon)
**outside Home Assistant**, as a plain Docker container, with inference on the NVIDIA GPU.

## How the GPU enablement works (verified in the SDK source)

- Supertonic-3 is 4 ONNX graphs (duration predictor, text encoder, vector estimator, vocoder).
- The `supertonic` PyPI SDK requests execution providers via `supertonic.loader.DEFAULT_ONNX_PROVIDERS`
  — hardcoded to `["CPUExecutionProvider"]` upstream, but read at call time, so it can be
  overridden at process start (`gpu_entry.py`). No sed hacks, no forked server code.
- The image swaps `onnxruntime` → `onnxruntime-gpu` (CUDA EP), on a CUDA 12.6 + cuDNN 9 base.
- The Wyoming server is **vendored** into this repo as `supertonic_server.py` (from
  `JulienDeveaux/HA-Supertonic-Addon` @ `1b5d612a`, 2026-05-14). One local diff: a startup
  log line reporting how many voices/languages it advertises. Builds are reproducible now —
  no silent drift from an upstream `main` push.
- Voices/config come from `/data/options.json` (the add-on Supervisor normally writes this;
  here we just mount it).

## CI: GitHub builds the image (GHCR)

Push this folder to a GitHub repo (use a **lowercase** repo name — GHCR requires it).
`.github/workflows/build.yml` then builds on every push to `main` and publishes:

```
ghcr.io/<owner>/supertonic3-wyoming-gpu:latest
ghcr.io/<owner>/supertonic3-wyoming-gpu:<commit-sha>
```

No registry secrets needed — it uses the built-in `GITHUB_TOKEN` with `packages: write`.

Pulling from your docker host:

- **Public repo** → the package must be made public once (repo → Packages → `<repo>` →
  Package settings → Change visibility → Public). Then `docker pull` works anonymously.
- **Private repo** → `docker login ghcr.io -u <you>` with a PAT that has `read:packages`
  on the docker host, once.

## Run

```bash
docker compose pull && docker compose up -d    # image from GHCR
# or build locally:  docker compose up -d --build
docker logs -f supertonic
```

Healthy startup looks like:

```
[gpu-entry] onnxruntime 1.20.2, available providers: ['CUDAExecutionProvider', 'CPUExecutionProvider', ...]
[gpu-entry] CUDA requested for all 4 ONNX sessions (CPU fallback kept)
...
Using ONNX providers: ['CUDAExecutionProvider', 'CPUExecutionProvider']
✓ Loaded voice: M1 ... F5
Starting Wyoming server on tcp://0.0.0.0:10300
```

If you see `CPUExecutionProvider` only in the *second* line, the nvidia runtime isn't
reaching the container (`nvidia-smi` inside: `docker exec supertonic nvidia-smi`).

## Verify GPU actually does the work

```bash
docker exec supertonic nvidia-smi     # supertonic should hold a few hundred MB – ~1.5 GB
# quick synthetic benchmark (run twice: once with SUPERTONIC_GPU=1, once =0):
docker exec supertonic python3 -c "
import time
from supertonic import TTS
t = TTS(model='supertonic-3', model_dir='/opt/supertonic-models', auto_download=False)
s = t.get_voice_style(voice_name='F2')
t0 = time.perf_counter()
wav, dur = t.synthesize('The kitchen lights are at 40 percent and the thermostat is set to 21 degrees.', voice_style=s, lang='en', total_steps=5, speed=1.2)
print(f'{time.perf_counter()-t0:.2f}s wall for {dur[0]:.1f}s audio')"
```

Realistic expectation: at `quality: 5` this model is already 5–15× realtime on a modern
x86 CPU — the CUDA provider mostly buys **offload from your HA host + concurrency
headroom**, not necessarily lower single-request latency. Benchmark both and keep the
faster one; keeping `CPUExecutionProvider` as fallback means unsupported ops auto-fallback.

## Home Assistant wiring

1. Settings → **Devices & Services → Add Integration → Wyoming Protocol** →
   `<docker-host-ip>` : **10301** (no mDNS across docker bridge → add manually).
2. You get a `supertonic3` TTS entity → Settings → **Voice assistants** → your assistant →
   Text-to-speech → select it.
3. **310 voices** = `<lang>_<voice>` (`en_F2`, `tr_M4`, …), pick a default in the entity
   options, or per call:

HA derives the assistant's TTS **Language** dropdown from the union of the `languages`
field on every advertised voice. If it shows only one language (or Dev tools → States →
`tts.supertonic3` shows `supported_languages: ['en']`), run the probe against the running
container to see what the server really put on the wire:

```
docker exec supertonic3 python3 /opt/describe_probe.py
# program : supertonic3 v3.0.0
# voices  : 310
# langs   : 31 -> ar, bg, cs, ... tr, uk, vi
```

- `langs : 31` but HA still lists one → the HA side dropped them (known voice-preset
  option-flow quirk; check for a Home Assistant core update, and use the entity Options
  or `options.voice` per call in the meantime — both work regardless).
- `langs : 1` or a `WARNING: voices carry NO languages field` → the server/image is at
  fault; the probe's `sample` JSON shows the exact serialized fields to fix.

```yaml
action: tts.speak
target:
  entity_id: tts.supertonic3
data:
  media_player_entity_id: media_player.woonkamer
  message: Goede avond, de verwarming staat op 21 graden.
  options:
    voice: en_F2
```

## Config (`options.json`, mounted at /data/options.json)

| Key | Meaning | Range |
|---|---|---|
| `default_language` | ISO-2 fallback when voice has no lang prefix | 31 codes + `na`; **server default is `fr`** if the file is absent |
| `default_voice` | Fallback timbre | `M1–M5`, `F1–F5` |
| `speed` | speech rate | 0.5–2.0 |
| `volume_boost` | linear gain (clipped) | 1.0–3.0 (server default 2.0 is loud) |
| `quality` | diffusion steps → voice quality vs speed | 2–16 |

Changes need `docker restart supertonic3` (file is read at startup).

## Notes & caveats

- **Port**: container listens on 10300; host mapping is 10301 because your whisper
  container already maps 10300. If you'd rather run Kokoro here too, pick any free host port.
- **VRAM**: budget ~0.5–1.5 GB with CUDA (ORT arena). Fine alongside whisper + an 8B LLM on your 24 GB card.
- **Turkish**: `tr` is fully in the advertised voice set — this is the main reason to
  choose Supertonic over Kokoro.
- **Streaming**: the server streams sentence-by-sentence (and strips last-word clipping
  with a 500 ms tail pad), so long announcements start playing early.
- Supertonic-3 weights are OpenRAIL-M (commercial use OK with use restrictions); the
  server wrapper is from the add-on repo — keep both when redistributing.
- To pick up upstream server fixes later: re-copy `supertonic_server.py` from
  `JulienDeveaux/HA-Supertonic-Addon` (`supertonic_tts/rootfs/usr/bin/`), re-apply the
  one-line advertise log, and note the upstream commit here.
