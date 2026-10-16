import { EmptyState } from "../components/ui";

/** Honest empty state for screens whose backend isn't built yet (no mock data, Rule 2). */
export function Upcoming({ title, message }: { title: string; message: string }) {
  return (
    <section className="mx-auto max-w-[680px] px-6 pt-20 text-center">
      <h1 className="text-h1 font-semibold">{title}</h1>
      <EmptyState message={message} />
    </section>
  );
}
