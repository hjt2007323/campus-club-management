import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def login_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CAMPUS_ADMIN_TOKEN", "admin-fixture-token")
    monkeypatch.setenv("CAMPUS_STUDENT_TOKEN", "student-fixture-token")
    monkeypatch.setenv("CAMPUS_STUDENT_TOKENS", '{"network-club":"network-fixture-token"}')
    return f"sqlite:///{(tmp_path / 'login.db').as_posix()}"


def test_demo_account_selection_changes_session_and_business_permissions(login_database):
    with TestClient(create_app(login_database, demo_login=True)) as client:
        landing = client.get("/", follow_redirects=False)
        assert landing.status_code == 303
        assert landing.headers["location"] == "/login"
        assert client.get("/?guest=1").status_code == 200
        assert client.get("/me").status_code == 401

        options = client.get("/session/options").json()
        assert options["mode"] == "demo"
        assert [account["id"] for account in options["accounts"]] == ["student", "network-club", "admin"]
        assert "fixture-token" not in str(options)

        signed_in = client.post("/session", json={"account_id": "student"})
        assert signed_in.status_code == 200
        cookie = signed_in.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        old_cookie = dict(client.cookies)
        assert client.get("/me").json() == {"id": "student", "role": "student"}
        assert client.get("/statistics").status_code == 403

        assert client.post("/session", json={"account_id": "admin"}).status_code == 200
        old_headers = {"Cookie": "; ".join(f"{name}={value}" for name, value in old_cookie.items())}
        assert client.get("/me", headers=old_headers).status_code == 401
        assert client.get("/statistics").status_code == 200
        assert client.post("/clubs", json={"name": "权限边界测试"}).status_code == 403
        assert client.delete("/session", headers={"Origin": "https://other.example"}).status_code == 403
        assert client.get("/me").json()["id"] == "admin"
        assert client.delete("/session").status_code == 200
        assert client.get("/me").status_code == 401

    with TestClient(create_app(login_database, demo_login=True)) as new_client:
        new_client.cookies.update(old_cookie)
        assert new_client.get("/me").status_code == 401


def test_normal_mode_keeps_token_login_and_api_authentication(login_database):
    with TestClient(create_app(login_database)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/session/options").json() == {"mode": "token", "accounts": []}
        assert client.post("/session", json={"account_id": "admin"}).status_code == 403
        assert client.post("/session", json={"token": "wrong-token"}).status_code == 401
        assert client.post("/session", json={"token": "admin-fixture-token"}).status_code == 200
        assert client.get("/me").json() == {"id": "admin", "role": "admin"}

        headers = {"Authorization": "Bearer network-fixture-token"}
        assert client.get("/me", headers=headers).json() == {"id": "network-club", "role": "student"}
        assert client.post("/venues", json={"name": "另一个站点", "capacity": 20},
                           headers={"Origin": "https://other.example"}).status_code == 403
