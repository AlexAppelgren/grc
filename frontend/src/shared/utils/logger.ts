// The one file that may talk to the console (playbook 6.6); eslint.config.js
// switches `no-console` off for this path only.
// Production-silent except errors. Never log tokens, PII or tenant content:
// the arguments are meant for identifiers and counts, and Sentry (when wired)
// receives only what passes through `error`.
type Meta = Record<string, string | number | boolean | null | undefined>;

const isProduction = process.env.NODE_ENV === 'production';

function emit(level: 'debug' | 'info' | 'warn' | 'error', message: string, meta?: Meta): void {
  if (isProduction && level !== 'error') return;
  const line = `[cw] ${message}`;
  if (meta === undefined) console[level](line);
  else console[level](line, meta);
}

export const logger = {
  debug: (message: string, meta?: Meta) => emit('debug', message, meta),
  info: (message: string, meta?: Meta) => emit('info', message, meta),
  warn: (message: string, meta?: Meta) => emit('warn', message, meta),
  error: (message: string, meta?: Meta) => emit('error', message, meta),
};
