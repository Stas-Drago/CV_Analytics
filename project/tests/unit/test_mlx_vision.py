from pathlib import Path
from subprocess import CompletedProcess

import pytest

from surveillance.analysis.vision import MlxVisionClient, parse_mlx_description, parse_vision_json


def test_parse_vision_json_ignores_cli_preamble() -> None:
    payload = parse_vision_json('loading model...\n{"description_ru":"На кадре автомобиль.","visible_objects":["автомобиль"],"observed_actions":[],"uncertainty":""}')
    assert payload.description_ru == "На кадре автомобиль."


def test_parse_mlx_description_accepts_concise_caption() -> None:
    payload = parse_mlx_description("На кадре виден автомобиль у здания.")
    assert payload.description_ru == "На кадре виден автомобиль у здания."


def test_mlx_client_uses_isolated_python_and_cleans_temp_image(tmp_path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    called = {}

    def runner(command, **kwargs):
        called["command"] = command
        return CompletedProcess(command, 0, '{"description_ru":"Виден автомобиль.","visible_objects":[],"observed_actions":[],"uncertainty":""}', "")

    client = MlxVisionClient("/mlx/python", str(model), 5, 100, "test-v1", runner=runner)
    result = client.describe(b"jpeg", "car", 0.9, [1, 2, 3, 4])
    assert result.description == "Виден автомобиль."
    assert called["command"][0] == "/mlx/python"
    assert called["command"][1].endswith("scripts/mlx_vision_infer.py")
    assert not Path(called["command"][-1]).exists()


def test_mlx_client_requires_model_directory(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        MlxVisionClient("python", str(tmp_path / "missing"), 5, 100, "test")
