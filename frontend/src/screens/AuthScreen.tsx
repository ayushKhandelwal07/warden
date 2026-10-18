import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ArrowRight, Users } from "lucide-react";
import { Logo } from "../components/Chrome";
import { api, type InviteInfo } from "../lib/api";
import { defaultProject, useAuth } from "../lib/auth";

function Field({ label, ...props }: { label: string } & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-small font-medium">{label}</span>
      <input {...props} className="h-11 rounded-full border border-line bg-bg px-4 text-body outline-none transition-colors placeholder:text-muted focus:border-ink" />
    </label>
  );
}

/** Log in and sign up share one screen. An invite token (from /invite/:token) joins that team on success. */
export function AuthScreen({ mode }: { mode: "login" | "signup" }) {
  const { me, setMe } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const invite = params.get("invite") ?? undefined;
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (invite) api.invite(invite).then(setInfo).catch((e) => setError(e.message));
  }, [invite]);

  if (me && !busy) {
    const p = defaultProject(me);
    return <Navigate to={p ? `/app/${p.slug}/home` : "/settings"} replace />;
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const m = mode === "login" ? await api.login(form.email, form.password, invite) : await api.signup(form.name, form.email, form.password, invite);
      setMe(m);
      // An invite lands you in the team you just joined; otherwise the shared project.
      const p = (info && m.projects.find((x) => x.org_id === info.org_id)) || defaultProject(m);
      nav(p ? `/app/${p.slug}/home` : "/", { replace: true });
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const other = mode === "login" ? "/signup" : "/login";
  return (
    <div className="flex min-h-screen flex-col bg-bg">
      <header className="mx-auto flex h-16 w-full max-w-[1200px] items-center px-4 sm:px-6">
        <Link to="/" aria-label="Warden">
          <Logo />
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-[8vh] pb-16">
        <div className="rise-in w-full max-w-[400px]">
          <h1 className="text-h1 font-semibold">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
          <p className="mt-2 text-muted">
            {mode === "login"
              ? "Log in to your team's security graph."
              : info
                ? `You'll join ${info.org_name} and every project in it.`
                : "You'll join the Google Microservices project, ready to ask."}
          </p>
          {info && (
            <div className="mt-6 flex items-center gap-3 rounded-card border border-line p-4 text-small">
              <Users size={18} className="shrink-0" />
              <span>
                {info.invited_by ? `${info.invited_by} invited you` : "You're invited"} to <b className="font-semibold">{info.org_name}</b> as {info.role}.
              </span>
            </div>
          )}
          <form onSubmit={submit} className="mt-8 flex flex-col gap-4">
            {mode === "signup" && <Field label="Name" value={form.name} onChange={set("name")} autoComplete="name" placeholder="Ada Lovelace" required />}
            <Field label="Email" type="email" value={form.email} onChange={set("email")} autoComplete="email" placeholder="you@company.com" required />
            <Field
              label="Password"
              type="password"
              value={form.password}
              onChange={set("password")}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "signup" ? "At least 8 characters" : ""}
              minLength={mode === "signup" ? 8 : undefined}
              required
            />
            {error && <p className="text-small text-accent" role="alert">{error}</p>}
            <button type="submit" disabled={busy} className="mt-2 inline-flex h-11 items-center justify-center gap-2 rounded-full bg-ink px-5 text-small font-medium text-white transition-opacity hover:opacity-85 disabled:opacity-40">
              {busy ? "One moment…" : mode === "login" ? "Log in" : "Create account"} <ArrowRight size={15} />
            </button>
          </form>
          <p className="mt-6 text-small text-muted">
            {mode === "login" ? "New to Warden? " : "Already have an account? "}
            <Link to={invite ? `${other}?invite=${invite}` : other} className="font-medium text-ink hover:underline">
              {mode === "login" ? "Create an account" : "Log in"}
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}

/** /invite/:token: signed in → join right away; signed out → sign up (or log in) with the invite attached. */
export function InviteScreen() {
  const { token = "" } = useParams();
  const { me, setMe } = useAuth();
  const nav = useNavigate();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!me) return;
    api
      .acceptInvite(token)
      .then((m) => {
        setMe(m);
        const p = m.projects.find((x) => x.org_id === m.org_id) ?? defaultProject(m);
        nav(p ? `/app/${p.slug}/home` : "/settings/team", { replace: true });
      })
      .catch((e) => setError(e.message));
  }, [me, token, setMe, nav]);

  if (!me) return <Navigate to={`/signup?invite=${token}`} replace />;
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      {error ? (
        <div className="max-w-[400px] text-center">
          <p className="text-h2 font-semibold">This invite didn't work</p>
          <p className="mt-2 text-muted">{error}</p>
          <Link to="/" className="mt-6 inline-block text-small font-medium hover:underline">Go to Warden</Link>
        </div>
      ) : (
        <p className="text-muted">Joining the team…</p>
      )}
    </div>
  );
}
