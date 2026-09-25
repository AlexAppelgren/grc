'use client';

import { TodayScreen } from '@/components/home/TodayScreen';
import { Redirect } from '@/components/shell/Redirect';
import { useSession } from '@/features/identity/hooks';
import { CONSOLE_HOME, surfaceOf } from '@/shared/navigation/registry';

// Today, for a member of an organisation. Platform staff have no tenant and
// so no Today: they go on to the console (ADM-02).
export default function TodayPage() {
  const { me } = useSession();
  return surfaceOf(me) === 'console' ? <Redirect to={CONSOLE_HOME} /> : <TodayScreen />;
}
