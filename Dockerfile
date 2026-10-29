# Supertonic-3 TTS (Wyoming protocol) - standalone GPU server for Home Assistant
# Based on: JulienDeveaux/HA-Supertonic-Addon (server code) + supertone-inc/supertonic-py (SDK)
# CUDA enablement: onnxruntime-gpu + provider override in gpu_entry.py
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Supertonic SDK + Wyoming protocol (pins match the HA add-on's Dockerfile),
# then swap the CPU-only onnxruntime for the CUDA build.
# onnxruntime-gpu 1.20.x needs CUDA 12.x + cuDNN 9 (provided by the base image).
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      'supertonic>=1.2.1,<2.0' \
      'wyoming>=1.5.0' \
      'zeroconf>=0.132.0' && \
    pip uninstall -y onnxruntime && \
    pip install --no-cache-dir 'onnxruntime-gpu==1.20.2'

# Bake Supertonic-3 weights into the image (~385 MB), same relocation trick
# the add-on uses: SDK downloads to its cache dir, we move it to a stable path.
RUN python3 -c "from supertonic import TTS; TTS(model='supertonic-3', auto_download=True)" && \
    SRC=$(python3 -c "from supertonic.loader import get_model_cache_dir; print(get_model_cache_dir('supertonic-3'))") && \
    test -d "$SRC/onnx" || (echo "ERROR: unexpected SDK cache layout at $SRC" && exit 1) && \
    mv "$SRC" /opt/supertonic-models && \
    ls -la /opt/supertonic-models/onnx /opt/supertonic-models/voice_styles

# Wyoming server vendored from the add-on repo (supertonic_server.py @ 1b5d612a,
# 2026-05-14, "fix: supertonic3 predictor under allocation") so builds are
# reproducible - we only added one startup log line advertising voice/language
# counts. One-line diff from upstream, see git history.
# Note: upstream's run() script passes --zeroconf; we skip it because mDNS
# across docker bridge networks is unreliable - add the integration manually by IP:port.
COPY supertonic_server.py /opt/supertonic_server.py
COPY describe_probe.py /opt/describe_probe.py
COPY gpu_entry.py /opt/gpu_entry.py

EXPOSE 10300
CMD ["--uri", "tcp://0.0.0.0:10300", "--data-dir", "/data", "--models-dir", "/opt/supertonic-models"]
ENTRYPOINT ["python3", "/opt/gpu_entry.py"]
