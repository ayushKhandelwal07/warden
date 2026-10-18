import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { Check, Copy, Database, Link2, Plus, Trash2, UserMinus } from "lucide-react";
import { api, type Member, type Org } from "../lib/api";
import { useAuth, useProject } from "../lib/auth";
import { Button } from "../components/ui";

const SECTIONS = [
  { key: "team", label: "Team" },
  { key: "projects", label: "Projects" },
  { key: "profile", label: "Profile" },
];

function Panel({ title, sub, children, actions }: { title: string; sub?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-card border border-line">
      <header className="flex flex-wrap items-start gap-3 border-b border-line px-5 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-small font-semibold">{title}</h2>
          {sub && <p className="mt-0.5 text-[12.5px] text-muted">{sub}</p>}
        </div>
        {actions}
      </header>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`h-11 min-w-0 rounded-full border border-line bg-bg px-4 text-small outline-none focus:border-ink ${props.className ?? ""}`} />;
}

const canAdmin = (o?: Org) => o?.role === "owner" || o?.role === "admin";

function InviteLink({ org }: { org: Org }) {
  const [link, setLink] = useState<string | null>(null);
  const [role, setRole] = useState("member");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const make = async () => {
    setError(null);
    try {
      const inv = await api.createInvite(org.id, role);
      setLink(`${window.location.origin}/invite/${inv.token}`);
      setCopied(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1 rounded-full border border-line p-1">
          {["member", "admin"].map((r) => (
            <button key={r} onClick={() => setRole(r)} className={`h-8 rounded-full px-3 text-[12px] font-medium ${role === r ? "bg-ink text-white" : "text-muted hover:text-ink"}`}>
              {r}
            </button>
          ))}
        </div>
        <Button icon={<Link2 size={15} />} onClick={make}>
          {link ? "New link" : "Create invite link"}
        </Button>
      </div>
      {link && (
        <div className="flex items-center gap-2 rounded-full border border-line p-1 pl-4">
          <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{link}</span>
          <button
            onClick={() => navigator.clipboard?.writeText(link).then(() => setCopied(true))}
            className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-ink px-3.5 text-[12.5px] font-medium text-white hover:opacity-85"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
      )}
      <p className="text-[12px] text-muted">Anyone with the link can join once, within 7 days. No email is sent: share it yourself.</p>
      {error && <p className="text-small text-accent">{error}</p>}
    </div>
  );
}

function Team() {
  const { me, setMe } = useAuth();
  const [orgId, setOrgId] = useState(me?.orgs[0]?.id ?? "");
  const org = me?.orgs.find((o) => o.id === orgId);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newTeam, setNewTeam] = useState("");

  const load = useCallback(() => {
    if (!orgId) return;
    api.members(orgId).then(setMembers, (e: Error) => setError(e.message));
  }, [orgId]);
  useEffect(load, [load]);

  const act = async (p: Promise<unknown>) => {
    setError(null);
    try {
      await p;
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!newTeam.trim()) return;
    const m = await api.createOrg(newTeam.trim());
    setMe(m);
    setNewTeam("");
    setOrgId(m.orgs[m.orgs.length - 1].id);
  };

  if (!me) return null;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap gap-2">
        {me.orgs.map((o) => (
          <button
            key={o.id}
            onClick={() => setOrgId(o.id)}
            className={`inline-flex h-9 items-center gap-2 rounded-full border px-3.5 text-[12.5px] font-medium ${o.id === orgId ? "border-ink" : "border-line text-muted hover:text-ink"}`}
          >
            {o.name}
            <span className="text-[11px] font-normal text-muted">{o.role}</span>
          </button>
        ))}
      </div>

      {org && (
        <Panel title={`${org.name} · members`} sub={org.personal ? "Your own team. Invite people to share projects and chats with them." : undefined}>
          {members === null ? (
            <p className="text-small text-muted">Loading…</p>
          ) : (
            <ul className="divide-y divide-line">
              {members.map((m) => (
                <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-line text-[12px] font-semibold">{m.name[0]?.toUpperCase()}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-small font-medium">
                      {m.name}
                      {m.user_id === me.user.id && <span className="font-normal text-muted"> (you)</span>}
                    </span>
                    <span className="block truncate text-[12px] text-muted">{m.email}</span>
                  </span>
                  {canAdmin(org) && m.role !== "owner" && m.user_id !== me.user.id ? (
                    <>
                      <select
                        value={m.role}
                        onChange={(e) => act(api.setRole(org.id, m.user_id, e.target.value))}
                        className="h-9 rounded-full border border-line bg-bg px-3 text-[12.5px]"
                        aria-label={`Role for ${m.name}`}
                      >
                        <option value="member">member</option>
                        <option value="admin">admin</option>
                      </select>
                      <button onClick={() => act(api.removeMember(org.id, m.user_id))} className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-code hover:text-ink" aria-label={`Remove ${m.name}`}>
                        <UserMinus size={15} />
                      </button>
                    </>
                  ) : (
                    <span className="text-[12.5px] text-muted">{m.role}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {error && <p className="mt-2 text-small text-accent">{error}</p>}
        </Panel>
      )}

      {org && canAdmin(org) && (
        <Panel title="Invite people" sub="They join this team and can ask every project in it.">
          <InviteLink key={org.id} org={org} />
        </Panel>
      )}

      <Panel title="New team">
        <form onSubmit={create} className="flex flex-wrap gap-2">
          <Input value={newTeam} onChange={(e) => setNewTeam(e.target.value)} placeholder="Platform security" className="flex-1" aria-label="Team name" />
          <Button icon={<Plus size={15} />} disabled={!newTeam.trim()}>
            Create team
          </Button>
        </form>
      </Panel>
    </div>
  );
}

function Projects() {
  const { me, setMe } = useAuth();
  const { slug } = useProject();
  const nav = useNavigate();
  const admins = (me?.orgs ?? []).filter(canAdmin);
  const [orgId, setOrgId] = useState(admins[0]?.id ?? "");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<string | null>(null);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const m = await api.createProject(orgId, name);
      setMe(m);
      setName("");
      nav(`/app/${m.project.slug}/home`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string, pslug: string) => {
    if (confirm !== id) return setConfirm(id);
    setError(null);
    try {
      const m = await api.deleteProject(id);
      setMe(m);
      if (pslug === slug) nav(`/app/${m.projects[0]?.slug}/settings/projects`);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  if (!me) return null;
  return (
    <div className="flex flex-col gap-6">
      <Panel title="Your projects" sub="Each project is its own FalkorDB graph. Everyone in the project's team asks the same graph.">
        <ul className="divide-y divide-line">
          {me.projects.map((p) => {
            const org = me.orgs.find((o) => o.id === p.org_id);
            return (
              <li key={p.id} className="flex flex-wrap items-center gap-3 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-ink text-[12px] font-semibold text-white">{p.name[0]}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-small font-medium">
                    {p.name} {p.slug === slug && <span className="font-normal text-muted">(open)</span>}
                  </span>
                  <span className="flex flex-wrap items-center gap-x-3 text-[12px] text-muted">
                    <span>{p.org_name}</span>
                    <span className="inline-flex items-center gap-1 font-mono">
                      <Database size={11} /> {p.graph}
                    </span>
                    {p.ref && <span className="font-mono">{p.ref}</span>}
                  </span>
                </span>
                {p.slug !== slug && (
                  <button onClick={() => nav(`/app/${p.slug}/home`)} className="inline-flex h-9 items-center rounded-full border border-line px-3.5 text-[12.5px] font-medium hover:border-ink">
                    Open
                  </button>
                )}
                {canAdmin(org) && p.slug !== "online-boutique" && (
                  <button
                    onClick={() => remove(p.id, p.slug)}
                    className={`inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[12.5px] ${confirm === p.id ? "border border-accent font-medium text-accent" : "text-muted hover:bg-code hover:text-ink"}`}
                    aria-label={`Delete ${p.name}`}
                  >
                    <Trash2 size={14} /> {confirm === p.id && "Delete graph and chats"}
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel title="New project" sub="Starts from the Google Microservices sample: a private copy of its graph that your team can sync, fix and decide on.">
        {admins.length ? (
          <form onSubmit={create} className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Checkout hardening" className="flex-1" aria-label="Project name" required />
              <select value={orgId} onChange={(e) => setOrgId(e.target.value)} className="h-11 rounded-full border border-line bg-bg px-4 text-small" aria-label="Team">
                {admins.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
              <Button variant="primary" icon={<Plus size={15} />} disabled={busy || !name.trim()}>
                {busy ? "Copying the graph…" : "Create project"}
              </Button>
            </div>
            <p className="text-[12px] text-muted">
              Source: {me.projects[0]?.repo_url?.replace("https://github.com/", "") ?? "Online Boutique"} at {me.projects[0]?.ref ?? "v0.8.0"}. Importing other repositories with the
              same layout (Kubernetes manifests + one folder per service) is next on the roadmap.
            </p>
          </form>
        ) : (
          <p className="text-small text-muted">You need to be an owner or admin of a team to create projects in it.</p>
        )}
        {error && <p className="mt-2 text-small text-accent">{error}</p>}
      </Panel>
    </div>
  );
}

function Profile() {
  const { me, setMe, logout } = useAuth();
  const nav = useNavigate();
  const [name, setName] = useState(me?.user.name ?? "");
  const [saved, setSaved] = useState(false);
  if (!me) return null;
  return (
    <div className="flex flex-col gap-6">
      <Panel title="Profile">
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setMe(await api.updateMe(name));
            setSaved(true);
          }}
          className="flex flex-col gap-3"
        >
          <label className="flex flex-col gap-1.5">
            <span className="text-small font-medium">Name</span>
            <div className="flex flex-wrap gap-2">
              <Input value={name} onChange={(e) => (setName(e.target.value), setSaved(false))} className="flex-1" />
              <Button icon={saved ? <Check size={15} /> : undefined} disabled={!name.trim() || name === me.user.name}>
                {saved ? "Saved" : "Save"}
              </Button>
            </div>
          </label>
          <p className="text-small text-muted">Email: {me.user.email}</p>
        </form>
      </Panel>
      <div>
        <Button
          onClick={async () => {
            await logout();
            nav("/login", { replace: true });
          }}
        >
          Log out
        </Button>
      </div>
    </div>
  );
}

export function Settings() {
  const { section = "team" } = useParams();
  const { to } = useProject();
  return (
    <div className="mx-auto max-w-[900px] px-4 pb-24 pt-8 sm:px-6">
      <h1 className="text-h1 font-semibold">Settings</h1>
      <nav className="mt-6 flex gap-1 border-b border-line" aria-label="Settings">
        {SECTIONS.map((s) => (
          <NavLink
            key={s.key}
            to={to(`/settings/${s.key}`)}
            className={({ isActive }) => `-mb-px border-b-2 px-3 py-3 text-small ${isActive || (s.key === "team" && !section) ? "border-ink font-medium" : "border-transparent text-muted hover:text-ink"}`}
          >
            {s.label}
          </NavLink>
        ))}
      </nav>
      <div className="mt-6">{section === "projects" ? <Projects /> : section === "profile" ? <Profile /> : <Team />}</div>
    </div>
  );
}
