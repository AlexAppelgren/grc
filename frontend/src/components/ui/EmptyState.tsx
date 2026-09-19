import Link from 'next/link';

// Prototype `.empty`: dashed, centred, names the next action (playbook 4.4,
// 6.5). Copy comes in as props from the catalog.
export function EmptyState({ title, body, action }: { title: string; body: string; action?: { label: string; href: string } }) {
  return (
    <div className="rounded-m border border-dashed border-line-strong p-7 text-center text-muted" data-empty-state="">
      <h2 className="text-fg">{title}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{body}</p>
      {action !== undefined ? (
        <Link href={action.href} className="mt-4 inline-block font-semibold text-fg underline">
          {action.label}
        </Link>
      ) : null}
    </div>
  );
}
