import type { ReactNode } from 'react';

import { AdminTabs } from '@/components/admin/AdminTabs';

// Every admin page sits under Admin's tab bar (D-137).
export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <AdminTabs />
      {children}
    </>
  );
}
