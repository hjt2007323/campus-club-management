import re
from shutil import copytree

from fastapi.testclient import TestClient

from app import frontend
from app.main import create_app


def asset_url(html: str, path: str) -> str:
    match = re.search(r'"/assets/[0-9a-f]{16}/' + re.escape(path) + r'"', html)
    assert match is not None, path
    return match.group(0).strip('"')


def test_frontend_pages_bust_browser_cache_when_assets_change(tmp_path, monkeypatch):
    assets = tmp_path / "assets"
    copytree(frontend.STATIC_DIR, assets)
    monkeypatch.setattr(frontend, "STATIC_DIR", assets)

    with TestClient(create_app(f"sqlite:///{(tmp_path / 'frontend.db').as_posix()}")) as client:
        login = client.get("/login")
        dashboard = client.get("/")
        assert login.headers["cache-control"] == dashboard.headers["cache-control"] == "no-store"
        original_css = asset_url(login.text, "campus.css")
        original_script = asset_url(dashboard.text, "campus.js")
        assert asset_url(dashboard.text, "campus.css") == original_css
        assert client.get(asset_url(login.text, "login.js")).status_code == 200
        assert client.get(original_script).status_code == 200
        assert client.get(original_css).headers["cache-control"].endswith("immutable")

        (assets / "campus.css").write_text(".login-shell { display: grid; }", encoding="utf-8")
        updated_css = asset_url(client.get("/login").text, "campus.css")
        assert updated_css != original_css
        assert client.get(updated_css).text == ".login-shell { display: grid; }"
        assert client.get(original_css).status_code == 404

        (assets / "campus.js").write_text('"use strict";', encoding="utf-8")
        updated_script = asset_url(client.get("/").text, "campus.js")
        assert updated_script != original_script
        assert client.get(updated_script).text == '"use strict";'
