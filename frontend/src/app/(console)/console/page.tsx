'use client';

import { Redirect } from '@/components/shell/Redirect';
import { destinations, visibleDestinations } from '@/shared/navigation/registry';
import { RestrictedScreen, usePermissions } from '@/shared/navigation/require-permission';

// /console: on to the first console destination the person's permissions
// unlock, in the registry's order. Anyone without one, every tenant member
// among them, gets the Restricted screen naming what the console's first
// destination needs.
export default function ConsolePage() {
  const [first] = visibleDestinations('console', usePermissions() ?? []);
  if (first !== undefined) return <Redirect to={first.href} />;
  const [door] = destinations.filter((d) => d.surface === 'console');
  return <RestrictedScreen requiredPermission={door?.anyOfPermissions[0]} />;
}
