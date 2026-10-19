"""Any repository becomes a graph: services from Kubernetes, compose or the code folders; dependencies from every
common lockfile; org data inferred when the curated files don't describe the repo."""
import json

from warden import config
from warden.ingest import deps, discover, orgdata
from warden.ingest.history import file_service


def _write(root, files: dict):
    for path, text in files.items():
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text if isinstance(text, str) else json.dumps(text), encoding="utf-8")


DEPLOY = """apiVersion: apps/v1
kind: Deployment
metadata: {{name: {name}}}
spec:
  template:
    spec:
      containers:
        - name: server
          image: example/{name}:1.0
          env: [{env}]
---
apiVersion: v1
kind: Service
metadata: {{name: {name}}}
spec: {{type: {type}, selector: {{app: {name}}}}}
"""


def test_kubernetes_services_ingress_calls_and_code_folders(tmp_path):
    _write(tmp_path, {
        "k8s/web.yaml": DEPLOY.format(name="web", type="ClusterIP", env="{name: API_URL, value: 'http://api:8080/v1'}"),
        "k8s/api.yaml": DEPLOY.format(name="api", type="ClusterIP", env="{name: DB_ADDR, value: 'db:5432'}"),
        "k8s/db.yaml": DEPLOY.format(name="db", type="ClusterIP", env=""),
        "k8s/ingress.yaml": "apiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata: {name: public}\nspec:\n  rules:\n"
                            "    - http: {paths: [{path: /, backend: {service: {name: web, port: {number: 80}}}}]}\n",
        "overlays/prod/web.yaml": DEPLOY.format(name="web", type="LoadBalancer", env=""),  # a variant: never wins
        "charts/app/templates/x.yaml": "kind: Deployment\nmetadata: {name: {{ .Values.name }}}\n",  # helm template: skipped
        "services/web/package.json": {"dependencies": {"express": "4.18.2"}},
        "services/api-service/go.mod": "module api\n\ngo 1.22\n",
    })
    m = discover.discover(tmp_path, "shop")
    assert m["source"] == "kubernetes"
    by = {s["name"]: s for s in m["services"]}
    assert set(by) == {"web", "api", "db"}
    assert by["web"]["tier"] == "public" and by["api"]["tier"] == "internal"
    assert by["web"]["path_prefix"] == "services/web/" and by["web"]["language"] == "node"
    assert by["api"]["path_prefix"] == "services/api-service/"  # matched by the name without its "-service" suffix
    assert by["db"]["path_prefix"] is None
    assert m["ingresses"] == [{"name": "public", "kind": "Ingress", "service": "web", "manifest": "k8s/ingress.yaml"}]
    assert {(c["src"], c["dst"], c["via"]) for c in m["calls"]} == {("web", "api", "http"), ("api", "db", "grpc")}


def test_compose_build_contexts_ports_and_depends_on(tmp_path):
    _write(tmp_path, {
        "docker-compose.yml": "services:\n  frontend:\n    build: ./client\n    ports: ['3000:3000']\n    depends_on: [backend]\n"
                              "  backend:\n    build: {context: ./server}\n    environment: ['MONGO_URL=mongodb://mongo:27017/app']\n"
                              "  mongo:\n    image: mongo:6\n",
        "client/package.json": {"dependencies": {"react": "18.2.0"}},
        "server/requirements.txt": "flask==2.0.0\n",
    })
    m = discover.discover(tmp_path, "app")
    assert m["source"] == "compose"
    by = {s["name"]: s for s in m["services"]}
    assert (by["frontend"]["path_prefix"], by["frontend"]["tier"]) == ("client/", "public")
    assert (by["backend"]["path_prefix"], by["backend"]["language"]) == ("server/", "python")
    assert by["mongo"]["path_prefix"] is None
    assert {(c["src"], c["dst"]) for c in m["calls"]} == {("frontend", "backend"), ("backend", "mongo")}


def test_code_only_repo_infers_internet_facing_services(tmp_path):
    _write(tmp_path, {
        "package.json": {"dependencies": {"lucide-react": "^0.509.0"}},  # a stray root manifest above the real apps
        "client/package.json": {"dependencies": {"react": "18.2.0"}, "devDependencies": {"vite": "5.0.0"}},
        "client/package-lock.json": {"lockfileVersion": 3, "packages": {"": {}}},
        "server/package.json": {"dependencies": {"express": "4.18.2"}},
        "server/package-lock.json": {"lockfileVersion": 3, "packages": {"": {}}},
        "worker/go.mod": "module w\n",
        "tests/e2e/package.json": {"dependencies": {"playwright": "1.0.0"}},
    })
    m = discover.discover(tmp_path, "metaverse")
    assert m["source"] == "code"
    by = {s["name"]: s for s in m["services"]}
    assert set(by) == {"client", "server", "worker"}
    assert {i["service"]: i["kind"] for i in m["ingresses"]} == {"client": "Inferred", "server": "Inferred"}
    assert by["worker"]["tier"] == "internal"


def test_single_app_repo_is_its_own_internet_facing_service(tmp_path):
    _write(tmp_path, {"package.json": {"dependencies": {"left-pad": "1.3.0"}}, "package-lock.json": {"lockfileVersion": 3, "packages": {}}})
    m = discover.discover(tmp_path, "stories")
    assert [(s["name"], s["tier"], s["path_prefix"]) for s in m["services"]] == [("stories", "public", "")]


def test_lockfile_parsers(tmp_path):
    _write(tmp_path, {
        "yarn/package.json": {"dependencies": {"lodash": "^4.17.0"}},
        "yarn/yarn.lock": '# yarn lockfile v1\n\n"lodash@^4.17.0", lodash@^4.17.20:\n  version "4.17.21"\n\n"@babel/core@^7.0.0":\n  version "7.22.0"\n',
        "pnpm/pnpm-lock.yaml": "lockfileVersion: '9.0'\nimporters:\n  .:\n    dependencies:\n      axios: {specifier: ^1.0.0, version: 1.6.0}\n"
                               "packages:\n  axios@1.6.0: {}\n  '@types/node@20.1.0': {}\n",
        "nolock/package.json": {"dependencies": {"express": "^4.17.1", "x": "latest", "y": ">=1"}},
        "poetry/pyproject.toml": '[tool.poetry.dependencies]\npython = "^3.11"\nDjango = "^4.2"\n',
        "poetry/poetry.lock": '[[package]]\nname = "django"\nversion = "4.2.1"\n\n[[package]]\nname = "sqlparse"\nversion = "0.4.4"\n',
        "maven/pom.xml": '<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><log4j.version>2.14.1</log4j.version></properties>'
                         "<dependencies><dependency><groupId>org.apache.logging.log4j</groupId><artifactId>log4j-core</artifactId>"
                         "<version>${log4j.version}</version></dependency><dependency><groupId>junit</groupId><artifactId>junit</artifactId>"
                         "<version>4.13</version><scope>test</scope></dependency></dependencies></project>",
        "rust/Cargo.toml": '[dependencies]\nserde = "1"\n',
        "rust/Cargo.lock": '[[package]]\nname = "app"\nversion = "0.1.0"\n\n[[package]]\nname = "serde"\nversion = "1.0.190"\n'
                           'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
        "ruby/Gemfile.lock": "GEM\n  remote: https://rubygems.org/\n  specs:\n    rack (2.2.3)\n      x (>= 1)\n    nokogiri (1.13.0-x86_64-linux)\n\n"
                             "PLATFORMS\n  ruby\n\nDEPENDENCIES\n  rack\n",
        "php/composer.json": {"require": {"guzzlehttp/guzzle": "^7.0"}},
        "php/composer.lock": {"packages": [{"name": "guzzlehttp/guzzle", "version": "v7.4.0"}]},
    })
    services = [{"name": n, "path_prefix": f"{n}/"} for n in ("yarn", "pnpm", "nolock", "poetry", "maven", "rust", "ruby", "php")]
    tok = config.CURRENT_SOURCE.set({"dir": str(tmp_path)})
    try:
        out = deps.parse_dependencies(services)
    finally:
        config.CURRENT_SOURCE.reset(tok)
    got = {(d["service"], d["key"]): d["direct"] for d in out["depends"]}
    assert got[("yarn", "npm:lodash@4.17.21")] and not got[("yarn", "npm:@babel/core@7.22.0")]
    assert got[("pnpm", "npm:axios@1.6.0")] and not got[("pnpm", "npm:@types/node@20.1.0")]
    assert [k for s, k in got if s == "nolock"] == ["npm:express@4.17.1"]  # unpinnable ranges are left out
    assert got[("poetry", "PyPI:django@4.2.1")] and not got[("poetry", "PyPI:sqlparse@0.4.4")]
    assert [k for s, k in got if s == "maven"] == ["Maven:org.apache.logging.log4j:log4j-core@2.14.1"]  # property resolved, test scope skipped
    assert [k for s, k in got if s == "rust"] == ["crates.io:serde@1.0.190"]  # the repo's own crate is not a dependency
    assert got[("ruby", "RubyGems:rack@2.2.3")] and not got[("ruby", "RubyGems:nokogiri@1.13.0")]
    assert got[("php", "Packagist:guzzlehttp/guzzle@7.4.0")]


def test_inferred_data_and_codeowners(tmp_path):
    d = {"packages": [{"key": "npm:stripe@1", "name": "stripe"}, {"key": "npm:mongoose@7", "name": "mongoose"},
                      {"key": "Go:github.com/golang-jwt/jwt/v4@v4.5.0", "name": "github.com/golang-jwt/jwt/v4"}],
         "depends": [{"service": "api", "key": "npm:stripe@1", "direct": True}, {"service": "api", "key": "npm:mongoose@7", "direct": False},
                     {"service": "auth", "key": "Go:github.com/golang-jwt/jwt/v4@v4.5.0", "direct": True}]}
    assets = {a["name"]: a["reads"] for a in orgdata.infer_assets(d)}
    assert assets == {"CardData": [{"service": "api", "evidence": "stripe"}],
                      "Credentials": [{"service": "auth", "evidence": "github.com/golang-jwt/jwt/v4"}]}  # transitive mongoose doesn't count
    _write(tmp_path, {".github/CODEOWNERS": "* @acme/platform\n/services/api/ @acme/payments @alice\n"})
    teams = {t["slug"]: t for t in orgdata.codeowners_teams([{"name": "api", "path_prefix": "services/api/"}, {"name": "web", "path_prefix": "web/"}], tmp_path)}
    assert teams["acme/payments"]["owns"] == ["api"] and teams["acme/platform"]["owns"] == ["web"]
    assert teams["alice"]["reviewers"] == ["alice"]


def test_curated_org_data_only_for_microservices_demo():
    assert orgdata.curated_applies([{"name": n} for n in ("frontend", "cartservice", "checkoutservice", "paymentservice", "emailservice",
                                                          "currencyservice", "adservice")])
    assert not orgdata.curated_applies([{"name": "client"}, {"name": "server"}])


def test_file_service_uses_service_folders():
    prefixes = {"api": "services/api/", "root": "", "db": None}
    assert file_service("services/api/main.go", {"api", "root", "db"}, prefixes) == "api"  # the deepest folder wins
    assert file_service("README.md", {"api", "root", "db"}, prefixes) == "root"
