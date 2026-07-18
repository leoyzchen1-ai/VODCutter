"""GPU probe: default 'auto' uses CUDA when present, else CPU/int8.

A customer's machine likely has no CUDA -- degrade, don't crash.
"""


def _cuda_count() -> int:
    try:
        import ctranslate2  # ships with faster-whisper
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


def pick_device(requested: str = "auto") -> tuple[str, str]:
    if requested == "cpu":
        return ("cpu", "int8")
    if requested == "cuda":
        return ("cuda", "float16")
    if _cuda_count() > 0:
        return ("cuda", "float16")
    print("[device] no CUDA GPU found; using CPU/int8 (slower but works everywhere)")
    return ("cpu", "int8")
