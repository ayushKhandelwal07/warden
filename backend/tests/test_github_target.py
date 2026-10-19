"""A project chooses the GitHub repo it acts on; everything reads it through config.gh_*(), falling back to .env."""
import pytest
from fastapi.testclient import TestClient

from warden import config
from warden.actions import github
from warden.db import init_db, session
from warden.db.models import Membership, Project


def test_accessors_fall_back_to_env_then_follow_the_project(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_OWNER", "envowner")
    monkeypatch.setattr(config, "GITHUB_REPO", "envrepo")
    monkeypatch.setattr(config, "GITHUB_BASE", "envbase")
    assert (config.gh_owner(), config.gh_repo(), config.gh_base()) == ("envowner", "envrepo", "envbase")
    tok = config.CURRENT_GITHUB.set({"owner": "me", "repo": "fork", "base": "main"})
    try:
        assert (config.gh_owner(), config.gh_repo(), config.gh_base()) == ("me", "fork", "main")
        monkeypatch.setattr(config, "GITHUB_TOKEN", "x")
        assert github.target() == "me/fork"
    finally:
        config.CURRENT_GITHUB.reset(tok)
    assert config.gh_owner() == "envowner"


def test_target_still_refuses_upstream(monkeypatch):
    monkeypatch.setattr(config, "GITHUB_TOKEN", "x")
    tok = config.CURRENT_GITHUB.set({"owner": "GoogleCloudPlatform", "repo": "microservices-demo", "base": "main"})
    try:
        with pytest.raises(PermissionError):
            github.target()
    finally:
        config.CURRENT_GITHUB.reset(tok)


REPOS = [
    {"full_name": "me/fork", "owner": "me", "name": "fork", "fork": True, "default_branch": "main", "push": True, "private": False},
    {"full_name": "me/readonly", "owner": "me", "name": "readonly", "fork": False, "default_branch": "main", "push": False, "private": False},
]


def _client():
    from warden.api import app as api
    from tests.test_api import _signup

    c = TestClient(api.app)
    me = _signup(c)
    return c, me


def test_repo_list_only_offers_repos_with_push_access(monkeypatch):
    monkeypatch.setattr(github, "list_repos", lambda: REPOS)
    c, _ = _client()
    assert [r["full_name"] for r in c.get("/api/github/repos").json()] == ["me/fork"]


def test_choosing_a_repo_is_validated_and_limited_to_admins(monkeypatch):
    init_db()
    monkeypatch.setattr(github, "list_repos", lambda: REPOS)
    monkeypatch.setattr(github, "list_branches", lambda o, r: ["main", "demo-base"])
    monkeypatch.setattr(github, "missing_paths", lambda o, r, ref, paths: [] if r == "fork" else paths)
    c, me = _client()
    with session() as s:
        proj = s.query(Project).filter(Project.slug == "microservices-demo").one()
        pid, saved = proj.id, (proj.gh_owner, proj.gh_repo, proj.gh_base, proj.repo_url)
    url = f"/api/projects/{pid}/github"
    assert c.put(url, json={"owner": "me"}).status_code == 400                                         # incomplete
    assert c.put(url, json={"owner": "me", "repo": "readonly", "base": "main"}).status_code == 400       # no push access
    assert c.put(url, json={"owner": "me", "repo": "fork", "base": "nope"}).status_code == 400           # no such branch
    assert c.put(url, json={"owner": "me", "repo": "fork", "base": "main"}).status_code == 403           # a plain member
    REPOS.append({"full_name": "me/other", "owner": "me", "name": "other", "fork": False, "default_branch": "main", "push": True, "private": False})
    try:
        bad = c.put(url, json={"owner": "me", "repo": "other", "base": "main"})
        assert bad.status_code == 400 and "does not contain the code" in bad.json()["error"]   # a repo the graph does not describe
    finally:
        REPOS.pop()
    with session() as s:  # make this user an admin of the team for the rest of the test
        m = s.query(Membership).filter(Membership.user_id == me["user"]["id"], Membership.org_id == "demo").one()
        m.role = "admin"
    try:
        out = c.put(url, json={"owner": "me", "repo": "fork", "base": "demo-base"}).json()
        assert (out["gh_owner"], out["gh_repo"], out["gh_base"]) == ("me", "fork", "demo-base")
        assert c.get("/api/github").json()["target"] == "me/fork"   # requests for this project now act on it
    finally:
        with session() as s:
            p = s.get(Project, pid)
            p.gh_owner, p.gh_repo, p.gh_base, p.repo_url = saved
        from warden import watch
        from warden.graph.client import rw

        rw("MATCH (e:WatchEvent) WHERE e.kind = 'watch' DELETE e", graph_name=watch._g())
