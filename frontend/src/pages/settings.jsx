import React from 'react';

export default function Settings() {
  return (
    <div className="min-h-screen bg-slate-900 text-white p-8">
      <div className="max-w-4xl mx-auto space-y-6">
        <h1 className="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-indigo-500">
          Settings
        </h1>
        <div className="p-6 bg-slate-800 rounded-xl border border-slate-700 space-y-4">
          <h2 className="text-xl font-semibold">General Config</h2>
          <div>
            <label className="block text-sm font-medium text-slate-350">Lab Name</label>
            <input
              type="text"
              placeholder="E.g. Apex Diagnostics"
              className="w-full px-4 py-2 mt-1 bg-slate-750 border border-slate-700 rounded-md focus:ring-2 focus:ring-indigo-500 text-white focus:outline-none"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
