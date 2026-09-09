import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { supabase } from '../lib/supabase';
import Toast from '../components/Toast';
import { 
  ShieldCheck, LayoutDashboard, Building2, Receipt, LogOut, 
  PlusCircle, User, Phone, Mail, Lock, X, Trash2, Key, Users, FileText, Send, Eye, EyeOff, Menu, Edit
} from 'lucide-react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8000'; 

export default function MasterDashboard() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [labs, setLabs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  // New Lab Form
  const [newLab, setNewLab] = useState({ email: '', password: '', business_name: '', exotel_number: '', collector_phone: '', receptionist_phone: '', whatsapp_phone_number_id: '', whatsapp_access_token: '', services: [], financial_password: '' });
  const [creatingLab, setCreatingLab] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showFinPasswordCreate, setShowFinPasswordCreate] = useState(false);
  const [showFinPasswordEdit, setShowFinPasswordEdit] = useState(false);

  // Financial Password Prompt
  const [financialPasswordPrompt, setFinancialPasswordPrompt] = useState({ show: false, lab: null, password: '', showPassword: false });

  // Bill Modal
  const [selectedLab, setSelectedLab] = useState(null);
  const [bills, setBills] = useState([]);
  const [labMetrics, setLabMetrics] = useState(null);
  const [newBill, setNewBill] = useState({ amount: '', description: '', notify_whatsapp: true });
  const [addingBill, setAddingBill] = useState(false);

  // Delete Lab Modal
  const [labToDelete, setLabToDelete] = useState(null);
  const [adminPassword, setAdminPassword] = useState('');
  const [deletingLab, setDeletingLab] = useState(false);

  // Edit Lab Modal
  const [labToEdit, setLabToEdit] = useState(null);
  const [isEditingLab, setIsEditingLab] = useState(false);

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
        fetchLabs(session.access_token);
      }
    });

    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      if (!session) {
        router.push('/login');
      } else {
        setSession(session);
      }
    });

    return () => subscription.unsubscribe();
  }, [router]);

  const fetchLabs = async (token) => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/labs`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        if (res.status === 403) {
          showToast('Access Denied. You are not the Master Admin.', 'error');
          router.push('/dashboard');
          return;
        }
        throw new Error('Failed to fetch labs');
      }
      const data = await res.json();
      setLabs(data.labs || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateLab = async (e) => {
    e.preventDefault();
    setCreatingLab(true);
    try {
      const payload = {
        ...newLab,
        exotel_number: newLab.exotel_number
      };
      const res = await fetch(`${API_BASE}/api/admin/labs`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        // Read the actual error message from the backend
        let errMsg = 'Failed to create lab';
        try {
          const errData = await res.json();
          errMsg = errData.detail || errMsg;
        } catch (_) {}
        throw new Error(errMsg);
      }
      showToast('Lab created successfully!', 'success');
      setNewLab({ email: '', password: '', business_name: '', exotel_number: '', collector_phone: '', receptionist_phone: '', whatsapp_phone_number_id: '', whatsapp_access_token: '', services: [], financial_password: '' });
      fetchLabs(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error creating lab: ${err.message}`, 'error');
    } finally {
      setCreatingLab(false);
    }
  };

  const handleEditLabSubmit = async (e) => {
    e.preventDefault();
    setIsEditingLab(true);
    try {
      const payload = {
        business_name: labToEdit.business_name,
        exotel_number: labToEdit.exotel_number,
        collector_phone: labToEdit.collector_phone,
        receptionist_phone: labToEdit.receptionist_phone,
        whatsapp_phone_number_id: labToEdit.whatsapp_phone_number_id,
        whatsapp_access_token: labToEdit.whatsapp_access_token,
        services: labToEdit.services,
        financial_password: labToEdit.financial_password,
      };
      const res = await fetch(`${API_BASE}/api/admin/labs/${labToEdit.id}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        let errMsg = 'Failed to update lab';
        try {
          const errData = await res.json();
          errMsg = errData.detail || errMsg;
        } catch (_) {}
        throw new Error(errMsg);
      }
      showToast('Lab updated successfully!', 'success');
      setLabToEdit(null);
      fetchLabs(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error updating lab: ${err.message}`, 'error');
    } finally {
      setIsEditingLab(false);
    }
  };

  const handleToggleExtendedStorage = async (labId, newValue) => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/labs/${labId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify({ extended_storage: newValue })
      });
      if (!res.ok) throw new Error('Failed to update extended storage');
      showToast(`Extended storage ${newValue ? 'enabled' : 'disabled'}`, 'success');
      fetchLabs(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error: ${err.message}`, 'error');
    }
  };

  const handleDeleteLab = async (e) => {
    e.preventDefault();
    if (!adminPassword.trim()) return;
    setDeletingLab(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/labs/${labToDelete.id}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify({ password: adminPassword })
      });
      
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Deletion failed');
      }
      
      showToast('Lab and all associated data permanently deleted.', 'success');
      setLabToDelete(null);
      setAdminPassword('');
      fetchLabs(session.access_token);
    } catch (err) {
      console.error(err);
      showToast(`Error deleting lab: ${err.message}`, 'error');
    } finally {
      setDeletingLab(false);
    }
  };

  const openBillsModal = async (lab) => {
    setSelectedLab(lab);
    setBills([]);
    setLabMetrics(null);
    try {
      // Fetch Bills
      const resBills = await fetch(`${API_BASE}/api/admin/labs/${lab.id}/bills`, {
        headers: { Authorization: `Bearer ${session.access_token}` }
      });
      if (resBills.ok) {
        const data = await resBills.json();
        setBills(data.bills || []);
      }
      
      // Fetch Metrics
      const resMetrics = await fetch(`${API_BASE}/api/admin/labs/${lab.id}/metrics`, {
        headers: { Authorization: `Bearer ${session.access_token}` }
      });
      if (resMetrics.ok) {
        const data = await resMetrics.json();
        setLabMetrics(data);
      }

    } catch (err) {
      console.error(err);
      alert('Error fetching lab data');
    }
  };

  const handleAddBill = async (e) => {
    e.preventDefault();
    setAddingBill(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/labs/${selectedLab.id}/bills`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${session.access_token}`
        },
        body: JSON.stringify({
          amount: parseFloat(newBill.amount),
          description: newBill.description,
          notify_whatsapp: newBill.notify_whatsapp
        })
      });
      if (!res.ok) throw new Error('Failed to add bill');
      setNewBill({ amount: '', description: '', notify_whatsapp: true });
      openBillsModal(selectedLab);
    } catch (err) {
      console.error(err);
      showToast(`Error adding bill: ${err.message}`, 'error');
    } finally {
      setAddingBill(false);
    }
  };

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading master console...</div>;
  }

  return (
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
            <h2 className="text-xl font-bold tracking-tight text-slate-900 truncate">LabSaaS</h2>
          </div>
          <button 
            onClick={() => setIsMobileMenuOpen(false)}
            className="md:hidden text-slate-400 hover:text-slate-600"
          >
            <X className="w-6 h-6" />
          </button>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="flex items-center gap-3 px-4 py-3 bg-sky-50 text-sky-700 rounded-xl font-medium transition-colors">
            <Building2 className="w-5 h-5" /> Network Hub
          </a>
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
      <Toast message={toast.message} type={toast.type} onClose={() => setToast({ message: '', type: 'success' })} />
        <header className="bg-white/80 backdrop-blur-md border-b border-stone-200 z-10 px-4 md:px-8 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 flex-shrink-0">
          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button 
              onClick={() => setIsMobileMenuOpen(true)}
              className="md:hidden text-slate-600 hover:text-slate-900 flex-shrink-0"
            >
              <Menu className="w-6 h-6" />
            </button>
            <div className="min-w-0">
              <h1 className="text-xl md:text-2xl font-bold text-slate-900 truncate">Lab Network</h1>
              <p className="text-xs md:text-sm text-slate-500 mt-1 truncate">Manage your multi-tenant SaaS clients.</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 sm:px-4 py-1.5 sm:py-2 bg-emerald-50 rounded-full text-xs sm:text-sm font-medium text-emerald-700 border border-emerald-200 self-start sm:self-auto">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span> SuperAdmin
          </div>
        </header>

        <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-8 flex-1 overflow-y-auto min-w-0 pb-24 md:pb-8">
          
          {/* Create New Lab Form */}
          <div className="bg-white rounded-2xl shadow-sm border border-stone-200 overflow-hidden">
            <div className="p-6 border-b border-stone-100 bg-stone-50/50 flex items-center gap-3">
              <PlusCircle className="w-5 h-5 text-sky-600" />
              <h3 className="text-lg font-semibold text-slate-800">Onboard New Lab</h3>
            </div>
            <form onSubmit={handleCreateLab} className="p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Building2 className="w-4 h-4 text-slate-400" /> Business Name
                </label>
                <input 
                  type="text" 
                  required
                  value={newLab.business_name}
                  onChange={(e) => setNewLab({...newLab, business_name: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="Apollo Labs"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Phone className="w-4 h-4 text-slate-400" /> Business Phone Number
                </label>
                <p className="text-xs text-slate-400 mb-1.5">Your Exotel or WhatsApp Business number</p>
                <input 
                  type="text"
                  value={newLab.exotel_number}
                  onChange={(e) => setNewLab({...newLab, exotel_number: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="09513886363"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Phone className="w-4 h-4 text-amber-500" /> Collector WhatsApp No.
                </label>
                <input 
                  type="text" 
                  required
                  value={newLab.collector_phone}
                  onChange={(e) => setNewLab({...newLab, collector_phone: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="+919876543210"
                />
                <p className="text-xs text-slate-400 mt-1">📦 Receives WhatsApp alerts for every new patient booking.</p>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Phone className="w-4 h-4 text-emerald-500" /> Receptionist WhatsApp No.
                </label>
                <input 
                  type="text" 
                  value={newLab.receptionist_phone}
                  onChange={(e) => setNewLab({...newLab, receptionist_phone: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="+919902283244"
                />
                <p className="text-xs text-slate-400 mt-1">Gets no-WhatsApp alerts & can send UPDATE commands.</p>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Mail className="w-4 h-4 text-slate-400" /> Login Email
                </label>
                <input 
                  type="email" 
                  required
                  value={newLab.email}
                  onChange={(e) => setNewLab({...newLab, email: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="lab@example.com"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Lock className="w-4 h-4 text-slate-400" /> Login Password
                </label>
                <div className="relative">
                  <input 
                    type={showPassword ? "text" : "password"} 
                    required
                    value={newLab.password}
                    onChange={(e) => setNewLab({...newLab, password: e.target.value})}
                    className="w-full bg-stone-50 border border-stone-200 rounded-xl pl-4 pr-10 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                    placeholder="******"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Key className="w-4 h-4 text-emerald-500" /> Meta WhatsApp Phone ID
                </label>
                <input 
                  type="text" 
                  value={newLab.whatsapp_phone_number_id}
                  onChange={(e) => setNewLab({...newLab, whatsapp_phone_number_id: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="e.g. 10123456789"
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Key className="w-4 h-4 text-emerald-500" /> Meta WhatsApp Token
                </label>
                <input 
                  type="password" 
                  value={newLab.whatsapp_access_token}
                  onChange={(e) => setNewLab({...newLab, whatsapp_access_token: e.target.value})}
                  className="w-full bg-stone-50 border border-stone-200 rounded-xl px-4 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                  placeholder="EAAG..."
                />
              </div>

              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-1.5">
                  <Lock className="w-4 h-4 text-slate-400" /> Financial Page Password
                </label>
                <div className="relative">
                  <input 
                    type={showFinPasswordCreate ? "text" : "password"} 
                    value={newLab.financial_password}
                    onChange={(e) => setNewLab({...newLab, financial_password: e.target.value})}
                    className="w-full bg-stone-50 border border-stone-200 rounded-xl pl-4 pr-10 py-2.5 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 transition-all"
                    placeholder="Optional (Locks Billing)"
                  />
                  <button
                    type="button"
                    onClick={() => setShowFinPasswordCreate(!showFinPasswordCreate)}
                    className="absolute right-3 top-3 text-slate-400 hover:text-slate-600"
                  >
                    {showFinPasswordCreate ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              {/* Dynamic Services Section */}
              <div className="md:col-span-2 lg:col-span-3 mt-4">
                <label className="flex items-center gap-2 text-sm font-medium text-slate-600 mb-3">
                  <FileText className="w-4 h-4 text-slate-400" /> Lab Services & Pricing (Optional)
                </label>
                <div className="space-y-3">
                  {newLab.services.map((service, index) => (
                    <div key={index} className="flex flex-wrap sm:flex-nowrap gap-2 sm:gap-4 items-center w-full">
                      <input 
                        type="text" 
                        value={service.name}
                        onChange={(e) => {
                          const updated = [...newLab.services];
                          updated[index].name = e.target.value;
                          setNewLab({...newLab, services: updated});
                        }}
                        placeholder="e.g. Complete Blood Count (CBC)"
                        className="flex-1 min-w-[120px] bg-stone-50 border border-stone-200 rounded-xl px-4 py-2 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                      />
                      <div className="flex gap-2 items-center">
                        <input 
                          type="number" 
                          value={service.price}
                          onChange={(e) => {
                            const updated = [...newLab.services];
                            updated[index].price = e.target.value;
                            setNewLab({...newLab, services: updated});
                          }}
                          placeholder="₹ Price"
                          className="w-24 sm:w-32 bg-stone-50 border border-stone-200 rounded-xl px-4 py-2 text-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                        />
                        <button 
                          type="button"
                          onClick={() => {
                            const updated = newLab.services.filter((_, i) => i !== index);
                            setNewLab({...newLab, services: updated});
                          }}
                          className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  ))}
                  <button 
                    type="button"
                    onClick={() => setNewLab({...newLab, services: [...newLab.services, { name: '', price: '' }]})}
                    className="flex items-center gap-2 text-sm text-sky-600 hover:text-sky-700 font-medium px-2 py-1 rounded-lg hover:bg-sky-50 transition-colors"
                  >
                    <PlusCircle className="w-4 h-4" /> Add Service
                  </button>
                </div>
              </div>
              <div className="md:col-span-2 lg:col-span-3 flex justify-end pt-2">
                <button 
                  type="submit" 
                  disabled={creatingLab}
                  className="px-8 py-3 bg-sky-600 hover:bg-sky-700 shadow-sm shadow-sky-200 rounded-xl text-white font-medium transition-all transform hover:-translate-y-0.5 disabled:opacity-50 disabled:transform-none"
                >
                  {creatingLab ? 'Registering...' : 'Register Lab Tenant'}
                </button>
              </div>
            </form>
          </div>

          {/* Labs List */}
          <div className="bg-white rounded-2xl shadow-sm border border-stone-200 overflow-hidden">
            <div className="p-6 border-b border-stone-100 bg-stone-50/50 flex justify-between items-center">
              <h3 className="text-lg font-semibold text-slate-800 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-slate-400" /> Registered Labs ({labs.length})
              </h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-left">
                <thead className="bg-stone-50 border-b border-stone-200 text-slate-500 text-sm">
                  <tr>
                    <th className="px-6 py-4 font-medium">Business Name</th>
                    <th className="px-6 py-4 font-medium">Contact Number</th>
                    <th className="px-6 py-4 font-medium">Collector Phone</th>
                    <th className="px-6 py-4 font-medium">Registered On</th>
                    <th className="px-6 py-4 font-medium text-center">Extended Storage</th>
                    <th className="px-6 py-4 font-medium text-right sticky right-0 bg-stone-50 z-10 shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)]">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {labs.length === 0 ? (
                    <tr>
                      <td colSpan="6" className="p-8 text-center text-slate-500">No labs registered yet.</td>
                    </tr>
                  ) : (
                    labs.map((lab) => (
                      <tr key={lab.id} className="hover:bg-stone-50/80 transition-colors">
                        <td className="px-6 py-4">
                          <div className="font-semibold text-slate-800">{lab.business_name}</div>
                          <div className="text-xs text-slate-400 mt-1 font-mono">ID: {lab.id}</div>
                        </td>
                        <td className="px-6 py-4 text-slate-600">{lab.exotel_number}</td>
                        <td className="px-6 py-4">
                          {lab.collector_phone ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                              <Phone className="w-3 h-3" />{lab.collector_phone}
                            </span>
                          ) : (
                            <span className="text-xs text-rose-500 font-medium">⚠️ Not set</span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-slate-500">{new Date(lab.created_at).toLocaleDateString()}</td>
                        <td className="px-6 py-4 text-center">
                          <div className="flex flex-col items-center justify-center gap-1">
                            <label className="relative inline-flex items-center cursor-pointer">
                              <input 
                                type="checkbox" 
                                className="sr-only peer" 
                                checked={lab.extended_storage || false}
                                onChange={(e) => handleToggleExtendedStorage(lab.id, e.target.checked)}
                              />
                              <div className="w-9 h-5 bg-stone-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-stone-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-emerald-500"></div>
                            </label>
                            {lab.old_records_count > 0 && (
                              <span className="text-xs text-rose-500 font-medium whitespace-nowrap">
                                {lab.old_records_count} old (₹{lab.extended_storage_fee})
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4 text-right flex items-center justify-end gap-2 sticky right-0 bg-white group-hover:bg-stone-50/80 z-10 shadow-[-4px_0_15px_-3px_rgba(0,0,0,0.05)]">
                          <button 
                            onClick={() => {
                              // Always prompt for a password; the backend will check it against financial_password or login password.
                              setFinancialPasswordPrompt({ show: true, lab: lab, password: '', showPassword: false, loading: false });
                            }}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 sm:px-4 sm:py-2 bg-stone-100 hover:bg-stone-200 border border-stone-200 rounded-lg text-xs sm:text-sm text-slate-700 font-medium transition-colors"
                          >
                            <Receipt className="w-3 h-3 sm:w-4 sm:h-4 text-slate-500" /> <span className="hidden sm:inline">Manage & Bill</span>
                          </button>
                          <button 
                            onClick={() => setLabToEdit(lab)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 sm:px-4 sm:py-2 bg-sky-50 hover:bg-sky-100 border border-sky-200 rounded-lg text-xs sm:text-sm text-sky-700 font-medium transition-colors"
                          >
                            <span className="hidden sm:inline">Edit</span><Edit className="w-3 h-3 sm:hidden" />
                          </button>
                          <button 
                            onClick={() => setLabToDelete(lab)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 sm:px-4 sm:py-2 bg-rose-50 hover:bg-rose-100 border border-rose-200 rounded-lg text-xs sm:text-sm text-rose-700 font-medium transition-colors"
                          >
                            <span className="hidden sm:inline">Delete</span><Trash2 className="w-3 h-3 sm:hidden" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
          
          {/* Footer */}
          <div className="mt-8 text-center text-sm text-slate-500 pb-4">
            Developed by Viresh <br className="sm:hidden" />
            <span className="hidden sm:inline"> | </span> 
            Contact: 6362268616
          </div>

        </div>
      </main>

      {/* Bill Management & Analytics Modal */}
      {selectedLab && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-200">
          <div className="bg-white border border-stone-200 rounded-2xl w-full max-w-3xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in slide-in-from-bottom-4 duration-300">
            
            <div className="p-6 border-b border-stone-100 bg-stone-50/50 flex justify-between items-center">
              <div>
                <h3 className="text-xl font-bold text-slate-800 flex items-center gap-2">
                  <Building2 className="w-6 h-6 text-sky-600" /> {selectedLab.business_name}
                </h3>
                <p className="text-sm text-slate-500 mt-1">Analytics & Billing Center</p>
              </div>
              <button onClick={() => setSelectedLab(null)} className="p-2 hover:bg-stone-200 rounded-full transition-colors text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1 bg-stone-50/30 space-y-6">
              
              {/* Lab Usage Analytics */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-sm">
                  <div className="flex items-center gap-2 text-slate-500 mb-2">
                    <Users className="w-4 h-4 text-blue-500" /> <span className="text-sm font-medium">Total Patients</span>
                  </div>
                  <div className="text-2xl font-bold text-slate-800">{labMetrics ? labMetrics.total_patients : '...'}</div>
                </div>
                <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-sm">
                  <div className="flex items-center gap-2 text-slate-500 mb-2">
                    <Receipt className="w-4 h-4 text-emerald-500" /> <span className="text-sm font-medium">Total Revenue</span>
                  </div>
                  <div className="text-2xl font-bold text-slate-800">{labMetrics ? `₹${labMetrics.total_revenue}` : '...'}</div>
                </div>
                <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-sm">
                  <div className="flex items-center gap-2 text-slate-500 mb-2">
                    <FileText className="w-4 h-4 text-amber-500" /> <span className="text-sm font-medium">Reports Hosted</span>
                  </div>
                  <div className="text-2xl font-bold text-slate-800">{labMetrics ? labMetrics.total_reports : '...'}</div>
                  <div className="text-xs text-slate-400 mt-1">Proxy for storage usage</div>
                </div>
              </div>

              {/* Add Bill Form */}
              <div className="bg-white p-5 rounded-xl border border-stone-200 shadow-sm">
                <h4 className="text-sm font-semibold text-slate-700 mb-4 flex items-center gap-2">
                  <PlusCircle className="w-4 h-4 text-sky-500" /> Issue New Bill
                </h4>
                <form onSubmit={handleAddBill} className="flex flex-col gap-4">
                  <div className="flex flex-col sm:flex-row gap-4 items-end">
                    <div className="flex-1 w-full">
                      <label className="block text-xs font-medium text-slate-500 mb-1">Amount (₹)</label>
                      <input 
                        type="number" 
                        required
                        min="0"
                        step="0.01"
                        value={newBill.amount}
                        onChange={(e) => setNewBill({...newBill, amount: e.target.value})}
                        className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                        placeholder="5000"
                      />
                    </div>
                    <div className="flex-[2] w-full">
                      <label className="block text-xs font-medium text-slate-500 mb-1">Description</label>
                      <input 
                        type="text" 
                        required
                        value={newBill.description}
                        onChange={(e) => setNewBill({...newBill, description: e.target.value})}
                        className="w-full bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                        placeholder="Monthly SaaS Fee + Storage"
                      />
                    </div>
                    <button 
                      type="submit" 
                      disabled={addingBill}
                      className="w-full sm:w-auto px-5 py-2 bg-sky-600 hover:bg-sky-700 disabled:opacity-50 rounded-lg text-white font-medium transition-colors"
                    >
                      {addingBill ? 'Sending...' : 'Issue Bill'}
                    </button>
                  </div>
                  
                  {/* WhatsApp Notify Toggle */}
                  <div className="flex items-center gap-2 mt-2">
                    <input 
                      type="checkbox" 
                      id="notify-whatsapp"
                      checked={newBill.notify_whatsapp}
                      onChange={(e) => setNewBill({...newBill, notify_whatsapp: e.target.checked})}
                      className="w-4 h-4 text-sky-600 bg-stone-50 border-stone-300 rounded focus:ring-sky-500"
                    />
                    <label htmlFor="notify-whatsapp" className="text-sm font-medium text-slate-600 flex items-center gap-1.5">
                      <Send className="w-3.5 h-3.5 text-emerald-500" /> Send invoice via WhatsApp to Lab Owner
                    </label>
                  </div>
                </form>
              </div>

              {/* Bill History */}
              <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Billing History</h4>
              <div className="space-y-3">
                {bills.length === 0 ? (
                  <div className="text-center py-8 bg-white border border-stone-200 border-dashed rounded-xl">
                    <Receipt className="w-8 h-8 text-stone-300 mx-auto mb-2" />
                    <p className="text-slate-500 text-sm">No bills issued yet.</p>
                  </div>
                ) : (
                  bills.map(bill => (
                    <div key={bill.id} className="flex justify-between items-center p-4 bg-white rounded-xl border border-stone-200 shadow-sm hover:border-sky-200 transition-colors">
                      <div>
                        <div className="font-semibold text-slate-800">{bill.description}</div>
                        <div className="text-xs text-slate-500 mt-1">{new Date(bill.created_at).toLocaleDateString()}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-bold text-emerald-600 text-lg">₹{bill.amount}</div>
                        <div className="inline-block px-2 py-0.5 mt-1 rounded text-[10px] font-bold uppercase tracking-wide bg-stone-100 text-stone-500 border border-stone-200">
                          {bill.status}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Delete Lab Password Verification Modal */}
      {labToDelete && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60] animate-in fade-in duration-200">
          <div className="bg-white border border-rose-200 rounded-2xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 text-center">
              <div className="mx-auto w-12 h-12 bg-rose-100 text-rose-600 rounded-full flex items-center justify-center mb-4">
                <Trash2 className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Delete {labToDelete.business_name}?</h3>
              <p className="text-sm text-slate-500 mb-6">
                This action is irreversible. All patients, bookings, reports, and bills associated with this lab will be permanently destroyed.
              </p>
              
              <form onSubmit={handleDeleteLab} className="text-left space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Verify SuperAdmin Password</label>
                  <div className="relative">
                    <Key className="w-5 h-5 text-slate-400 absolute left-3 top-2.5" />
                    <input 
                      type="password"
                      required
                      value={adminPassword}
                      onChange={(e) => setAdminPassword(e.target.value)}
                      placeholder="Enter your password"
                      className="w-full pl-10 pr-4 py-2 bg-stone-50 border border-rose-200 rounded-xl focus:ring-2 focus:ring-rose-500/50 focus:border-rose-500 outline-none transition-all"
                    />
                  </div>
                </div>
                
                <div className="flex gap-3 pt-2">
                  <button 
                    type="button"
                    onClick={() => { setLabToDelete(null); setAdminPassword(''); }}
                    className="flex-1 py-2.5 bg-stone-100 hover:bg-stone-200 text-slate-700 font-medium rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit"
                    disabled={deletingLab}
                    className="flex-1 py-2.5 bg-rose-600 hover:bg-rose-700 text-white font-medium rounded-xl transition-colors shadow-sm shadow-rose-200 disabled:opacity-50"
                  >
                    {deletingLab ? 'Deleting...' : 'Wipe Data'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Edit Lab Modal */}
      {labToEdit && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60] animate-in fade-in duration-200">
          <div className="bg-white border border-stone-200 rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 border-b border-stone-100 bg-stone-50/50 flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-800 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-sky-600" /> Edit Lab: {labToEdit.business_name}
              </h3>
              <button onClick={() => setLabToEdit(null)} className="p-2 hover:bg-stone-200 rounded-full transition-colors text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto">
              <form onSubmit={handleEditLabSubmit} className="space-y-4">
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Business Name</label>
                    <input 
                      type="text"
                      required
                      value={labToEdit.business_name || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, business_name: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Business Phone Number</label>
                    <input 
                      type="text"
                      required
                      value={labToEdit.exotel_number || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, exotel_number: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Collector Phone</label>
                    <input 
                      type="text"
                      value={labToEdit.collector_phone || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, collector_phone: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Receptionist Phone</label>
                    <input 
                      type="text"
                      value={labToEdit.receptionist_phone || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, receptionist_phone: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-slate-700 mb-1">Meta WhatsApp Phone ID</label>
                    <input 
                      type="text"
                      value={labToEdit.whatsapp_phone_number_id || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, whatsapp_phone_number_id: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-slate-700 mb-1">Meta WhatsApp Access Token</label>
                    <input 
                      type="password"
                      value={labToEdit.whatsapp_access_token || ''}
                      onChange={(e) => setLabToEdit({...labToEdit, whatsapp_access_token: e.target.value})}
                      className="w-full px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                      placeholder="Leave blank to keep unchanged (if already set)"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-sm font-medium text-slate-700 mb-1">Financial Page Password</label>
                    <div className="relative">
                      <input 
                        type={showFinPasswordEdit ? "text" : "password"}
                        value={labToEdit.financial_password || ''}
                        onChange={(e) => setLabToEdit({...labToEdit, financial_password: e.target.value})}
                        className="w-full pl-3 pr-10 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 outline-none"
                        placeholder="Leave blank to keep unchanged (if already set)"
                      />
                      <button
                        type="button"
                        onClick={() => setShowFinPasswordEdit(!showFinPasswordEdit)}
                        className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                      >
                        {showFinPasswordEdit ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Dynamic Services Section (Edit Mode) */}
                <div className="mt-4">
                  <label className="flex items-center gap-2 text-sm font-medium text-slate-700 mb-3">
                    <FileText className="w-4 h-4 text-slate-400" /> Lab Services & Pricing (Optional)
                  </label>
                  <div className="space-y-3">
                    {(labToEdit.services || []).map((service, index) => (
                      <div key={index} className="flex flex-wrap sm:flex-nowrap gap-2 sm:gap-4 items-center w-full">
                        <input 
                          type="text" 
                          value={service.name}
                          onChange={(e) => {
                            const currentServices = labToEdit.services || [];
                            const updated = [...currentServices];
                            updated[index].name = e.target.value;
                            setLabToEdit({...labToEdit, services: updated});
                          }}
                          placeholder="e.g. Complete Blood Count (CBC)"
                          className="flex-1 min-w-[120px] px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                        />
                        <div className="flex gap-2 items-center">
                          <input 
                            type="number" 
                            value={service.price}
                            onChange={(e) => {
                              const currentServices = labToEdit.services || [];
                              const updated = [...currentServices];
                              updated[index].price = e.target.value;
                              setLabToEdit({...labToEdit, services: updated});
                            }}
                            placeholder="₹ Price"
                            className="w-24 sm:w-32 px-3 py-2 bg-stone-50 border border-stone-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-sky-500/50"
                          />
                          <button 
                            type="button"
                            onClick={() => {
                              const currentServices = labToEdit.services || [];
                              const updated = currentServices.filter((_, i) => i !== index);
                              setLabToEdit({...labToEdit, services: updated});
                            }}
                            className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors shrink-0"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    ))}
                    <button 
                      type="button"
                      onClick={() => {
                        const currentServices = labToEdit.services || [];
                        setLabToEdit({...labToEdit, services: [...currentServices, { name: '', price: '' }]})
                      }}
                      className="flex items-center gap-2 text-sm text-sky-600 hover:text-sky-700 font-medium px-2 py-1 rounded-lg hover:bg-sky-50 transition-colors"
                    >
                      <PlusCircle className="w-4 h-4" /> Add Service
                    </button>
                  </div>
                </div>

                <div className="flex justify-end gap-3 pt-4 border-t border-stone-100">
                  <button 
                    type="button"
                    onClick={() => setLabToEdit(null)}
                    className="px-4 py-2 bg-stone-100 hover:bg-stone-200 text-slate-700 font-medium rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit"
                    disabled={isEditingLab}
                    className="px-6 py-2 bg-sky-600 hover:bg-sky-700 text-white font-medium rounded-xl transition-colors shadow-sm disabled:opacity-50"
                  >
                    {isEditingLab ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Financial Password Prompt Modal */}
      {financialPasswordPrompt.show && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4 z-[60] animate-in fade-in duration-200">
          <div className="bg-white border border-stone-200 rounded-2xl w-full max-w-sm flex flex-col shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200">
            <div className="p-6 text-center">
              <div className="mx-auto w-12 h-12 bg-sky-100 text-sky-600 rounded-full flex items-center justify-center mb-4">
                <Lock className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-slate-900 mb-2">Unlock Financial Page</h3>
              <p className="text-sm text-slate-500 mb-6">
                Enter the financial password to access billing for {financialPasswordPrompt.lab?.business_name}.
              </p>
              
              <form onSubmit={async (e) => {
                e.preventDefault();
                setFinancialPasswordPrompt(prev => ({...prev, loading: true}));
                try {
                  const res = await fetch(`${API_BASE}/api/admin/labs/${financialPasswordPrompt.lab.id}/verify-financial-password`, {
                    method: 'POST',
                    headers: {
                      'Content-Type': 'application/json',
                      'Authorization': `Bearer ${session.access_token}`
                    },
                    body: JSON.stringify({ password: financialPasswordPrompt.password })
                  });
                  if (res.ok) {
                    setFinancialPasswordPrompt({ show: false, lab: null, password: '', showPassword: false, loading: false });
                    openBillsModal(financialPasswordPrompt.lab);
                  } else {
                    const data = await res.json();
                    showToast(data.detail || 'Incorrect financial password', 'error');
                  }
                } catch (err) {
                  showToast('Error verifying password', 'error');
                } finally {
                  setFinancialPasswordPrompt(prev => ({...prev, loading: false}));
                }
              }} className="text-left space-y-4">
                <div>
                  <div className="relative">
                    <Key className="w-5 h-5 text-slate-400 absolute left-3 top-2.5" />
                    <input 
                      type={financialPasswordPrompt.showPassword ? "text" : "password"}
                      required
                      disabled={financialPasswordPrompt.loading}
                      value={financialPasswordPrompt.password}
                      onChange={(e) => setFinancialPasswordPrompt({...financialPasswordPrompt, password: e.target.value})}
                      placeholder="Enter financial password"
                      className="w-full pl-10 pr-10 py-2 bg-stone-50 border border-stone-200 rounded-xl focus:ring-2 focus:ring-sky-500/50 focus:border-sky-500 outline-none transition-all disabled:opacity-50"
                    />
                    <button
                      type="button"
                      onClick={() => setFinancialPasswordPrompt({...financialPasswordPrompt, showPassword: !financialPasswordPrompt.showPassword})}
                      className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {financialPasswordPrompt.showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                </div>
                
                <div className="flex gap-3 pt-2">
                  <button 
                    type="button"
                    onClick={() => setFinancialPasswordPrompt({ show: false, lab: null, password: '', showPassword: false })}
                    className="flex-1 py-2.5 bg-stone-100 hover:bg-stone-200 text-slate-700 font-medium rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button 
                    type="submit"
                    disabled={financialPasswordPrompt.loading}
                    className="flex-1 py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-medium rounded-xl transition-colors shadow-sm shadow-sky-200 disabled:opacity-50"
                  >
                    {financialPasswordPrompt.loading ? 'Verifying...' : 'Unlock'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
