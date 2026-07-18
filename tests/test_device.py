import cutter.device as device


def test_explicit_cpu():
    assert device.pick_device("cpu") == ("cpu", "int8")


def test_explicit_cuda():
    assert device.pick_device("cuda") == ("cuda", "float16")


def test_auto_with_gpu(monkeypatch):
    monkeypatch.setattr(device, "_cuda_count", lambda: 1)
    assert device.pick_device("auto") == ("cuda", "float16")


def test_auto_without_gpu(monkeypatch):
    monkeypatch.setattr(device, "_cuda_count", lambda: 0)
    assert device.pick_device("auto") == ("cpu", "int8")
