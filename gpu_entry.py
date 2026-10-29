#!/usr/bin/env python3
"""Launcher for the Wyoming Supertonic-3 server with CUDA enabled.

The supertonic SDK (supertonic/loader.py) resolves execution providers as:

    providers = DEFAULT_ONNX_PROVIDERS            # module global, read per call
    valid = [p for p in providers if p in ort.get_available_providers()]

DEFAULT_ONNX_PROVIDERS ships hardcoded to ["CPUExecutionProvider"], but it is
read from the *loader module's namespace* at call time — so we can swap it for
CUDA before the server starts, without patching any upstream file.

Set SUPERTONIC_GPU=0 to force CPU (useful for A/B benchmarking).
"""
import os
import runpy
import sys

SERVER = "/opt/supertonic_server.py"
DEFAULT_ARGS = [
    "--uri", "tcp://0.0.0.0:10300",
    "--data-dir", "/data",
    "--models-dir", "/opt/supertonic-models",
]


def main() -> None:
    want_gpu = os.environ.get("SUPERTONIC_GPU", "1").lower() not in ("0", "false", "off", "")

    import onnxruntime as ort
    available = ort.get_available_providers()
    print(f"[gpu-entry] onnxruntime {ort.__version__}, available providers: {available}", flush=True)

    if want_gpu and "CUDAExecutionProvider" in available:
        import supertonic.loader as loader
        loader.DEFAULT_ONNX_PROVIDERS = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        print("[gpu-entry] CUDA requested for all 4 ONNX sessions (CPU fallback kept)", flush=True)
    elif want_gpu:
        print("[gpu-entry] CUDAExecutionProvider missing -> CPU mode. "
              "Check the nvidia runtime / GPU reservation.", flush=True)
    else:
        print("[gpu-entry] SUPERTONIC_GPU=0 -> CPU mode", flush=True)

    sys.argv = [SERVER] + (sys.argv[1:] or DEFAULT_ARGS)
    runpy.run_path(SERVER, run_name="__main__")


if __name__ == "__main__":
    main()
