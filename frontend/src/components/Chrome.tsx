import { useEffect, useState } from "react";
import { api, APPROVALS_CHANGED } from "../lib/api";

export function Logo() {
  return (
    <span className="flex items-center gap-2 text-[17px] font-semibold tracking-[-0.02em]">
      <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden>
        <path d="M12 2.5 4 5.5v6.2c0 4.6 3.3 8.6 8 9.8 4.7-1.2 8-5.2 8-9.8V5.5z" className="fill-accent" />
        <path d="M7.5 15.5 11 11l2.5 2.5L17 8" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      Warden
    </span>
  );
}

/** Pending approvals count for the nav badge; refreshes on change events and every 15 s. */
export function usePendingCount() {
  const [n, setN] = useState(0);
  useEffect(() => {
    const load = () => api.approvals().then((a) => setN(a.filter((x) => x.status === "pending").length)).catch(() => setN(0));
    load();
    const t = window.setInterval(load, 15000);
    window.addEventListener(APPROVALS_CHANGED, load);
    return () => {
      window.clearInterval(t);
      window.removeEventListener(APPROVALS_CHANGED, load);
    };
  }, []);
  return n;
}
