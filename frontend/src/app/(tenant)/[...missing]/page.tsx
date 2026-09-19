import { notFound } from 'next/navigation';

// Any tenant address no route claims, which today includes the tab bar's
// Watch, Inventory and Search and More's Roadmap, renders the tenant group's
// not-found inside the shell, so the bar and the rail stay
// (design/system/navigation.md 15). Explicit routes (auth, dev, the console)
// still win over this catch-all.
export default function MissingPage(): never {
  notFound();
}
