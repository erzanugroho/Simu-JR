import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  PlayCircle,
  FolderKanban,
  Settings,
  Gavel,
  PanelLeftClose,
  PanelLeftOpen
} from 'lucide-react';

import { useHealthCheck, useSettings, useSimulation } from '../../hooks/useApi';

interface SidebarProps {
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

const Sidebar: React.FC<SidebarProps> = ({ collapsed, onCollapsedChange }) => {
  const { settings } = useSettings();
  const provider = settings.provider || 'local';
  const activeModel =
    settings.customModelId ||
    settings.model ||
    (provider === 'deepseek'
      ? 'deepseek-v4-flash'
      : provider === 'mimo'
        ? 'mimo-v2-omni'
        : 'local-model');
  const activeBaseUrl =
    provider === 'local'
      ? (settings.llmUrl || 'http://127.0.0.1:1234/v1')
      : provider === 'deepseek'
        ? 'https://api.deepseek.com'
        : provider === 'mimo'
          ? 'https://token-plan-sgp.xiaomimimo.com/v1'
          : provider === 'openrouter'
            ? 'https://openrouter.ai/api/v1'
            : undefined;
  const { health } = useHealthCheck(activeBaseUrl);
  const { currentSimulationId, currentProjectId } = useSimulation();
  const llmConnected = health?.llm === 'connected';
  const ragConnected = health?.rag === 'connected';
  const ragVectorCount = new Intl.NumberFormat('id-ID').format(health?.rag_vectors || 0);
  const providerLabel = {
    local: 'Local',
    deepseek: 'DeepSeek',
    mimo: 'MiMo',
    openrouter: 'OpenRouter',
    claude: 'Claude',
  }[provider] || provider;

  const menuItems = [
    { icon: LayoutDashboard, label: 'Dashboard', path: '/', end: true },
    { 
      icon: PlayCircle, 
      label: 'Simulasi Saya', 
      path: currentProjectId ? `/simulasi?project=${currentProjectId}` : '/simulasi',
      isActiveSession: !!currentSimulationId 
    },
    { icon: FolderKanban, label: 'Folder Project', path: '/projects' },
    { icon: Settings, label: 'Pengaturan', path: '/settings' },
  ];

  return (
    <div className={`${collapsed ? 'w-20' : 'w-64'} h-screen bg-primary border-r border-primary-dim flex flex-col fixed left-0 top-0 z-50 transition-all duration-200`}>
      {/* Brand Logo */}
      <div className={`${collapsed ? 'px-4 py-6' : 'p-6'} flex items-center gap-3`}>
        <div className="w-10 h-10 shrink-0 bg-accent flex items-center justify-center rounded-lg shadow-lg">
          <Gavel className="text-primary w-6 h-6" />
        </div>
        {!collapsed && (
        <div className="min-w-0">
          <h1 className="text-white font-serif font-bold text-lg leading-tight">JUDICIAL</h1>
          <p className="text-accent text-[10px] tracking-[0.2em] font-bold uppercase">Simulation</p>
        </div>
        )}
      </div>

      <div className={`${collapsed ? 'px-4' : 'px-4'} mb-2`}>
        <button
          type="button"
          onClick={() => onCollapsedChange(!collapsed)}
          className={`h-10 rounded-xl border border-primary-light/15 bg-primary-dim text-slate-300 transition-all hover:bg-primary-light hover:text-white ${collapsed ? 'w-12' : 'w-full px-3 flex items-center justify-between'}`}
          title={collapsed ? 'Buka sidebar utama' : 'Ciutkan sidebar utama'}
        >
          {collapsed ? (
            <PanelLeftOpen className="mx-auto h-5 w-5" />
          ) : (
            <>
              <span className="text-[10px] font-black uppercase tracking-widest">Menu</span>
              <PanelLeftClose className="h-5 w-5" />
            </>
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 mt-4">
        <div className="space-y-1">
          {menuItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) => `
                flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3 px-4'} py-3 rounded-xl transition-all duration-200 group
                ${isActive
                  ? 'bg-accent text-primary font-bold shadow-md'
                  : 'text-slate-300 hover:bg-primary-light hover:text-white'}
              `}
              title={collapsed ? item.label : undefined}
            >
              {({ isActive }) => (
                <>
                  <div className="relative">
                    <item.icon className={`w-5 h-5 ${isActive ? 'text-primary' : 'text-slate-400 group-hover:text-accent'} transition-colors`} />
                    {item.isActiveSession && (
                      <span className="absolute -top-1 -right-1 w-2.5 h-2.5 bg-accent rounded-full border-2 border-primary animate-pulse shadow-[0_0_8px_rgba(255,191,0,0.5)]"></span>
                    )}
                  </div>
                  {!collapsed && <span className="text-sm">{item.label}</span>}
                  {item.isActiveSession && !collapsed && (
                    <span className="ml-auto text-[9px] font-black bg-accent/20 text-accent px-1.5 py-0.5 rounded uppercase tracking-tighter">Running</span>
                  )}
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Footer Info */}
      <div className={`${collapsed ? 'p-4' : 'p-6'}`}>
        {collapsed ? (
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-primary-light/10 bg-primary-dim py-3">
            <span className={`w-2.5 h-2.5 rounded-full ${llmConnected ? 'bg-dikabulkan animate-pulse' : 'bg-ditolak'}`} title={`LLM: ${llmConnected ? 'Connected' : 'Offline'}`} />
            <span className={`w-2.5 h-2.5 rounded-full ${ragConnected ? 'bg-dikabulkan animate-pulse' : 'bg-ditolak'}`} title={`RAG: ${ragConnected ? 'Connected' : 'Offline'}`} />
          </div>
        ) : (
        <div className="bg-primary-dim rounded-2xl p-4 border border-primary-light/10">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest font-bold mb-3">System Status</p>
          <div className="space-y-3">
            <div className="flex items-start gap-2.5 min-w-0">
              <div className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${llmConnected ? 'bg-dikabulkan animate-pulse' : 'bg-ditolak'}`}></div>
              <div className="min-w-0">
                <p className="text-[11px] text-slate-200 font-semibold leading-tight">
                  LLM: {llmConnected ? 'Connected' : 'Offline'}
                </p>
                <p className="mt-1 text-[10px] text-slate-400 leading-tight truncate" title={`${providerLabel} · ${activeModel}`}>
                  {providerLabel} · {activeModel}
                </p>
              </div>
            </div>
            <div className="flex items-start gap-2.5 min-w-0">
              <div className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${ragConnected ? 'bg-dikabulkan animate-pulse' : 'bg-ditolak'}`}></div>
              <div className="min-w-0">
                <p className="text-[11px] text-slate-200 font-semibold leading-tight">
                  RAG: {ragConnected ? 'Connected' : 'Offline'}
                </p>
                <p className="mt-1 text-[10px] text-slate-400 leading-tight">
                  {ragVectorCount} vectors connected
                </p>
              </div>
            </div>
          </div>
        </div>
        )}
      </div>
    </div>
  );
};

export default Sidebar;
