"""A project built from its own repository: created from a repo choice, built in the background, scoped to its own
checkout, and rebuilt (not refused) when it moves to another repository."""
from fastapi.testclient import TestClient

from warden import build, config, workspaces
from warden.actions import github


def _chosen(owner, repo, base):
    return {"full_name": f"{owner}/{repo}", "owner": owner, "name": repo, "fork": False, "default_branch": base, "push": True, "private": False}


def test_create_from_repo_queues_a_build_and_switching_repo_rebuilds(monkeypatch):
    from warden.api import app as api
    from tests.test_api import _signup

    started: list[str] = []
    monkeypatch.setattr(github, "validate_choice", _chosen)
    monkeypatch.setattr(build, "start", lambda pid: started.append(pid) or True)
    c = TestClient(api.app)
    me = _signup(c, "Repo Owner")
    team = next(o for o in me["orgs"] if o["personal"])

    made = c.post("/api/projects", json={"org_id": team["id"], "name": "", "owner": "me", "repo": "metaverse", "base": "master"})
    assert made.status_code == 200, made.text
    p = made.json()["project"]
    assert (p["name"], p["status"], p["repo_url"], p["ref"]) == ("metaverse", "queued", "https://github.com/me/metaverse", "master")
    assert (p["gh_owner"], p["gh_repo"], p["gh_base"]) == ("me", "metaverse", "master")
    assert started == [p["id"]]
    src = workspaces.source_for(p)
    assert src["dir"] == str(config.REPOS_DIR / p["id"]) and src["clone"] == "https://github.com/me/metaverse.git" and src["ref"] == "master"
    assert c.get(f"/api/projects/{p['id']}").json()["status"] == "queued"

    moved = c.put(f"/api/projects/{p['id']}/github", json={"owner": "me", "repo": "stories", "base": "main"})
    assert moved.status_code == 200, moved.text  # another codebase is a rebuild, not an error
    assert (moved.json()["repo_url"], moved.json()["status"]) == ("https://github.com/me/stories", "queued")
    assert started == [p["id"], p["id"]]

    assert c.post(f"/api/projects/{p['id']}/rebuild").status_code == 200
    assert len(started) == 3
    assert c.delete(f"/api/projects/{p['id']}").status_code == 200


def test_demo_project_is_named_after_the_fork_and_never_reads_its_own_checkout():
    from warden.db import init_db, session
    from warden.db.models import Project

    init_db()
    with session() as s:
        demo = workspaces.project_json(s.query(Project).filter(Project.slug == workspaces.DEMO_PROJECT_SLUG).one())
    assert demo["name"] == config.DEMO_PROJECT_NAME and "outique" not in demo["name"]
    assert workspaces.source_for(demo) is None and demo["demo"]
