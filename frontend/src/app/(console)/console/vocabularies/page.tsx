import { AdminGate } from '@/components/admin/AdminGate';
import { VocabulariesScreen } from '@/components/admin/VocabulariesScreen';

// The shared library lists (VOC-07): every change is a proposal a second
// library editor approves.
export default function ConsoleVocabulariesPage() {
  return (
    <AdminGate id="console-vocabularies">
      <VocabulariesScreen surface="console" />
    </AdminGate>
  );
}
