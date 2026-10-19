import { useEffect, useState } from "react";
import { api, type ExampleNames } from "./api";

const cache = new Map<string, Promise<ExampleNames>>();

/** Names from the open project's graph (a service worth protecting, its caller, an internet-facing service, the most
 * sensitive data, the top advisory), so suggestions and defaults never name something only the demo graph has. */
export function useExamples(slug: string): ExampleNames | null {
  const [names, setNames] = useState<ExampleNames | null>(null);
  useEffect(() => {
    let live = true;
    if (!cache.has(slug)) cache.set(slug, api.examples().catch((e) => (cache.delete(slug), Promise.reject(e))));
    cache.get(slug)!.then((n) => live && setNames(n), () => live && setNames(null));
    return () => {
      live = false;
    };
  }, [slug]);
  return names;
}

/** Forget cached names (after a project's graph is rebuilt). */
export function forgetExamples(slug?: string) {
  if (slug) cache.delete(slug);
  else cache.clear();
}
