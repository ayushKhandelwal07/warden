import { useEffect, useState } from "react";
import { api, CONTRADICTIONS_CHANGED, type Contradiction } from "./api";

let cache: Promise<Contradiction[]> | null = null;
const load = () => (cache ??= api.contradictions().then((r) => r.items).catch(() => []));

/** Open contradictions, fetched once and shared by every component on the page; refreshed when a scan finishes. */
export function useContradictions() {
  const [items, setItems] = useState<Contradiction[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    const run = () => load().then((i) => alive && (setItems(i), setLoading(false)));
    run();
    const onChange = () => {
      cache = null;
      run();
    };
    window.addEventListener(CONTRADICTIONS_CHANGED, onChange);
    return () => {
      alive = false;
      window.removeEventListener(CONTRADICTIONS_CHANGED, onChange);
    };
  }, []);
  return { items, loading };
}
