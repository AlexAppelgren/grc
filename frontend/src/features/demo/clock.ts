// The demo's today is the day it was recorded, so "this week" on Today, the
// briefing's week and every "3 days ago" agree with the answers they sit
// beside. Installed only inside the demo frame, whose window is its own: the
// page around it keeps the real clock.

export function installDemoClock(recordedAt: string): void {
  const RealDate = Date;
  const offset = RealDate.parse(recordedAt) - RealDate.now();
  if (Number.isNaN(offset)) return;
  class DemoDate extends RealDate {
    constructor(...args: unknown[]) {
      if (args.length === 0) super(RealDate.now() + offset);
      else super(...(args as [number]));
    }

    static override now(): number {
      return RealDate.now() + offset;
    }
  }
  globalThis.Date = DemoDate as DateConstructor;
}
