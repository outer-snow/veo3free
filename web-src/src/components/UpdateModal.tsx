import { Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import type { UpdateInfo } from '../types';

interface UpdateModalProps {
  isOpen: boolean;
  updateInfo: UpdateInfo | null;
  onClose: () => void;
  onDownload: () => void;
}

export function UpdateModal({
  isOpen,
  updateInfo,
  onClose,
  onDownload,
}: UpdateModalProps) {
  if (!isOpen || !updateInfo) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="bg-white rounded-2xl p-6 max-w-md w-full mx-4 shadow-xl"
      >
        <div className="text-center mb-4">
          <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-emerald-100 flex items-center justify-center">
            <Sparkles className="w-7 h-7 text-emerald-600" />
          </div>
          <h3 className="text-lg font-semibold text-zinc-900">发现新版本</h3>
          <p className="text-sm text-zinc-500 mt-1">
            v{updateInfo.current_version} → v{updateInfo.latest_version}
          </p>
        </div>

        {updateInfo.release_notes && (
          <div className="bg-zinc-50 rounded-xl p-4 mb-4 max-h-40 overflow-y-auto">
            <p className="text-xs text-zinc-600 whitespace-pre-wrap">
              {updateInfo.release_notes}
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 py-3 px-4 bg-zinc-100 text-zinc-700 rounded-xl text-sm font-medium hover:bg-zinc-200 transition-colors"
          >
            稍后提醒
          </button>
          <button
            onClick={onDownload}
            className="flex-1 py-3 px-4 bg-emerald-500 text-white rounded-xl text-sm font-medium hover:bg-emerald-600 transition-colors"
          >
            前往下载
          </button>
        </div>
      </motion.div>
    </div>
  );
}
