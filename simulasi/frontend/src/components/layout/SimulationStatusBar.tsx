import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, Activity, Gavel, X, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useSimulation } from '../../hooks/useApi';

const SimulationStatusBar: React.FC = () => {
  const { isRunning, progress, currentSimulationId, currentProjectId, error, stopSimulation, syncSimulation } = useSimulation();
  const navigate = useNavigate();
  const location = useLocation();

  const isDone = progress?.status === 'done' || progress?.phase === 'done' || progress?.phase === 'Selesai';

  // Show only for an active/interrupted session. A finished simulation should not
  // keep a global banner alive on unrelated pages.
  if (!currentSimulationId || isDone) return null;
  if (!isRunning && !error && !progress) return null;

  // Don't show if we are already on the simulation page
  if (location.pathname === '/simulasi') return null;

  const handleReturn = () => {
    const path = currentProjectId ? `/simulasi?project=${currentProjectId}` : '/simulasi';
    navigate(path);
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    // We don't necessarily want to STOP the simulation, just clear the local ID so the bar hides
    // But usually, dismissing the "active session" bar means the user is done with it.
    // Let's just use stopSimulation to be safe, or just clear the ID if we want it to keep running.
    // For now, let's just clear the session if it's done, otherwise just hide it.
    stopSimulation();
  };

  return (
    <div className="animate-in slide-in-from-top duration-500">
      <div className={`
        ${isDone ? 'bg-dikabulkan/90' : error ? 'bg-ditolak/90' : 'bg-primary/95'}
        backdrop-blur-md border-b border-white/10 px-4 py-2.5 shadow-[0_4px_20px_rgba(0,0,0,0.15)] overflow-hidden relative transition-colors duration-500
      `}>
        {/* Animated Background Glow */}
        <div className="absolute top-0 left-1/4 w-1/2 h-full bg-white/5 blur-[40px] pointer-events-none"></div>
        
        <div className="max-w-7xl mx-auto flex items-center justify-between relative z-10">
          <div className="flex items-center gap-4">
            <div className={`
              flex items-center justify-center w-8 h-8 rounded-lg border 
              ${isDone ? 'bg-white/20 border-white/30' : 'bg-accent/10 border-accent/20'}
            `}>
              {isDone ? (
                <CheckCircle2 className="w-4 h-4 text-white" />
              ) : error ? (
                <AlertCircle className="w-4 h-4 text-white" />
              ) : (
                <Gavel className="w-4 h-4 text-accent" />
              )}
            </div>
            
            <div className="flex flex-col">
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-black uppercase tracking-[0.2em] ${isDone ? 'text-white' : 'text-accent/80'}`}>
                  {isDone ? 'Hasil Tersedia' : 'Status Sidang'}
                </span>
                {isRunning && (
                  <span className="flex h-1.5 w-1.5 rounded-full bg-dikabulkan animate-pulse shadow-[0_0_8px_rgba(21,128,61,0.8)]"></span>
                )}
              </div>
              <p className="text-sm font-serif font-bold text-white leading-tight">
                {error ? 'Gagal Terhubung' : isDone ? 'Simulasi Selesai' : isRunning ? (progress?.phase || 'Sedang Berlangsung...') : 'Simulasi Terjeda'} 
                <span className="text-white/40 font-sans font-medium mx-2">—</span>
                <span className="text-slate-200 text-xs font-sans font-medium italic">
                  {error || progress?.step || 'Menunggu pemrosesan argumen...'}
                </span>
              </p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {!isRunning && !isDone && (
              <button 
                onClick={() => syncSimulation(currentSimulationId!)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[10px] font-bold bg-accent/20 hover:bg-accent/30 text-accent transition-all border border-accent/30"
              >
                <Activity className="w-3 h-3 animate-pulse" />
                {error ? 'COBA LAGI' : 'HUBUNGKAN KEMBALI'}
              </button>
            )}
            
            <button 
              onClick={handleReturn}
              className={`
                group flex items-center gap-2.5 px-4 py-1.5 rounded-full text-xs font-black transition-all duration-300 shadow-lg active:scale-95
                ${isDone ? 'bg-white text-dikabulkan hover:bg-slate-100' : 'bg-accent text-primary hover:bg-accent-light shadow-accent/20'}
              `}
            >
              {isDone ? 'LIHAT HASIL' : 'KEMBALI KE RUANG SIDANG'}
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform duration-300" />
            </button>
            
            <button 
              onClick={handleDismiss}
              className="p-1.5 hover:bg-white/10 rounded-full text-white/60 hover:text-white transition-colors"
              title="Tutup Status Bar"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Progress Bar Animation */}
        <div className="absolute bottom-0 left-0 h-[2px] bg-white/10 w-full">
          {isRunning && (
            <div className="h-full bg-accent shadow-[0_0_10px_rgba(212,175,55,0.5)] animate-progress-indeterminate w-1/3"></div>
          )}
          {isDone && (
            <div className="h-full bg-white w-full"></div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SimulationStatusBar;
