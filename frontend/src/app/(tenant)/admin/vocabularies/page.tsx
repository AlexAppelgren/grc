import { AdminGate } from '@/components/admin/AdminGate';
import { VocabulariesScreen } from '@/components/admin/VocabulariesScreen';

export default function VocabulariesPage() {
  return (
    <AdminGate id="admin-vocabularies">
      <VocabulariesScreen />
    </AdminGate>
  );
}
