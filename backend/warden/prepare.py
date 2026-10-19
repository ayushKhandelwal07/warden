"""Put everything back to the clean, pinned state before a demo or a recording. One command, no clicking:

    python -m warden.prepare

  1. the watcher is switched off
  2. the fork's demo change is undone (paymentservice made internal again), only if GitHub is configured
  3. the graph is restored from the pinned snapshot; approvals and watcher state are cleared
  4. the evaluation is run once so the Evaluation page has a result

Chats and users are never touched. Writes to GitHub are limited to reverting the one-line change the watcher demo makes on your own fork.
"""
import sys

from warden import config


def run() -> list[dict]:
    steps: list[dict] = []

    def step(name: str, fn):
        try:
            steps.append({"step": name, "ok": True, "detail": fn()})
        except Exception as e:  # keep going: a failed step is reported, not hidden
            steps.append({"step": name, "ok": False, "detail": f"{type(e).__name__}: {str(e)[:160]}"})

    from warden import sync, watch
    from warden.actions import github

    step("watcher off", lambda: ("off" if not watch.set_enabled(False)["enabled"] else "still on"))
    if github.configured():
        def undo():
            r = watch.set_exposure("paymentservice", False)
            return "fork restored (paymentservice internal again)" if r.get("changed") else "fork already clean"
        step("undo the fork's demo change", undo)
    else:
        steps.append({"step": "undo the fork's demo change", "ok": True, "detail": "skipped: GitHub is not configured"})

    step("restore the pinned graph", lambda: f"graph at {sync.reset().get('ref')}")

    def evaluate():
        from warden import eval as ev

        m = ev.run()["metrics"]["overall"]
        return f"{m['warden']} of {m['n']} designed scenarios match"
    step("run the evaluation", evaluate)

    def check():
        from warden.graph import overview

        f = {s["key"]: s["n"] for s in overview.funnel()["stages"]}
        return f"{f['present']} advisories, {f['reachable']} reachable, {f['signal']} with an exploit signal, {f['kev']} on KEV"
    step("check the numbers", check)
    return steps


if __name__ == "__main__":
    out = run()
    for s in out:
        print(("ok   " if s["ok"] else "FAIL ") + f"{s['step']}: {s['detail']}")
    sys.exit(0 if all(s["ok"] for s in out) else 1)
