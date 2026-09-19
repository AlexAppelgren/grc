'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';

import { useT } from '@/shared/i18n/LocaleProvider';
import { findDestination } from '@/shared/navigation/registry';
import { RequirePermission } from '@/shared/navigation/require-permission';

// Every admin screen sits behind the client gate of its registry entry
// (playbook 6.2); the server's structured 403 is the enforcer.
export function AdminGate({ id, children }: { id: string; children: ReactNode }) {
  const destination = findDestination(id);
  return <RequirePermission anyOf={destination?.anyOfPermissions ?? []}>{children}</RequirePermission>;
}

// Prototype `.back`: the way up, one level.
export function BackLink({ href, label }: { href: string; label: string }) {
  const t = useT();
  const text = `← ${label.length > 0 ? label : t('common.back')}`;
  return (
    <Link href={href} className="mb-3 inline-block font-semibold underline">
      {text}
    </Link>
  );
}
