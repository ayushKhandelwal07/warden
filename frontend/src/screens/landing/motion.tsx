import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** Users who ask for less motion get the final state of every animation. */
export const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** True once the element has scrolled into view (stays true). */
export function useInView<T extends HTMLElement>(margin = "0px 0px -12% 0px") {
  const ref = useRef<T>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (reducedMotion()) return setSeen(true);
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setSeen(true), { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [seen, margin]);
  return [ref, seen] as const;
}

/** 0 → 1 as the element travels through the viewport: 0 when its top reaches the bottom edge,
 *  1 when its bottom reaches the top edge minus one viewport (works for tall pinned sections). */
export function useScrollProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [p, setP] = useState(0);
  useEffect(() => {
    if (reducedMotion()) return setP(1);
    let raf = 0;
    const tick = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const span = r.height - window.innerHeight;
      const v = span > 0 ? -r.top / span : 1 - (r.top - window.innerHeight * 0.2) / (window.innerHeight * 0.6);
      setP(Math.min(1, Math.max(0, v)));
    };
    const on = () => (raf ||= requestAnimationFrame(tick));
    tick();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      cancelAnimationFrame(raf);
    };
  }, []);
  return [ref, p] as const;
}

export function useScrolled(y = 24) {
  const [s, setS] = useState(false);
  useEffect(() => {
    const on = () => setS(window.scrollY > y);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, [y]);
  return s;
}

/** Fades and lifts its children in when scrolled into view. */
export function Reveal({ children, delay = 0, className = "", as: Tag = "div" }: { children: ReactNode; delay?: number; className?: string; as?: "div" | "section" | "li" }) {
  const [ref, seen] = useInView<HTMLDivElement>();
  return (
    <Tag ref={ref as never} className={`lp-reveal ${seen ? "is-in" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` } as CSSProperties}>
      {children}
    </Tag>
  );
}

/** Counts up to `to` the first time it's visible. */
export function CountUp({ to, duration = 1200, suffix = "", className = "" }: { to: number; duration?: number; suffix?: string; className?: string }) {
  const [ref, seen] = useInView<HTMLSpanElement>();
  const [v, setV] = useState(to);
  useEffect(() => {
    setV(to);
    if (!seen || reducedMotion()) return;
    const t0 = performance.now();
    let raf = requestAnimationFrame(function step(t) {
      const k = Math.min(1, (t - t0) / duration);
      setV(Math.round(to * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(step);
    });
    return () => cancelAnimationFrame(raf);
  }, [seen, to, duration]);
  return (
    <span ref={ref} className={`tabular-nums ${className}`}>
      {v.toLocaleString()}
      {suffix}
    </span>
  );
}

/** A paragraph whose words light up one by one as it scrolls past (muted → ink). Bold parts stay bold. */
export function ScrollWords({ parts, className = "" }: { parts: { text: string; strong?: boolean }[]; className?: string }) {
  const [ref, p] = useScrollProgress<HTMLParagraphElement>();
  const words = parts.flatMap((part) => part.text.split(/(\s+)/).filter(Boolean).map((w) => ({ w, strong: part.strong })));
  const real = words.filter((x) => x.w.trim()).length;
  let i = 0;
  return (
    <p ref={ref} className={className}>
      {words.map((x, k) => {
        if (!x.w.trim()) return x.w;
        const lit = p * (real + 4) > i++;
        return (
          <span key={k} className={`transition-colors duration-300 ${lit ? "text-ink" : "text-ink/20"} ${x.strong ? "font-semibold" : ""}`}>
            {x.w}
          </span>
        );
      })}
    </p>
  );
}

/** Cycles 0..n-1 every `ms` while `on`. */
export function useTicker(n: number, ms: number, on = true) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!on || reducedMotion()) return;
    const t = window.setInterval(() => setI((x) => (x + 1) % n), ms);
    return () => window.clearInterval(t);
  }, [n, ms, on]);
  return i;
}
