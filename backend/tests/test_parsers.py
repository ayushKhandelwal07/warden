import json

from warden.ingest import deps
from warden.ingest.common import version_key
from warden.ingest.history import _person, file_service


def test_npm_lock_resolves_nested_and_direct(tmp_path):
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"dependencies": {"a": "^1.0.0"}},
            "node_modules/a": {"version": "1.0.0", "dependencies": {"b": "^2"}},
            "node_modules/a/node_modules/b": {"version": "2.0.0"},
            "node_modules/b": {"version": "1.0.0"},
            "node_modules/devonly": {"version": "9.9.9", "dev": True},
        },
    }
    p = tmp_path / "package-lock.json"
    p.write_text(json.dumps(lock))
    ds = deps.DepSet()
    deps._npm(ds, "svc", p, "src/svc/package-lock.json")
    out = ds.to_dict()
    assert {"src": "npm:a@1.0.0", "dst": "npm:b@2.0.0"} in out["requires"]  # nested copy wins over hoisted
    direct = {d["key"]: d["direct"] for d in out["depends"]}
    assert direct == {"npm:a@1.0.0": True, "npm:b@2.0.0": False, "npm:b@1.0.0": False}


def test_pip_compile_via_builds_chain(tmp_path):
    p = tmp_path / "requirements.txt"
    p.write_text(
        "grpcio==1.54.2\n    # via\n    #   -r requirements.in\n    #   google-api-core\n"
        "google-api-core[grpc]==2.11.0\n    # via -r requirements.in\n"
        "protobuf==4.23.2\n    # via google-api-core\n"
    )
    ds = deps.DepSet()
    deps._pypi(ds, "svc", p, "src/svc/requirements.txt")
    out = ds.to_dict()
    assert {"src": "PyPI:google-api-core@2.11.0", "dst": "PyPI:protobuf@4.23.2"} in out["requires"]
    direct = {d["key"]: d["direct"] for d in out["depends"]}
    assert direct["PyPI:grpcio@1.54.2"] and not direct["PyPI:protobuf@4.23.2"]


def test_go_mod_indirect_and_stdlib(tmp_path):
    (tmp_path / "go.mod").write_text(
        "module x\n\ngo 1.19\n\nrequire (\n\tgolang.org/x/net v0.10.0\n)\n\nrequire (\n\tgithub.com/a/b v1.0.0 // indirect\n)\n"
    )
    (tmp_path / "Dockerfile").write_text("FROM golang:1.20.4-alpine@sha256:abc AS builder\n")
    ds = deps.DepSet()
    deps._go(ds, "svc", tmp_path / "go.mod", "src/svc/go.mod")
    direct = {d["key"]: d["direct"] for d in ds.to_dict()["depends"]}
    assert direct == {"Go:golang.org/x/net@v0.10.0": True, "Go:github.com/a/b@v1.0.0": False, "Go:stdlib@1.20.4": True}


def test_version_key_orders_semver_and_prerelease():
    assert version_key("v0.10.0") < version_key("0.17.0")
    assert version_key("1.2.3-rc1") < version_key("1.2.3")
    assert version_key("2.0.61.Final") > version_key("2.0.6")


def test_person_never_keeps_email():
    p = _person("Jane Doe", "123+janed@users.noreply.github.com")
    assert p == {"key": "janed", "name": "Jane Doe", "login": "janed", "is_bot": False}
    assert "email" not in _person("Bot", "bot@example.com")
    assert _person("renovate[bot]", "x@y")["is_bot"]


def test_file_service_mapping():
    svcs = {"frontend", "cartservice"}
    assert file_service("src/frontend/main.go", svcs) == "frontend"
    assert file_service("kubernetes-manifests/cartservice.yaml", svcs) == "cartservice"
    assert file_service("README.md", svcs) is None
