import React, { useState, useEffect } from 'react';
import { supabase } from '../lib/supabase';
import { useRouter } from 'next/router';
import { ShieldCheck, Mail, Lock, Eye, EyeOff } from 'lucide-react';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  // Listen for auth state changes (e.g. after github OAuth redirect)
  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        redirectUser(session.user.email);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (session) {
        redirectUser(session.user.email);
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  const redirectUser = (userEmail) => {
    if (userEmail === 'viresh.s8637@gmail.com') {
      router.push('/master');
    } else {
      router.push('/dashboard');
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
    } catch (error) {
      alert(error.message);
    } finally {
      setLoading(false);
    }
  };



  return (
    <div className="flex items-center justify-center min-h-screen bg-stone-50 text-slate-800 p-4">
      <div className="w-full max-w-md p-6 sm:p-8 space-y-6 bg-white rounded-3xl shadow-xl border border-stone-200">
        
        <div className="flex flex-col items-center text-center space-y-4">
          <div className="bg-sky-100 p-3 rounded-2xl text-sky-600">
            <ShieldCheck className="w-10 h-10" />
          </div>
          <div>
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">
              Welcome Back
            </h2>
            <p className="text-slate-500 mt-1">
              Sign in to access your dashboard.
            </p>
          </div>
        </div>

        <form onSubmit={handleLogin} className="space-y-4 pt-4">
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1.5">Email Address</label>
            <div className="relative">
              <Mail className="w-5 h-5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="lab@example.com"
                className="w-full pl-10 pr-4 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 outline-none transition-all"
              />
            </div>
          </div>
          
          <div>
            <label className="block text-sm font-medium text-slate-600 mb-1.5">Password</label>
            <div className="relative">
              <Lock className="w-5 h-5 text-slate-400 absolute left-3 top-2.5" />
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full pl-10 pr-10 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 outline-none transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
              >
                {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
              </button>
            </div>
          </div>

          <button 
            type="submit" 
            disabled={loading}
            className="w-full py-3 mt-4 bg-sky-600 hover:bg-sky-700 shadow-sm shadow-sky-200 rounded-xl text-white font-semibold transition-all transform hover:-translate-y-0.5 disabled:opacity-50 disabled:transform-none"
          >
            {loading ? 'Processing...' : 'Sign In'}
          </button>
        </form>



      </div>
    </div>
  );
}
