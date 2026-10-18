import { useCallback, useEffect, useState } from "react";

type State<T> = { data: T | null; error: Error | null; loading: boolean };

/** Fetches once on mount; `reload` re-runs. Errors are surfaced, never swallowed. */
export function useApi<T>(fn: () => Promise<T>) {
  const [state, setState] = useState<State<T>>({ data: null, error: null, loading: true });
  const reload = useCallback(() => {
    // Keep what is on screen while refreshing: only the very first load shows a loading state.
    setState((s) => ({ ...s, loading: s.data === null, error: null }));
    fn()
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error: Error) => setState((s) => ({ data: s.data, error: s.data ? null : error, loading: false })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(reload, [reload]);
  return { ...state, reload };
}
