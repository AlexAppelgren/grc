import { AdminGate } from '@/components/admin/AdminGate';
import { FootprintScreen } from '@/components/admin/FootprintScreen';

export default function FootprintPage() {
  return (
    <AdminGate id="admin-footprint">
      <FootprintScreen />
    </AdminGate>
  );
}
