import { notFound } from 'next/navigation';

// Any address no route claims. Explicit routes (auth, dev, the console, the
// tenant screens) still win over this catch-all.
//
// It sits in a group of its own, outside the session gate, so the server
// renders it and the response is a real 404: behind the gate the page never
// rendered on the server and every unknown address answered 200 with the app,
// the soft 404 a bank's web filter reads as a phishing kit. The group's
// not-found still draws the screen inside the gate and the shell.
export default function MissingPage(): never {
  notFound();
}
