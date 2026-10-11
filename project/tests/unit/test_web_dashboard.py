from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[2] / "web"


def test_dashboard_uses_safe_dom_rendering() -> None:
    javascript = "\n".join(path.read_text(encoding="utf-8") for path in (WEB_ROOT / "src").glob("*.js"))
    forbidden = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")
    assert all(value not in javascript for value in forbidden)
    assert "textContent" in javascript


def test_dashboard_does_not_request_protected_media_before_authorization() -> None:
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'id="camera-stream"' in html
    camera_tag = html.split('id="camera-stream"', 1)[1].split(">", 1)[0]
    assert "src=" not in camera_tag


def test_frontend_has_no_database_or_secret_dependencies() -> None:
    sources = "\n".join(path.read_text(encoding="utf-8") for path in WEB_ROOT.rglob("*.*"))
    forbidden = ("psycopg", "postgresql://", "DATABASE_URL", "POSTGRES_PASSWORD")
    assert all(value not in sources for value in forbidden)
