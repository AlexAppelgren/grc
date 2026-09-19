import { AdminGate } from '@/components/admin/AdminGate';
import { MemberDetailScreen } from '@/components/admin/MemberDetailScreen';

export default async function MemberDetailPage({ params }: { params: Promise<{ userId: string }> }) {
  const { userId } = await params;
  return (
    <AdminGate id="admin-members">
      <MemberDetailScreen userId={userId} />
    </AdminGate>
  );
}
