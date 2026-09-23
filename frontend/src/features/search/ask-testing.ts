import { vi } from 'vitest';

// Test support for Ask's stream: the network under the fetch adapter of the
// one axios instance, answering as the server's `text/event-stream` does.
// Not a mock of the API contract: the journeys prove that.

/** A `text/event-stream` response delivering `chunks` one read at a time. */
export function sseResponse(chunks: readonly string[], status = 200): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

/** The frames of `events`, one `data:` line and a blank line each. */
export function framesOf(events: readonly unknown[]): string[] {
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`);
}

/** Replaces the network for the fetch adapter; returns every request it saw. */
export function stubFetch(answer: (request: Request) => Response | Promise<Response>): Request[] {
  const requests: Request[] = [];
  vi.stubGlobal('fetch', async (input: Request) => {
    requests.push(input.clone());
    return answer(input);
  });
  return requests;
}
