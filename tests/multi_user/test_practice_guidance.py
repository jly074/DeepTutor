from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from deeptutor.api.routers import auth, practice, question_notebook
from deeptutor.services.auth import TokenPayload
from deeptutor.services.workspace.activity import WorkspaceActivityMiddleware


def test_guidance_uses_authenticated_account_and_workspace(mu_isolated_root, monkeypatch, as_user):
    monkeypatch.setattr(auth, "AUTH_ENABLED", True)
    monkeypatch.setattr(
        auth,
        "decode_token",
        lambda token: (
            TokenPayload(username=token, role="user", user_id=token)
            if token in {"alice", "bob"}
            else None
        ),
    )
    app = FastAPI()
    app.add_middleware(WorkspaceActivityMiddleware)
    app.include_router(
        practice.router,
        prefix="/api/question-notebook/practice",
        dependencies=[Depends(auth.require_learning_surface)],
    )
    app.include_router(
        question_notebook.router,
        prefix="/api/question-notebook",
        dependencies=[Depends(auth.require_learning_surface)],
    )
    h = {"Authorization": "Bearer alice"}
    with TestClient(app) as client:
        row = client.post(
            "/api/question-notebook/entries/upsert",
            headers=h,
            json={
                "origin_type": "external_import",
                "origin_ref": "synthetic",
                "question_id": "one",
                "question": "Synthetic?",
                "source": "import",
                "result": "ungraded",
            },
        ).json()
        identity = row["id"]
        path = f"/api/question-notebook/practice/questions/{identity}"
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer bob"}).status_code == 404
        body = {
            "request_id": "guidance_update_001",
            "version": 0,
            "quality": "ready",
            "kind": "simulated",
        }
        assert (
            client.post(
                path + "/guidance", headers=h, json={**body, "account_id": "bob"}
            ).status_code
            == 422
        )
        assert client.post(path + "/guidance", headers=h, json=body).status_code == 200
        with as_user("alice"):
            from deeptutor.services.workspace import get_content_workspace_service

            workspace = get_content_workspace_service().create_workspace("Synthetic other")[
                "workspace_id"
            ]
        assert client.get(path, headers=h, params={"dt_workspace": workspace}).status_code == 404
        assert client.get(path, headers=h).json()["guidance"]["config"]["version"] == 1
