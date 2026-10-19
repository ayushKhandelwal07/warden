# Warden: demo script (say these words)

Numbers below are for the **pinned release** (v0.8.0). If a number on screen differs, say the number on screen. Never say "exploited here": say "known exploited" (KEV) or "graph-reachable".

## Before you record (10 minutes)

1. Run one command from the repo root: `cd backend && .venv/Scripts/python -m warden.prepare` (or `.\start.ps1 -Reset`). It switches the watcher off, reverts the fork's demo change, restores the pinned graph, clears approvals and runs the evaluation. Check Home reads **256 alerts. 1 attack path that matters.**
2. Approvals are now empty (honest: nothing has happened yet). Delete old chats you do not want in the sidebar; chats are never touched by the command.
4. `.env`: `LLM_API_KEY`, `GITHUB_*` set. Run `GET /api/health`; run Evaluation once so it has a result.
5. Browser at 1440 px wide, zoom 100%, bookmarks bar hidden, one tab. Rehearse the full flow twice before recording. Keep the Ask answers short: if a reply is slow, cut the pause in the edit.
6. Do **not** merge real PRs on camera unless you have rehearsed it; show the PRs and the verification timeline instead.

---

## The 3-minute video (master script)

| Time | Screen | Say |
|---|---|---|
| 0:00 | Landing page | "A scanner gives you two hundred and fifty-six alerts and sorts them by severity. It cannot tell you which one an attacker can actually reach, or whether your fix really removes the path. This is Warden." |
| 0:15 | Click **Open Warden**, Home | "Warden turns a repository and public vulnerability data into one FalkorDB graph: services, calls, packages, advisories, exploit signals, the data each service reads, and the team's history." |
| 0:30 | Attack-surface map | "These are the twelve services of Google's Online Boutique, placed by hops from the internet. Size is risk. Orange services carry a CISA KEV exposure, and the thick line is the route an attacker takes to get there." |
| 0:45 | Scroll to the KEV card, **Validate in graph** | "This is the one that matters: CVE-2023-44487 in golang.org/x/net, on CISA's known-exploited list. Every hop is a real edge with its source: the load balancer, the service, the go.mod line, the advisory. Validate re-queries the graph and confirms every hop still exists." |
| 1:05 | Open **Show query** | "And here is the Cypher. FalkorDB is not decoration: remove it and none of this can be answered." |
| 1:15 | Graph vs severity card | "The same six hundred and eighty-one exposures ranked two ways. By severity alone, the four KEV exposures sit around rank one ninety-five. By graph risk they are the top few. That is reachability, exploit evidence and the data they can reach, not a bigger CVSS number." |
| 1:35 | **Ask**, click "What should we fix first?" | "Now I ask in plain language. The agent only answers from graph tools, and it shows the path behind the answer." (wait for the answer) "It names the finding, the path and the tools it used, and the verifier checks every service and CVE it mentions." |
| 2:00 | Home → **Build a fix plan** → Approvals | "Warden builds the smallest set of upgrades that removes the most risk, then rehearses them on a copy of the graph, with the new versions' advisories loaded. The gate is deterministic code, not the model: risk must drop, KEV must go, and nothing new may appear." |
| 2:20 | Gate, before/after, regression | "Here is the gate, the before and after path, and the regression: the same paths re-queried after the fix. The KEV path is dashed, removed. Nothing new is opened." |
| 2:35 | Click **Approve** | "Nothing external happens until a human approves. Approving opens one pull request per service on our fork, with a link back to this page." |
| 2:45 | Verification timeline | "After the merge the graph is re-read and the exposures the plan promised to remove are checked. Verified, or not." |
| 2:52 | **Evaluation** | "And these are measured, not claimed: thirteen designed scenarios, all matching, next to a severity-only baseline. They are designed tests on controlled graphs, not an independent benchmark." |
| 3:00 | Logo | "Warden. Know what attackers can really reach, and prove the fix." |

---

## Feature scripts (use for a longer video, a blog, or live Q&A)

### 1. Landing page
**Do:** scroll slowly top to bottom.
**Say:** "Warden answers one question: which vulnerabilities can attackers really reach? The numbers on this page come live from the graph: two hundred and fifty-six advisories present, two hundred and thirty-nine graph-reachable, three with an exploit signal, one on CISA's known-exploited list. Those are overlapping filters over the same advisories, not buckets."

### 2. Home: the headline and the funnel
**Do:** point at the headline, then open **Where the numbers come from**, expand one row, click **Show query**.
**Say:** "Two hundred and fifty-six alerts, one attack path that matters. Every number here is the result of a Cypher query, and I can open it. The units matter: advisories are unique CVEs; exposures are an advisory in a service, six hundred and eighty-one of them. 'Reachable' means graph-reachable under our topology model, not proven exploitable."

### 3. Attack-surface map and the secure toggle
**Do:** click `checkoutservice`, press **Secure checkoutservice**, then click `cartservice` and press the button again.
**Say:** "Click any service and the button changes to secure that service. Securing checkoutservice cuts six of the seven routes from the internet to card and personal data. Shipping address is still reachable by another route, and the map shows exactly which. Securing cartservice changes nothing there, and it says so."

### 4. Evidence path and provenance
**Do:** on the KEV card, hover the path, point at the sourced and inferred badges, press **Validate in graph**.
**Say:** "Each hop says where it comes from. 'Sourced' is read from a manifest, a lockfile or an advisory. 'Inferred' is derived from configuration, for example a service address in an environment variable, and no traffic was observed. Validate re-runs the path read-only and confirms every hop still exists."

### 5. Graph versus severity
**Do:** open the card, switch **Severity only** to **KEV first**, press **Show the full top 10**.
**Say:** "This is the fair comparison: the same exposures, the same snapshot. Severity only buries the known-exploited ones. A KEV-first scanner finds that advisory but misses the exploit-likelihood signal on another one and fills the rest with high-CVSS findings two hops behind the front door. Neither ranking is tuned to the other."

### 6. Ask (the agent)
**Do:** ask "Which service should we secure first to protect card data?".
**Say:** "The answer is one line, then the evidence: checkoutservice sits on six of the seven internet-to-card-data paths. Under the answer the graph work shows how many queries ran and how long they took. 'Verified' means a deterministic check found every service and CVE in a tool result, not that the model sounded sure."

### 7. Ask about the repo and people
**Do:** ask "Who am I and what is my role on this repository? Who else maintains it?".
**Say:** "The agent also has tools for the live fork on GitHub and for any person, so it can answer who maintains the repository and what is open right now, with the real data, not guesses."

### 8. Choke points
**Do:** on Home, point at the **Secure checkoutservice first** card.
**Say:** "Choke points are counted by enumerating every route from the internet to card and personal data and seeing which service most of them pass through. Exact betweenness from FalkorDB's all-pairs shortest paths is shown next to it as a cross-check."

### 9. What-if
**Do:** Sync page, What if: "expose paymentservice" is pre-filled; press **Rehearse**.
**Say:** "What if paymentservice became public? Warden copies the graph, applies the change on the copy and shows the new path to card data in red, the change in risk, and the single best counter-move. Nothing in the live graph changes, and the copy is deleted."

### 10. Compare fix plans
**Do:** Home → **Compare fix plans** → **Compare**.
**Say:** "Four strategies, each rehearsed on its own copy of the graph: fewest changes, safest, balanced, most risk removed. The table shows risk removed, changes, major version bumps, new advisories, KEV left and the gate verdict. If I forbid major bumps, the honest answer is that no plan can close the KEV exposure, and the gate says so."

### 11. Fix plan, gate and regression
**Do:** **Build a fix plan** → Approvals → open it.
**Say:** "One upgrade of golang.org/x/net clears dozens of exposures across four services. The gate runs deterministic checks: risk drops, KEV is eliminated, nothing new that is critical, nothing new that touches card or personal data. Then the regression: the invariant paths recorded before, re-queried after."

### 12. Unsafe plan
**Do:** Home → **Try a deliberately unsafe plan**.
**Say:** "Here I pin golang.org/x/net back to an old version. Warden rehearses it for real, and the gate blocks it: the KEV exposure is not removed. The language model cannot talk its way past this check, because it is code."

### 13. Approval, pull requests and verification
**Do:** press **Approve**, show the PR links, open the timeline.
**Say:** "Approving opens one pull request per service on the fork only; the code refuses to touch the upstream repository. The comment links back here. The timeline runs from proposed to approved to pull requests, checks, merged, graph re-read, and exposures gone. The final step is measured, not assumed."

### 14. Decision memory
**Do:** reject a plan with the reason "A gRPC bump broke checkout", build a new plan.
**Say:** "The rejection is a node in the graph. The next plan drops that upgrade and says why: who rejected it, when, and the reason. If the situation changes, the decision expires and the plan is re-gated."

### 15. Contradictions
**Do:** Home → **Evidence contradictions** → **Re-check sources**.
**Say:** "Warden checks whether its own sources disagree: go.mod against the Dockerfile, package.json against the lockfile, a public label against the manifest. If one touches a fix, the plan is blocked instead of guessed. Today it checked three hundred forty-two facts and found none."

### 16. Watcher
**Do:** Home → **Watcher** → switch on → **Make paymentservice public** → **Check now**.
**Say:** "The watcher notices a change on the fork by itself. I make paymentservice public with one commit. It re-reads the graph, finds a new exposure, and files an issue for the owning team and a rehearsed fix plan, both waiting for approval. Undo puts the fork back."

### 17. Timeline and replay
**Do:** Sync → **Exposure timeline**, then Ask → **Replay this investigation**.
**Say:** "The graph shows today; the timeline shows how it got here. And any answer can be replayed: Warden re-runs its tool calls against the current graph and tells me per call whether the rows are the same or changed."

### 18. Tools and MCP
**Do:** Tools page → open `choke_points` → **Run**; point at **Without the graph**.
**Say:** "These twenty tools are the whole interface: read-only queries over FalkorDB. The agent calls them over MCP, and so can any MCP client. Each tool says what you could not answer without the graph."

### 19. PR impact
**Do:** PR impact → analyse one PR from merged history.
**Say:** "For a pull request Warden answers what it touches, what breaks three hops away, who has changed this code before, and which past incident looks similar. Merged history is a report only; an open PR on the fork can also get a comment, after approval."

### 20. Evaluation
**Do:** Evaluation → **Run again**, open two scenarios.
**Say:** "Thirteen designed scenarios on throwaway graphs, built in the real schema and run through the real tools and gate. Warden matches all thirteen; the severity-only baseline can only attempt some, and where it cannot take part, the page says 'not supported'. This shows the code behaves as designed. It is not an independent benchmark."

### 21. Closing line (any length)
**Say:** "Every claim has a path, every fix is rehearsed, and a human decides. That is Warden."

---

## Questions you will be asked (short answers)

- **Does a graph path mean it is exploitable?** "No. It means an attacker can reach the vulnerable component under our topology model. We say 'graph-reachable', and KEV means exploitation was reported somewhere, not here."
- **Where is FalkorDB essential?** "Reachability, ranking, rehearsal on `GRAPH.COPY`, choke points with `algo.SPpaths`, memory, history. Without it, none of the answers exist."
- **What is synthetic?** "Teams, ownership, which data each service reads, the policies and four incident post-mortems. Dependencies, advisories, KEV, EPSS and git history are real."
- **What can it not do?** "No function-level analysis, `CALLS` are inferred from configuration, and lockfiles are regenerated by CI, not by Warden."
- **Is the AI allowed to change anything?** "No. It reads through tools. Every write is a pending approval a human must click, and only on the fork."
