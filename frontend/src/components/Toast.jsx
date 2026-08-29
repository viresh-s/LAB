import React, { useEffect } from 'react';
import { CheckCircle, AlertCircle, X } from 'lucide-react';

export default function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    if (message) {
      const timer = setTimeout(onClose, 5000);
      return () => clearTimeout(timer);
    }
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[100] animate-in slide-in-from-bottom-8 fade-in duration-300">
      <div className={`flex items-center gap-3 px-5 py-4 rounded-xl shadow-xl border ${
        type === 'error' ? 'bg-rose-50 border-rose-200 text-rose-800' : 'bg-emerald-50 border-emerald-200 text-emerald-800'
      }`}>
        {type === 'error' ? <AlertCircle className="w-5 h-5 text-rose-500" /> : <CheckCircle className="w-5 h-5 text-emerald-500" />}
        <p className="font-medium text-sm">{message}</p>
        <button type="button" onClick={onClose} className="ml-2 hover:opacity-70 transition-opacity">
          <X className={`w-4 h-4 ${type === 'error' ? 'text-rose-500' : 'text-emerald-500'}`} />
        </button>
      </div>
    </div>
  );
}
