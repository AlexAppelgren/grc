'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { adminGroups } from '@/shared/navigation/registry';
import { usePermissions } from '@/shared/navigation/require-permission';

// /admin (ADM-01, ADM-03, D-137): opens the first page of the first group this
// person's permissions unlock, in place of the old list of sections. The tab bar
// above it is the way to every other page. Nothing here checks a role name.
export function AdminIndexScreen() {
  const router = useRouter();
  const permissions = usePermissions();
  const first = permissions === null ? undefined : adminGroups(permissions)[0]?.pages[0];
  useEffect(() => {
    if (first !== undefined) router.replace(first.href);
  }, [first, router]);
  return null;
}
