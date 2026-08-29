import React from 'react';
import Link from 'next/link';
import { 
  Activity, ShieldCheck, Zap, PhoneCall, 
  MessageSquare, Clock, ArrowRight, Microscope, TestTube
} from 'lucide-react';

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-50 font-sans selection:bg-sky-200">
      
      {/* Decorative Background Elements */}
      <div className="absolute top-0 inset-x-0 h-96 bg-gradient-to-b from-sky-100/50 to-transparent -z-10 pointer-events-none" />
      <div className="absolute top-[-10%] left-[-10%] w-96 h-96 bg-sky-400/20 rounded-full blur-3xl -z-10" />
      <div className="absolute top-[20%] right-[-5%] w-96 h-96 bg-indigo-400/20 rounded-full blur-3xl -z-10" />

      {/* Navigation Bar */}
      <nav className="sticky top-0 z-50 backdrop-blur-md bg-white/70 border-b border-white/20">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex justify-between items-center h-20">
          <div className="flex items-center gap-2">
            <div className="bg-gradient-to-tr from-sky-600 to-indigo-600 p-2.5 rounded-xl shadow-sm">
              <ShieldCheck className="text-white w-6 h-6" />
            </div>
            <span className="text-2xl font-extrabold tracking-tight text-slate-900">LabSaaS</span>
          </div>
          
          <div className="flex items-center gap-4">
            <Link 
              href="/login" 
              className="px-6 py-2.5 text-sm font-semibold text-slate-700 hover:text-slate-900 transition-colors"
            >
              Sign In
            </Link>
            <Link 
              href="/login" 
              className="group flex items-center gap-2 px-6 py-2.5 bg-slate-900 hover:bg-slate-800 text-white text-sm font-medium rounded-full shadow-lg shadow-slate-900/20 transition-all transform hover:-translate-y-0.5"
            >
              Lab Dashboard
              <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <main className="max-w-7xl mx-auto px-6 lg:px-8 pt-24 pb-32 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white border border-slate-200 shadow-sm mb-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <span className="flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-sky-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-sky-500"></span>
          </span>
          <span className="text-sm font-medium text-slate-600">The Future of Lab Bookings is Here</span>
        </div>

        <h1 className="text-5xl md:text-7xl font-extrabold text-slate-900 tracking-tight leading-tight mb-8 animate-in fade-in slide-in-from-bottom-6 duration-700">
          Automate Bookings with <br className="hidden md:block" />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-sky-500 to-indigo-600">
            AI Voice & WhatsApp
          </span>
        </h1>
        
        <p className="text-xl text-slate-600 mb-12 max-w-2xl mx-auto animate-in fade-in slide-in-from-bottom-8 duration-1000 leading-relaxed">
          The all-in-one operating system for diagnostic labs. Let AI handle patient calls, dispatch collectors instantly, and manage your entire workflow effortlessly.
        </p>
        
        <div className="flex flex-col sm:flex-row justify-center items-center gap-4 animate-in fade-in slide-in-from-bottom-10 duration-1000 delay-150">
          <Link 
            href="/login" 
            className="flex items-center gap-2 px-8 py-4 bg-sky-600 hover:bg-sky-700 text-white text-lg font-medium rounded-full shadow-xl shadow-sky-600/30 transition-all transform hover:-translate-y-1"
          >
            Access Dashboard
          </Link>
          <a 
            href="#features" 
            className="flex items-center gap-2 px-8 py-4 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-lg font-medium rounded-full shadow-sm transition-all transform hover:-translate-y-1"
          >
            Explore Features
          </a>
        </div>
      </main>

      {/* Feature Section */}
      <section id="features" className="bg-white py-24 border-t border-slate-100">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-slate-900">Built for Modern Laboratories</h2>
            <p className="mt-4 text-lg text-slate-500">Everything you need to run a high-volume diagnostic lab.</p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {/* Feature 1 */}
            <div className="p-8 rounded-3xl bg-slate-50 border border-slate-100 hover:shadow-xl hover:shadow-slate-200/50 transition-all group">
              <div className="w-14 h-14 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <PhoneCall className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-3">AI Voice Receptionist</h3>
              <p className="text-slate-600 leading-relaxed">
                Never miss a booking. Our AI answers calls 24/7, extracts patient details, and books tests directly into your system.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="p-8 rounded-3xl bg-slate-50 border border-slate-100 hover:shadow-xl hover:shadow-slate-200/50 transition-all group">
              <div className="w-14 h-14 rounded-2xl bg-emerald-100 text-emerald-600 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <MessageSquare className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-3">WhatsApp Automation</h3>
              <p className="text-slate-600 leading-relaxed">
                Automatically dispatch sample collectors via WhatsApp and notify patients as soon as their reports are ready.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="p-8 rounded-3xl bg-slate-50 border border-slate-100 hover:shadow-xl hover:shadow-slate-200/50 transition-all group">
              <div className="w-14 h-14 rounded-2xl bg-sky-100 text-sky-600 flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Activity className="w-7 h-7" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-3">Centralized Dashboard</h3>
              <p className="text-slate-600 leading-relaxed">
                Manage walk-ins, track collector statuses, upload reports, and view daily analytics all in one intuitive interface.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-900 text-slate-400 py-12 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 flex flex-col md:flex-row justify-between items-center gap-6">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-sky-500" />
            <span className="text-xl font-bold text-white">LabSaaS</span>
          </div>
          <p className="text-sm">© {new Date().getFullYear()} LabBooking SaaS. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
