from pathlib import Path


def test_camera_source_neither_records_video_nor_calculates_fps() -> None:
    source = (Path(__file__).parents[2] / "src/surveillance/camera/source.py").read_text(encoding="utf-8")
    assert "VideoWriter" not in source
    assert "fps" not in source.lower()
