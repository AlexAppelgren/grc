// Where demo mode comes from. The public page frames the app under this name,
// and a browsing context keeps its name across every navigation inside the
// frame, a full reload included, so the app in the frame is answered from the
// recordings from its first request to its last. Outside that frame the name
// is not enough on its own: the parent must be this very origin, so no other
// site can put the app into demo mode by naming a window.

export const DEMO_FRAME_NAME = 'bleqq-demo';

interface FrameWindow {
  name: string;
  self: unknown;
  top: unknown;
  location: { origin: string };
  parent: { location: { origin: string } };
}

export function isDemoFrameWindow(win: FrameWindow): boolean {
  if (win.name !== DEMO_FRAME_NAME || win.self === win.top) return false;
  try {
    return win.parent.location.origin === win.location.origin;
  } catch {
    // A parent on another origin cannot be read at all.
    return false;
  }
}

export function isDemoFrame(): boolean {
  return typeof window !== 'undefined' && isDemoFrameWindow(window);
}
