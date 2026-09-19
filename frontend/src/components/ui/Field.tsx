import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

import { cn } from '@/shared/utils/cn';

// Prototype `.field`: label, control, hint, error. Placeholders render as
// dim hints (playbook 6.5) through the base styles below; the copy comes in
// from the catalog through props.

export const controlClass =
  'w-full min-h-11 rounded-s border border-line-strong bg-surface px-3 py-2 placeholder:italic placeholder:text-muted aria-invalid:border-negative';

export function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div className="mb-3.5 grid gap-1.5">
      <label htmlFor={id} className="font-semibold text-meta">
        {label}
      </label>
      {children}
      {hint !== undefined ? (
        <span id={`${id}-hint`} className="text-meta text-muted">
          {hint}
        </span>
      ) : null}
      {error !== undefined ? (
        <span id={`${id}-error`} role="alert" className="text-meta text-negative">
          {error}
        </span>
      ) : null}
    </div>
  );
}

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(controlClass, className)} {...rest} />;
}

export function TextArea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(controlClass, 'min-h-[76px] resize-y', className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(controlClass, className)} {...rest}>
      {children}
    </select>
  );
}

// Prototype `.check`: a checkbox row with an optional second line.
export function CheckRow({ id, label, hint, checked, disabled, onChange }: { id: string; label: string; hint?: string; checked: boolean; disabled?: boolean; onChange?: (checked: boolean) => void }) {
  return (
    <label htmlFor={id} className="flex items-start gap-2.5 border-b border-line py-2.5 last:border-b-0">
      <input id={id} type="checkbox" className="mt-0.5 h-5 w-5 accent-brand" checked={checked} disabled={disabled} onChange={(e) => onChange?.(e.target.checked)} />
      <span>
        {label}
        {hint !== undefined ? <small className="block text-meta text-muted">{hint}</small> : null}
      </span>
    </label>
  );
}

/** A group of check rows under one legend. */
export function CheckGroup({ legend, hint, error, children }: { legend: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <fieldset className="mb-3.5 grid gap-0 border-0 p-0">
      <legend className="mb-1 font-semibold text-meta">{legend}</legend>
      {children}
      {hint !== undefined ? <span className="mt-1 text-meta text-muted">{hint}</span> : null}
      {error !== undefined ? (
        <span role="alert" className="mt-1 text-meta text-negative">
          {error}
        </span>
      ) : null}
    </fieldset>
  );
}
