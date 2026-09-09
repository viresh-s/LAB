import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { supabase } from '../lib/supabase';
import { 
  LayoutDashboard, FileText, LogOut, 
  UploadCloud, Download, CheckCircle, Activity, ShieldCheck, CreditCard,
  Users, Pencil, X, Save, Copy, Search, Eye, EyeOff, Menu, Trash2
} from 'lucide-react';
import Toast from '../components/Toast';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000'; 

export default function Dashboard() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [bookings, setBookings] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  
  // Financials State
  const [financialsPassword, setFinancialsPassword] = useState('');
  const [showFinancialsPassword, setShowFinancialsPassword] = useState(false);
  const [isFinancialsUnlocked, setIsFinancialsUnlocked] = useState(false);
  const [financialsData, setFinancialsData] = useState(null);
  const [financialsError, setFinancialsError] = useState('');
  
  const getTodayStr = () => new Date().toISOString().split('T')[0];
  const getOneMonthAgoStr = () => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().split('T')[0];
  };
  const [activeTab, setActiveTab] = useState('overview'); // overview, records, financials
  const [startDate, setStartDate] = useState(getOneMonthAgoStr());
  const [endDate, setEndDate] = useState(getTodayStr());
  
  const [manualBookingId, setManualBookingId] = useState('');
  const [manualFile, setManualFile] = useState(null);

  // Patient Edit Modal
  const [editingPatient, setEditingPatient] = useState(null);
  const [editForm, setEditForm] = useState({ name: '', phone: '', test_type: '' });
  const [savingEdit, setSavingEdit] = useState(false);

  // Walk-in Booking Modal
  const [isWalkinOpen, setIsWalkinOpen] = useState(false);
  const [walkinForm, setWalkinForm] = useState({ name: '', age: '', phone: '', test_type: '', collector_phone: '', payment_status: 'pending' });
  const [creatingWalkin, setCreatingWalkin] = useState(false);

  // Toast Notification
  const [toast, setToast] = useState({ message: '', type: 'success' });

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
  };

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.push('/login');
      } else {
        setSession(session);
        const initSd = activeTab === 'overview' ? getTodayStr() : startDate;
        const initEd = activeTab === 'overview' ? getTodayStr() : endDate;
        fetchBookings(session.access_token, initSd, initEd);
        fetchMetrics(session.access_token);
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
      if (!session) router.push('/login');
    });

    return () => subscription.unsubscribe();
  }, [router]);

  useEffect(() => {
    if (session) {
      const sd = activeTab === 'overview' ? getTodayStr() : startDate;
      const ed = activeTab === 'overview' ? getTodayStr() : endDate;
      fetchBookings(session.access_token, sd, ed);
    }
  }, [startDate, endDate, activeTab]);

  // Realtime Subscription for Auto-Update
  useEffect(() => {
    if (!session) return;
    const channel = supabase
      .channel('dashboard-realtime')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'patients' },
        (payload) => {
          console.log('Realtime change received!', payload);
          const sd = activeTab === 'overview' ? getTodayStr() : startDate;
          const ed = activeTab === 'overview' ? getTodayStr() : endDate;
          fetchBookings(session.access_token, sd, ed);
          fetchMetrics(session.access_token);
        }
      )
      .subscribe();

    return () => {
      supabase.removeChannel(channel);
    };
  }, [session, startDate, endDate, activeTab]);

  const fetchBookings = async (token, sd, ed) => {
    const actualSd = sd || (activeTab === 'overview' ? getTodayStr() : startDate);
    const actualEd = ed || (activeTab === 'overview' ? getTodayStr() : endDate);
    try {
      const res = await fetch(`${API_BASE}/api/lab/bookings?start_date=${actualSd}&end_date=${actualEd}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) throw new Error('Failed to fetch bookings');
      const data = await res.json();
      setBookings(data.patients || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetrics = async (token) => {
    try {
      const res = await fetch(`${API_BASE}/api/lab/metrics`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch (err) {
      console.error("Failed to fetch metrics", err);
    }
  };

  const fetchFinancials = async (e) => {
    e.preventDefault();
    setFinancialsError('');
    try {
      const res = await fetch(`${API_BASE}/api/lab/financials`, {
        headers: { 
          Authorization: `Bearer ${session.access_token}`,
          'lab-password': financialsPassword
        }
      });
      if (!res.ok) throw new Error('Invalid password or unauthorized');
      const data = await res.json();
      setFinancialsData(data);
      setIsFinancialsUnlocked(true);
    } catch (err) {
      setFinancialsError(err.message);
    }
  };

  const handleExport = async () => {
    if (!session) return;
    try {
      const res = await fetch(`${API_BASE}/api/lab/export?start_date=${startDate}&end_date=${endDate}&format=xlsx`, {
        headers: { Authorization: `Bearer ${session.access_token}` }
      });
      
      if (!res.ok) throw new Error('Export failed');
      
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Bookings_${startDate}_to_${endDate}.xlsx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert('Error exporting data');
    }
  };

  const forceDownload = async (url, filename) => {
    try {
      const res = await fetch(url);
      const blob = await res.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename || 'Report.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) {
      console.error('Download failed', err);
      showToast('Failed to download report automatically', 'error');
      // Fallback to opening in new tab
      window.open(url, '_blank');
    }
  };

  const handleManualUpload = async (e) => {
    e.preventDefault();
    if (!manualBookingId.trim() || !manualFile) return;

    setUploadingId('manual');
    try {
      const formData = new FormData();
      formData.append('booking_id', manualBookingId.trim());
      formData.append('file', manualFile);

      const res = await fetch(`${API_BASE}/api/lab/report/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${session.access_token}` },
        body: formData
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      showToast('Report uploaded successfully!');
      setManualBookingId('');
      setManualFile(null);
      fetchMetrics(session.access_token);
      fetchBookings(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error uploading report: ${err.message}`, 'error');
    } finally {
      setUploadingId(null);
      e.target.reset();
    }
  };

  const openEditModal = (patient) => {
    setEditingPatient(patient);
    setEditForm({ name: patient.name || '', phone: patient.phone || '', test_type: patient.test_type || '' });
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    if (!editingPatient) return;
    setSavingEdit(true);
    try {
      const payload = {};
      if (editForm.name !== editingPatient.name) payload.name = editForm.name;
      if (editForm.phone !== editingPatient.phone) payload.phone = editForm.phone;
      if (editForm.test_type !== editingPatient.test_type) payload.test_type = editForm.test_type;

      if (Object.keys(payload).length === 0) {
        showToast('No changes detected.', 'error');
        setSavingEdit(false);
        return;
      }

      const res = await fetch(`${API_BASE}/api/lab/patient/${editingPatient.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error('Update failed');
      showToast('Patient updated successfully!');
      setEditingPatient(null);
      fetchBookings(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeletePatient = async (patientId, patientName) => {
    if (!window.confirm(`Are you sure you want to delete patient "${patientName}"? This action cannot be undone.`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/lab/patient/${patientId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${session.access_token}` }
      });
      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to delete patient');
      }
      showToast('Patient deleted successfully!');
      fetchBookings(session.access_token);
      fetchMetrics(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error deleting patient: ${err.message}`, 'error');
    }
  };

  const handleWalkinSubmit = async (e) => {
    e.preventDefault();
    setCreatingWalkin(true);
    try {
      // Use session user id as lab_id
      const lab_id = session.user.id;

      const res = await fetch(`${API_BASE}/webhooks/walkin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify({
          lab_id: lab_id,
          name: walkinForm.name,
          age: parseInt(walkinForm.age, 10),
          phone: walkinForm.phone,
          test_type: walkinForm.test_type,
          collector_phone: walkinForm.collector_phone, // Optional
          payment_status: walkinForm.payment_status
        })
      });

      if (!res.ok) throw new Error('Failed to create walk-in booking');
      
      const resData = await res.json();
      if (resData.status !== "success" && !resData.booking_id) {
        throw new Error("Database error: Lab account might be incomplete. Please re-create the lab.");
      }
      
      showToast('Walk-in booking created successfully!');
      setIsWalkinOpen(false);
      setWalkinForm({ name: '', age: '', phone: '', test_type: '', collector_phone: '', payment_status: 'pending' });
      fetchBookings(session.access_token);
      fetchMetrics(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error: ${err.message}`, 'error');
    } finally {
      setCreatingWalkin(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading your workspace...</div>;
  }

  const filteredBookings = bookings.filter(b => 
    b.name?.toLowerCase().includes(searchQuery.toLowerCase()) || 
    String(b.phone || '').includes(searchQuery) || 
    String(b.id || '').includes(searchQuery) || 
    b.test_type?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    b.status?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const recordsTotalPatients = bookings.length;
  const recordsTotalCollection = bookings.reduce((sum, b) => b.payment_status === 'paid' ? sum + (Number(b.payment_amount) || 0) : sum, 0);

  return (
    <>
    <div className="min-h-screen flex text-slate-800">
      
      {/* Mobile Sidebar Overlay */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 bg-slate-900/50 z-40 md:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar - Warm Trustworthy Vibe */}
      <aside className={`fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-stone-200 flex-col shadow-xl md:shadow-sm md:static md:flex transform transition-transform duration-300 ease-in-out ${isMobileMenuOpen ? 'translate-x-0 flex' : '-translate-x-full md:translate-x-0'}`}>
        <div className="p-6 flex items-center justify-between border-b border-stone-100">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="bg-sky-600 p-2 rounded-lg flex-shrink-0">
              <ShieldCheck className="text-white w-6 h-6" />
            </div>
            <h2 className="text-xl font-bold tracking-tight text-slate-900 truncate">
              {metrics?.lab_name || 'LabSaaS'}
            </h2>
          </div>
          <button 
            onClick={() => setIsMobileMenuOpen(false)}
            className="md:hidden text-slate-400 hover:text-slate-600"
          >
            <X className="w-6 h-6" />
          </button>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          <button 
            onClick={() => { setActiveTab('overview'); setIsMobileMenuOpen(false); }}
            className={`flex items-center gap-3 px-4 py-3 w-full text-left rounded-xl font-medium transition-colors ${activeTab === 'overview' ? 'bg-sky-50 text-sky-700' : 'text-slate-600 hover:bg-stone-50 hover:text-slate-900'}`}>
            <LayoutDashboard className="w-5 h-5" /> Overview
          </button>
          <button 
            onClick={() => { setActiveTab('records'); setIsMobileMenuOpen(false); }}
            className={`flex items-center gap-3 px-4 py-3 w-full text-left rounded-xl font-medium transition-colors ${activeTab === 'records' ? 'bg-sky-50 text-sky-700' : 'text-slate-600 hover:bg-stone-50 hover:text-slate-900'}`}>
            <FileText className="w-5 h-5" /> Patient Records
          </button>
          <button 
            onClick={() => { setActiveTab('financials'); setIsFinancialsUnlocked(false); setFinancialsPassword(''); setIsMobileMenuOpen(false); }}
            className={`flex items-center gap-3 px-4 py-3 w-full text-left rounded-xl font-medium transition-colors ${activeTab === 'financials' ? 'bg-emerald-50 text-emerald-700' : 'text-slate-600 hover:bg-stone-50 hover:text-slate-900'}`}>
            <CreditCard className="w-5 h-5" /> Financials
          </button>
        </nav>
        
        <div className="p-4 border-t border-stone-100">
          <button 
            onClick={() => supabase.auth.signOut()}
            className="flex items-center gap-3 px-4 py-3 w-full text-slate-600 hover:bg-red-50 hover:text-red-700 rounded-xl font-medium transition-colors"
          >
            <LogOut className="w-5 h-5" /> Sign Out
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden min-w-0">
        {/* Header */}
        <header className="bg-white/80 backdrop-blur-md border-b border-stone-200 z-10 px-4 md:px-8 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 flex-shrink-0">
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button 
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden text-slate-600 hover:text-slate-900 flex-shrink-0"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="min-w-0">
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 truncate">
                {activeTab === 'overview' ? 'Overview' : activeTab === 'records' ? 'Patient Records' : 'Financials'}
              </h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1 truncate">
                {activeTab === 'overview' ? "Welcome back! Here's what's happening today." : activeTab === 'records' ? "View and filter historical patient data." : "Protected financial metrics."}
              </p>
            </div>
          </div>
          <div className="flex gap-2 md:gap-3 w-full md:w-auto">
            <button 
              onClick={() => setIsWalkinOpen(true)}
              className="flex-1 md:flex-none flex justify-center items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-700 shadow-sm shadow-emerald-200 rounded-lg text-white font-medium transition-all"
            >
              <Users className="w-4 h-4" /> <span className="hidden sm:inline">New Walk-in</span><span className="sm:hidden">Walk-in</span>
            </button>
            {activeTab === 'records' && (
              <button 
                onClick={handleExport}
                className="flex-1 md:flex-none flex justify-center items-center gap-2 px-4 py-2.5 bg-sky-600 hover:bg-sky-700 shadow-sm shadow-sky-200 rounded-lg text-white font-medium transition-all"
              >
                <Download className="w-4 h-4" /> <span className="hidden sm:inline">Export Report</span><span className="sm:hidden">Export</span>
              </button>
            )}
          </div>
        </header>

        <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 flex-1 overflow-y-auto min-w-0 pb-24 md:pb-8">
          
          {/* WhatsApp Not Configured Alert */}
          {metrics && metrics.whatsapp_configured === false && (
            <div className="bg-rose-50 border border-rose-200 text-rose-700 p-4 rounded-xl flex items-start gap-3 shadow-sm">
              <ShieldCheck className="w-6 h-6 mt-0.5 flex-shrink-0" />
              <div>
                <h4 className="font-bold text-rose-800">WhatsApp Not Configured</h4>
                <p className="text-sm mt-1">Please ask your Master Admin to update your Meta WhatsApp credentials in the Master Dashboard. Automated AI messages will fail until this is resolved.</p>
              </div>
            </div>
          )}

          {/* Metrics Grid */}
          {activeTab === 'overview' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <MetricCard 
              icon={<Users className="w-6 h-6 text-blue-600" />}
              title="Today Booked" 
              value={metrics?.today_booked || 0} 
              bg="bg-blue-50" 
            />
            <MetricCard 
              icon={<Activity className="w-6 h-6 text-amber-600" />}
              title="In Testing" 
              value={metrics?.today_in_testing || 0} 
              bg="bg-amber-50" 
            />
            <MetricCard 
              icon={<CheckCircle className="w-6 h-6 text-emerald-600" />}
              title="Today Delivered" 
              value={metrics?.today_delivered || 0} 
              bg="bg-emerald-50" 
            />
          </div>
          )}

          {/* Date Filter & Table Section - Show on both but layout changes */}
          {activeTab === 'records' && (
            <div className="space-y-6 mb-8">
              <div className="grid grid-cols-1 md:grid-cols-1 gap-6 max-w-sm">
                <MetricCard 
                  icon={<Users className="w-6 h-6 text-indigo-600" />}
                  title="Total Patients (Selected Period)" 
                  value={recordsTotalPatients} 
                  bg="bg-indigo-50" 
                />
              </div>

              <div className="bg-white rounded-2xl shadow-sm border border-stone-200 p-6 flex flex-wrap gap-4 items-end">
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1.5">Start Date</label>
                  <input 
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    className="bg-stone-50 border border-stone-200 rounded-xl px-4 py-2 text-slate-800 focus:ring-2 focus:ring-sky-500/50 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1.5">End Date</label>
                  <input 
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    className="bg-stone-50 border border-stone-200 rounded-xl px-4 py-2 text-slate-800 focus:ring-2 focus:ring-sky-500/50 outline-none"
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === 'financials' && !isFinancialsUnlocked && (
            <div className="max-w-md mx-auto bg-white p-8 rounded-2xl shadow-sm border border-stone-200 mt-10">
              <div className="flex justify-center mb-4">
                <div className="bg-emerald-100 p-3 rounded-full text-emerald-600">
                  <ShieldCheck className="w-8 h-8" />
                </div>
              </div>
              <h2 className="text-xl font-bold text-center text-slate-800 mb-2">Protected Area</h2>
              <p className="text-sm text-slate-500 text-center mb-6">Enter your lab password to view financials.</p>
              <form onSubmit={fetchFinancials} className="space-y-4">
                <div>
                  <div className="relative">
                    <input
                      type={showFinancialsPassword ? "text" : "password"}
                      placeholder="Enter Lab Password"
                      value={financialsPassword}
                      onChange={(e) => setFinancialsPassword(e.target.value)}
                      className="w-full pl-4 pr-10 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-emerald-500/50 outline-none"
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowFinancialsPassword(!showFinancialsPassword)}
                      className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {showFinancialsPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                {financialsError && <p className="text-red-500 text-sm text-center">{financialsError}</p>}
                <button type="submit" className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl font-medium transition-colors">
                  Unlock Financials
                </button>
              </form>
            </div>
          )}

          {activeTab === 'financials' && isFinancialsUnlocked && financialsData && (
            <div className="space-y-8">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <MetricCard 
                  icon={<CreditCard className="w-6 h-6 text-emerald-600" />}
                  title="Total Monthly Collection" 
                  value={`₹${financialsData.monthly_collection}`} 
                  bg="bg-emerald-50" 
                />
                <MetricCard 
                  icon={<FileText className="w-6 h-6 text-indigo-600" />}
                  title="Total Weekly Collection" 
                  value={`₹${financialsData.weekly_collection}`} 
                  bg="bg-indigo-50" 
                />
              </div>
              
              <div className="bg-white rounded-2xl shadow-sm border border-stone-200 overflow-hidden">
                <div className="p-6 border-b border-stone-100 bg-stone-50/50">
                  <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                    <Activity className="w-5 h-5 text-slate-400" /> Test-wise Collection (This Month)
                  </h3>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[600px] text-left">
                    <thead className="bg-stone-50 border-b border-stone-200 text-slate-500 text-sm">
                      <tr>
                        <th className="px-6 py-4 font-medium">Test Type</th>
                        <th className="px-6 py-4 font-medium text-center">Count</th>
                        <th className="px-6 py-4 font-medium text-right">Amount Collected</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-100 text-sm">
                      {financialsData.test_wise.map((item, idx) => (
                        <tr key={idx} className="hover:bg-stone-50/50 transition-colors">
                          <td className="px-6 py-4 font-medium text-slate-800">{item.test_type}</td>
                          <td className="px-6 py-4 font-medium text-center text-slate-600">{item.count}</td>
                          <td className="px-6 py-4 text-right font-medium text-emerald-600">₹{item.amount}</td>
                        </tr>
                      ))}
                      {financialsData.test_wise.length === 0 && (
                        <tr>
                          <td colSpan="3" className="px-6 py-8 text-center text-slate-500">No paid tests this month yet.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          <div className={`grid grid-cols-1 gap-8 ${activeTab === 'financials' ? 'hidden' : activeTab === 'overview' ? 'lg:grid-cols-3' : ''}`}>
            {/* Table Section */}
            <div className={`${activeTab === 'overview' ? 'lg:col-span-2' : ''} bg-white rounded-2xl shadow-sm border border-stone-200 overflow-hidden`}>
              <div className="p-6 border-b border-stone-100 bg-stone-50/50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                  <FileText className="w-5 h-5 text-slate-400" /> {activeTab === 'overview' ? "Today's Patients" : "Patient Records"}
                </h3>
                <div className="relative max-w-md w-full">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search by name, ID, phone, or test..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full pl-9 pr-4 py-2 bg-white border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 outline-none text-sm"
                  />
                </div>
              </div>
              <div className="overflow-x-auto overflow-y-auto max-h-[60vh]">
                <table className="w-full min-w-[800px] text-left">
                  <thead className="bg-stone-50 border-b border-stone-200 text-slate-500 text-sm sticky top-0 z-10 shadow-sm">
                    <tr>
                      <th className="px-6 py-4 font-medium">Patient Details</th>
                      <th className="px-6 py-4 font-medium">Test</th>
                      <th className="px-6 py-4 font-medium">Status</th>
                      <th className="px-6 py-4 font-medium">Payment</th>
                      <th className="px-6 py-4 font-medium text-right">Edit</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {filteredBookings.length === 0 ? (
                      <tr>
                        <td colSpan="5" className="p-8 text-center text-slate-500">No matching bookings found.</td>
                      </tr>
                    ) : (
                      filteredBookings.map((booking) => (
                        <tr key={booking.id} className="hover:bg-stone-50/80 transition-colors">
                          <td className="px-6 py-4">
                            <div className="font-semibold text-slate-800">{booking.name}</div>
                            <div className="text-sm text-slate-500">{booking.phone}</div>
                            <div className="text-xs text-slate-400 mt-1 flex items-center gap-1">
                              ID: {booking.id.slice(0, 8)}...
                              <button 
                                onClick={() => { navigator.clipboard.writeText(booking.id); showToast('Patient ID copied!'); }} 
                                className="hover:text-sky-600 transition-colors p-0.5 rounded-md hover:bg-sky-50"
                                title="Copy full ID"
                              >
                                <Copy className="w-3 h-3" />
                              </button>
                            </div>
                          </td>
                          <td className="px-6 py-4 text-slate-600 font-medium">{booking.test_type}</td>
                          <td className="px-6 py-4">
                            <StatusBadge status={booking.status} reportLink={booking.report_link} paymentStatus={booking.payment_status} />
                          </td>
                          <td className="px-6 py-4">
                            <PaymentBadge paymentStatus={booking.payment_status} amount={booking.payment_amount} />
                          </td>
                          <td className="px-6 py-4 text-right flex justify-end gap-2">
                            {booking.report_link && (
                              <button
                                onClick={() => forceDownload(booking.report_link, `Report_${booking.name.replace(/\s+/g, '_')}.pdf`)}
                                className="p-2 rounded-lg hover:bg-emerald-50 text-emerald-400 hover:text-emerald-600 transition-colors"
                                title="Download Report"
                              >
                                <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                </svg>
                              </button>
                            )}
                            <button
                              onClick={() => openEditModal(booking)}
                              className="p-2 rounded-lg hover:bg-sky-50 text-slate-400 hover:text-sky-600 transition-colors"
                              title="Edit Patient"
                            >
                              <Pencil className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDeletePatient(booking.id, booking.name)}
                              className="p-2 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-600 transition-colors"
                              title="Delete Patient"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Upload Action Card - Only on Overview */}
            {activeTab === 'overview' && (
              <div className="bg-white rounded-2xl shadow-sm border border-stone-200 p-6 flex flex-col h-fit sticky top-24">
                <div className="flex items-center gap-3 mb-6">
                <div className="bg-teal-50 p-2 rounded-lg">
                  <UploadCloud className="text-teal-600 w-5 h-5" />
                </div>
                <h3 className="text-lg font-semibold text-slate-800">Upload Report</h3>
              </div>
              
              <form onSubmit={handleManualUpload} className="flex-1 flex flex-col gap-5">
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1.5">Booking ID</label>
                  <input 
                    type="text" 
                    required
                    value={manualBookingId}
                    onChange={(e) => setManualBookingId(e.target.value)}
                    placeholder="Enter UUID"
                    className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-600 mb-1.5">PDF File</label>
                  <div className="relative border-2 border-dashed border-stone-200 rounded-xl p-6 hover:bg-stone-50 transition-colors text-center group cursor-pointer">
                    <input 
                      type="file" 
                      required
                      accept="application/pdf"
                      onChange={(e) => setManualFile(e.target.files[0])}
                      className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                    />
                    <UploadCloud className="mx-auto h-8 w-8 text-slate-400 group-hover:text-sky-500 transition-colors mb-2" />
                    <p className="text-sm text-slate-600">
                      {manualFile ? <span className="font-semibold text-sky-600">{manualFile.name}</span> : 'Click or drag PDF here'}
                    </p>
                  </div>
                </div>
                <div className="mt-auto pt-4">
                  <button 
                    type="submit" 
                    disabled={uploadingId === 'manual'}
                    className="w-full py-3 bg-teal-600 hover:bg-teal-700 shadow-sm shadow-teal-200 rounded-xl text-white font-medium transition-all transform hover:-translate-y-0.5 disabled:opacity-50 disabled:transform-none"
                  >
                    {uploadingId === 'manual' ? 'Uploading safely...' : 'Upload & Dispatch'}
                  </button>
                </div>
              </form>
            </div>
            )}
          </div>
          
          {/* Footer */}
          <div className="mt-8 text-center text-sm text-slate-500 pb-4">
            Developed by Viresh <br className="sm:hidden" />
            <span className="hidden sm:inline"> | </span> 
            Contact: 6362268616
          </div>
          
        </div>
      </main>

      {/* Mobile Bottom Nav */}
      <div className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-stone-200 flex justify-around items-center z-40 pb-safe">
        <button 
          onClick={() => setActiveTab('overview')}
          className={`flex flex-col items-center p-3 flex-1 ${activeTab === 'overview' ? 'text-sky-600' : 'text-slate-500'}`}
        >
          <LayoutDashboard className="w-5 h-5 mb-1" />
          <span className="text-xs font-medium">Overview</span>
        </button>
        <button 
          onClick={() => setActiveTab('records')}
          className={`flex flex-col items-center p-3 flex-1 ${activeTab === 'records' ? 'text-sky-600' : 'text-slate-500'}`}
        >
          <FileText className="w-5 h-5 mb-1" />
          <span className="text-xs font-medium">Records</span>
        </button>
        <button 
          onClick={() => supabase.auth.signOut()}
          className="flex flex-col items-center p-3 flex-1 text-slate-500 hover:text-red-600"
        >
          <LogOut className="w-5 h-5 mb-1" />
          <span className="text-xs font-medium">Sign Out</span>
        </button>
      </div>

    </div>

      {/* Edit Patient Modal */}
      {editingPatient && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-white border border-stone-200 rounded-2xl w-full max-w-md shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="p-5 border-b border-stone-100 bg-stone-50/50 flex justify-between items-center flex-shrink-0">
              <div>
                <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                  <Pencil className="w-5 h-5 text-sky-600" /> Edit Patient
                </h3>
                <p className="text-xs text-slate-500 mt-0.5 font-mono truncate">ID: {editingPatient.id}</p>
              </div>
              <button onClick={() => setEditingPatient(null)} className="p-1.5 hover:bg-stone-200 rounded-full text-slate-400 hover:text-slate-700 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="p-6 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-sm font-medium text-slate-600 mb-1.5">Patient Name</label>
                <input
                  type="text"
                  required
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-600 mb-1.5">Phone Number</label>
                <input
                  type="text"
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-600 mb-1.5">Test Type</label>
                <input
                  type="text"
                  value={editForm.test_type}
                  onChange={(e) => setEditForm({ ...editForm, test_type: e.target.value })}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingPatient(null)}
                  className="flex-1 py-2.5 bg-stone-100 hover:bg-stone-200 text-slate-700 font-medium rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingEdit}
                  className="flex-1 py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  <Save className="w-4 h-4" /> {savingEdit ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Walk-in Booking Modal */}
      {isWalkinOpen && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl overflow-hidden flex flex-col max-h-[90vh] animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-stone-100 flex justify-between items-center bg-stone-50/50 flex-shrink-0">
              <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                <Users className="w-5 h-5 text-emerald-500" /> New Walk-in Booking
              </h3>
              <button onClick={() => setIsWalkinOpen(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleWalkinSubmit} className="p-6 space-y-4 overflow-y-auto flex-1">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Patient Name</label>
                <input 
                  type="text" 
                  required
                  value={walkinForm.name}
                  onChange={(e) => setWalkinForm({...walkinForm, name: e.target.value})}
                  className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
                  placeholder="John Doe"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Age</label>
                  <input 
                    type="number" 
                    required
                    min="0"
                    value={walkinForm.age}
                    onChange={(e) => setWalkinForm({...walkinForm, age: e.target.value})}
                    className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
                    placeholder="30"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Phone Number</label>
                  <input 
                    type="text" 
                    required
                    value={walkinForm.phone}
                    onChange={(e) => setWalkinForm({...walkinForm, phone: e.target.value})}
                    className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
                    placeholder="9876543210"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Test Type</label>
                <input 
                  type="text" 
                  required
                  value={walkinForm.test_type}
                  onChange={(e) => setWalkinForm({...walkinForm, test_type: e.target.value})}
                  className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
                  placeholder="CBC, Lipid Profile..."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Override Collector Phone (Optional)</label>
                <input 
                  type="text"
                  value={walkinForm.collector_phone}
                  onChange={(e) => setWalkinForm({...walkinForm, collector_phone: e.target.value})}
                  className="w-full border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500"
                  placeholder="Leave empty to use lab default"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Payment Setting</label>
                <div className="flex bg-stone-100 p-1 rounded-xl">
                  <button
                    type="button"
                    onClick={() => setWalkinForm({...walkinForm, payment_status: 'pending'})}
                    className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${walkinForm.payment_status !== 'waived' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    Paid Person
                  </button>
                  <button
                    type="button"
                    onClick={() => setWalkinForm({...walkinForm, payment_status: 'waived'})}
                    className={`flex-1 py-2 text-sm font-medium rounded-lg transition-all ${walkinForm.payment_status === 'waived' ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'}`}
                  >
                    Not Payment (Free)
                  </button>
                </div>
                {walkinForm.payment_status === 'waived' && (
                  <p className="text-xs text-amber-600 mt-2 font-medium bg-amber-50 p-2 rounded-lg border border-amber-100">
                    Reports will be sent immediately upon upload without requiring payment.
                  </p>
                )}
              </div>
              <div className="pt-4 flex justify-end gap-3 border-t border-stone-100">
                <button 
                  type="button" 
                  onClick={() => setIsWalkinOpen(false)}
                  className="px-5 py-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 rounded-xl transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={creatingWalkin}
                  className="flex items-center gap-2 px-5 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-xl shadow-sm shadow-emerald-200 transition-all disabled:opacity-50"
                >
                  {creatingWalkin ? 'Booking...' : <><Save className="w-4 h-4" /> Book Patient</>}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <Toast message={toast.message} type={toast.type} onClose={() => setToast({ message: '', type: 'success' })} />
    </>
  );
}


// Helper Components for clean UI
function MetricCard({ icon, title, value, bg }) {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-stone-200 hover:shadow-md hover:border-sky-100 transition-all group">
      <div className={`w-12 h-12 rounded-xl ${bg} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
        {icon}
      </div>
      <h3 className="text-sm font-medium text-slate-500">{title}</h3>
      <p className="text-3xl font-bold text-slate-800 mt-1">{value}</p>
    </div>
  );
}

function StatusBadge({ status, reportLink, paymentStatus }) {
  let displayStatus = status;
  // If a report is uploaded, but payment isn't paid, and it hasn't been officially dispatched yet
  if (reportLink && paymentStatus !== 'paid' && status !== 'report_delivered') {
    displayStatus = 'report_ready';
  }

  const styles = {
    booked: 'bg-blue-50 text-blue-700 border-blue-200',
    sample_collected: 'bg-amber-50 text-amber-700 border-amber-200',
    report_ready: 'bg-purple-50 text-purple-700 border-purple-200',
    delivered: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    report_delivered: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  };
  const style = styles[displayStatus] || 'bg-stone-100 text-stone-600 border-stone-200';
  let displayText = (displayStatus || 'pending').replace('_', ' ');
  if (displayStatus === 'report_delivered') displayText = 'delivered';
  return (
    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${style} capitalize`}>
      {displayText}
    </span>
  );
}

function PaymentBadge({ paymentStatus, amount }) {
  if (paymentStatus === 'paid' || amount) {
    return (
      <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        Paid {amount ? `(₹${amount})` : ''}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
      Pending
    </span>
  );
}
