import Link from 'next/link';

// Prototype `.empty`: dashed, centred, names the next action (playbook 4.4,
// 6.5). Copy comes in as props from the catalog.
export function EmptyState({ title, body, action }: { title: string; body: string; action?: { label: string; href: string; onClick?: () => void } }) {
  return (
    <div className="rounded-card border border-dashed border-line-control p-6 text-center text-muted" data-empty-state="">
      <h2 className="text-fg">{title}</h2>
      <p className="mx-auto mt-2 max-w-[60ch]">{body}</p>
      {action !== undefined ? (
        // `onClick` is for the part of a view the address does not carry, such
        // as a phrase someone typed: the screen clears that here while the
        // link puts the rest of the view back.
        <Link href={action.href} onClick={action.onClick} className="mt-3 inline-block font-medium text-fg underline">
          {action.label}
        </Link>
      ) : null}
    </div>
  );
}
