"""build_features 10차원 + 분모 0 안전성."""
from ml_server.feature.feature_builder import build_features


def test_feature_dimension_is_10():
    feats = build_features(
        cpu=50, memory=60, gpu_pct=70, vram_mb=2048,
        gpu_total_mb=8192, disk_r=1.0, disk_w=2.0, power=120.0,
    )
    assert len(feats) == 10  # raw 7 + derived 3


def test_zero_gpu_pct_does_not_divide_by_zero():
    """gpu_pct=0이라도 cpu/(gpu+0.001) 계산이 정상 수치여야 한다."""
    feats = build_features(
        cpu=80.0, memory=50.0, gpu_pct=0.0, vram_mb=0.0,
        gpu_total_mb=8192, disk_r=0.0, disk_w=0.0, power=0.0,
    )
    assert all(isinstance(v, (int, float)) for v in feats)
    # cpu/(0+0.001) = 80000
    assert abs(feats[7] - 80000.0) < 1e-3


def test_zero_gpu_total_mb_falls_back_to_8192():
    feats = build_features(
        cpu=10, memory=20, gpu_pct=50, vram_mb=4096,
        gpu_total_mb=0, disk_r=0, disk_w=0, power=0,
    )
    # derived[2] = gpu_pct * (1 - vram/8192) = 50 * (1 - 0.5) = 25
    assert abs(feats[9] - 25.0) < 1e-6
