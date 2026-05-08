import React, { useState, useEffect } from 'react';
import { 
  Settings, 
  Globe, 
  Key, 
  Cpu, 
  Save,
  CheckCircle2,
  AlertCircle,
  Database,
  Cloud,
  Layers,
  Users,
  Loader2,
  ChevronDown
} from 'lucide-react';
import { useSettings } from '../hooks/useApi';
import { JUDGE_PERSONA_OPTIONS } from '../types';

const modelPresets = {
  deepseek: [
    { id: 'deepseek-v4-flash', name: 'DeepSeek V4 Flash ($0.0028 hit / $0.14 miss / $0.28 out)' },
    { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro ($0.003625 hit / $0.435 miss / $0.87 out)' }
  ],
  mimo: [
    { id: 'mimo-v2.5-pro', name: 'MiMo V2.5 Pro (Flagship)' },
    { id: 'mimo-v2-pro', name: 'MiMo V2 Pro (Flagship)' },
    { id: 'mimo-v2.5', name: 'MiMo V2.5 (Multimodal)' },
    { id: 'mimo-v2-omni', name: 'MiMo V2 Omni (Multimodal)' },
    { id: 'mimo-v2-flash', name: 'MiMo V2 Flash (Fast & Cheap)' }
  ],
  claude: [
    { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6 (Balanced)' },
    { id: 'claude-haiku-4-5', name: 'Claude Haiku 4.5 (Fastest)' },
    { id: 'claude-3-7-sonnet-20250219', name: 'Claude 3.7 Sonnet (Legacy)' }
  ],
  openrouter: [
    { 
      category: '🟢 Model Gratis', 
      models: [
        { id: 'meta-llama/llama-3.3-70b-instruct:free', name: 'Llama 3.3 70B ($0.00)' },
        { id: 'deepseek/deepseek-r1:free', name: 'DeepSeek R1 ($0.00)' },
        { id: 'qwen/qwen3-coder:free', name: 'Qwen3 Coder ($0.00)' },
        { id: 'mistralai/mistral-small-3.1-24b-instruct:free', name: 'Mistral Small 3.1 ($0.00)' },
        { id: 'google/gemma-3-27b-it:free', name: 'Gemma 3 27B ($0.00)' }
      ] 
    },
    { 
      category: '🔵 Anthropic (Claude)', 
      models: [
        { id: 'anthropic/claude-3-haiku', name: 'Claude 3 Haiku ($0.25/$1.25)' },
        { id: 'anthropic/claude-haiku-4.5', name: 'Claude Haiku 4.5 ($1.00/$5.00)' },
        { id: 'anthropic/claude-3.5-sonnet', name: 'Claude 3.5 Sonnet ($3.00/$15.00)' },
        { id: 'anthropic/claude-3.7-sonnet', name: 'Claude 3.7 Sonnet ($3.00/$15.00)' },
        { id: 'anthropic/claude-sonnet-4.5', name: 'Claude Sonnet 4.5 ($3.00/$15.00)' },
        { id: 'anthropic/claude-sonnet-4.6', name: 'Claude Sonnet 4.6 ($3.00/$15.00)' },
        { id: 'anthropic/claude-opus-4.6', name: 'Claude Opus 4.6 ($5.00/$25.00)' },
        { id: 'anthropic/claude-opus-4.1', name: 'Claude Opus 4.1 ($15.00/$75.00)' }
      ] 
    },
    { 
      category: '🔴 OpenAI (GPT)', 
      models: [
        { id: 'openai/gpt-5-mini', name: 'GPT-5 Mini ($0.25/$2.00)' },
        { id: 'openai/gpt-4.1-mini', name: 'GPT-4.1 Mini ($0.40/$1.60)' },
        { id: 'openai/gpt-4o', name: 'GPT-4o ($2.50/$10.00)' },
        { id: 'openai/gpt-5', name: 'GPT-5 ($1.25/$10.00)' },
        { id: 'openai/o3-mini', name: 'o3-mini ($1.10/$4.40)' },
        { id: 'openai/o1', name: 'o1 ($15.00/$60.00)' },
        { id: 'openai/gpt-4', name: 'GPT-4 ($30.00/$60.00)' }
      ] 
    },
    { 
      category: '🟡 Google (Gemini)', 
      models: [
        { id: 'google/gemini-2.0-flash-001', name: 'Gemini 2.0 Flash ($0.10/$0.40)' },
        { id: 'google/gemini-2.5-flash', name: 'Gemini 2.5 Flash ($0.30/$2.50)' },
        { id: 'google/gemini-2.5-pro', name: 'Gemini 2.5 Pro ($1.25/$10.00)' },
        { id: 'google/gemini-3.1-pro-preview', name: 'Gemini 3.1 Pro ($2.00/$12.00)' }
      ] 
    },
    { 
      category: '🟣 DeepSeek', 
      models: [
        { id: 'deepseek/deepseek-v4-flash', name: 'DeepSeek V4 Flash' },
        { id: 'deepseek/deepseek-v4-pro', name: 'DeepSeek V4 Pro' },
        { id: 'deepseek/deepseek-chat-v3.1', name: 'DeepSeek Chat V3.1 ($0.20/$0.80)' },
        { id: 'deepseek/deepseek-v3.2', name: 'DeepSeek V3.2 ($0.28/$0.40)' },
        { id: 'deepseek/deepseek-r1', name: 'DeepSeek R1 ($0.55/$2.19)' }
      ] 
    },
    { 
      category: '🟠 Qwen (Alibaba)', 
      models: [
        { id: 'qwen/qwen3-235b-a22b-thinking-2507', name: 'Qwen3 Thinking ($0.11/$0.60)' },
        { id: 'qwen/qwen3.5-35b-a3b', name: 'Qwen 3.5 35B ($0.25/$2.00)' },
        { id: 'qwen/qwen3.5-122b-a10b', name: 'Qwen 3.5 122B ($0.40/$2.00)' },
        { id: 'qwen/qwen3-coder-plus', name: 'Qwen3 Coder Plus ($1.00/$5.00)' }
      ] 
    },
    { 
      category: '⚫ Mistral', 
      models: [
        { id: 'mistralai/mistral-small-3.2-24b-instruct', name: 'Mistral Small 3.2 ($0.10/$0.30)' },
        { id: 'mistralai/ministral-8b-2512', name: 'Ministral 8B ($0.15/$0.15)' },
        { id: 'mistralai/mistral-large-2512', name: 'Mistral Large ($0.50/$1.50)' }
      ] 
    },
    { 
      category: '🔷 Lainnya', 
      models: [
        { id: 'openrouter/auto', name: 'Auto Router (Dinamis)' },
        { id: 'x-ai/grok-4', name: 'Grok 4 ($3.00/$15.00)' },
        { id: 'moonshotai/kimi-k2.6', name: 'Kimi K2.6 ($0.60/$3.00)' },
        { id: 'z-ai/glm-5', name: 'GLM 5 ($0.80/$2.56)' },
        { id: 'meta-llama/llama-3-70b-instruct', name: 'Llama 3 70B ($0.59/$0.79)' }
      ] 
    }
  ]
};

const defaultModelByProvider: Record<string, string> = {
  local: 'local-model',
  deepseek: 'deepseek-v4-flash',
  mimo: 'mimo-v2-omni',
  openrouter: 'deepseek/deepseek-v4-flash',
  claude: 'claude-haiku-4-5',
};

const SettingsPage: React.FC = () => {
  const { settings, saveSettings } = useSettings();
  const [localSettings, setLocalSettings] = useState(settings);
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    setLocalSettings(settings);
  }, [settings]);

  const handleSave = async () => {
    await saveSettings(localSettings);
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 3000);
  };

  const providers = [
    { id: 'local', name: 'Local LLM (Ollama/LM Studio)', icon: Database, color: 'text-blue-600', bg: 'bg-blue-50' },
    { id: 'deepseek', name: 'DeepSeek API', icon: Cloud, color: 'text-cyan-600', bg: 'bg-cyan-50' },
    { id: 'mimo', name: 'Xiaomi MiMo API', icon: Cloud, color: 'text-orange-600', bg: 'bg-orange-50' },
    { id: 'openrouter', name: 'OpenRouter', icon: Globe, color: 'text-indigo-600', bg: 'bg-indigo-50' },
    { id: 'claude', name: 'Anthropic Claude', icon: Layers, color: 'text-emerald-600', bg: 'bg-emerald-50' },
  ];

  if (!localSettings) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-12 h-12 text-primary animate-spin opacity-20" />
        <p className="text-sm font-bold text-text-muted animate-pulse uppercase tracking-widest">Memuat Pengaturan...</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl py-8 animate-slide-in">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-3">
            <Settings className="w-8 h-8 text-primary" />
            Konfigurasi Sistem
          </h1>
          <p className="text-text-muted mt-1">Atur koneksi model bahasa dan parameter kecerdasan buatan.</p>
        </div>
        <button 
          onClick={handleSave}
          className="flex items-center gap-2 bg-primary text-white px-6 py-2.5 rounded-xl font-bold shadow-lg shadow-primary/20 hover:bg-primary-light transition-all active:scale-95"
        >
          {isSaved ? <CheckCircle2 className="w-5 h-5" /> : <Save className="w-5 h-5" />}
          {isSaved ? 'Tersimpan' : 'Simpan Perubahan'}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {/* Left Column: Navigation/Tabs */}
        <div className="space-y-2">
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl bg-primary text-white font-bold shadow-md transition-all">
            <Cpu className="w-5 h-5" /> LLM Provider
          </button>
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-text-muted hover:bg-bg-secondary transition-all">
            <Database className="w-5 h-5" /> RAG & Knowledge Base
          </button>
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-text-muted hover:bg-bg-secondary transition-all">
            <Globe className="w-5 h-5" /> Network Settings
          </button>
          <button className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-text-muted hover:bg-bg-secondary transition-all">
            <Users className="w-5 h-5" /> Default Judge Panel
          </button>
        </div>

        {/* Right Column: Content */}
        <div className="md:col-span-2 space-y-6">
          {/* Provider Selection */}
          <div className="bg-white rounded-2xl border border-border shadow-sm p-6">
            <h3 className="text-sm font-black text-text-primary uppercase tracking-widest mb-4">Pilih Provider Utama</h3>
            <div className="grid grid-cols-2 gap-3">
              {providers.map((p) => (
                <button
                  key={p.id}
                  onClick={() => setLocalSettings({
                    ...localSettings,
                    provider: p.id,
                    model: defaultModelByProvider[p.id] || '',
                    customModelId: '',
                  })}
                  className={`flex flex-col items-start p-4 rounded-xl border-2 transition-all ${
                    localSettings.provider === p.id 
                      ? 'border-primary bg-primary/5 shadow-sm' 
                      : 'border-border hover:border-primary/20 bg-transparent'
                  }`}
                >
                  <div className={`p-2 rounded-lg ${p.bg} ${p.color} mb-3`}>
                    <p.icon className="w-5 h-5" />
                  </div>
                  <span className={`text-sm font-bold ${localSettings.provider === p.id ? 'text-primary' : 'text-text-primary'}`}>
                    {p.name}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Connection Details */}
          <div className="bg-white rounded-2xl border border-border shadow-sm p-6 space-y-5">
            <h3 className="text-sm font-black text-text-primary uppercase tracking-widest mb-4">Detail Koneksi</h3>
            
            {localSettings.provider === 'local' && (
              <div className="space-y-4 animate-slide-up">
                <div>
                  <label className="block text-xs font-bold text-text-muted uppercase mb-1.5 ml-1">Base URL</label>
                  <div className="relative">
                    <Globe className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <input 
                      type="text"
                      value={localSettings.llmUrl}
                      onChange={(e) => setLocalSettings({...localSettings, llmUrl: e.target.value})}
                      placeholder="http://127.0.0.1:1234/v1"
                      className="w-full pl-11 pr-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-text-muted uppercase mb-1.5 ml-1">Model Name / ID</label>
                  <div className="relative">
                    <Cpu className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <input 
                      type="text"
                      value={localSettings.model}
                      onChange={(e) => setLocalSettings({...localSettings, model: e.target.value})}
                      placeholder="e.g. gemma-7b-it"
                      className="w-full pl-11 pr-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all"
                    />
                  </div>
                </div>
              </div>
            )}

            {localSettings.provider !== 'local' && (
              <div className="space-y-4 animate-slide-up">
                <div>
                  <label className="block text-xs font-bold text-text-muted uppercase mb-1.5 ml-1">API Key</label>
                  <div className="relative">
                    <Key className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <input 
                      type="password"
                      value={localSettings.apiKey}
                      onChange={(e) => setLocalSettings({...localSettings, apiKey: e.target.value})}
                      placeholder="sk-..."
                      className="w-full pl-11 pr-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all font-mono"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-bold text-text-muted uppercase mb-1.5 ml-1">Pilih Model</label>
                  <div className="relative">
                    <Layers className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
                    <select 
                      value={
                        localSettings.provider === 'openrouter'
                        ? (modelPresets.openrouter.some(g => g.models.some(m => m.id === (localSettings.customModelId || localSettings.model))) ? (localSettings.customModelId || localSettings.model) : 'custom')
                        : (modelPresets[localSettings.provider as keyof typeof modelPresets] as any[])?.some(m => m.id === (localSettings.customModelId || localSettings.model)) ? (localSettings.customModelId || localSettings.model) : 'custom'
                      }
                      onChange={(e) => {
                        if (e.target.value === 'custom') {
                          setLocalSettings({...localSettings, customModelId: localSettings.customModelId || localSettings.model});
                        } else {
                          setLocalSettings({...localSettings, model: e.target.value, customModelId: ''});
                        }
                      }}
                      className="w-full pl-11 pr-10 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all appearance-none cursor-pointer font-bold"
                    >
                      {localSettings.provider === 'openrouter' ? (
                        modelPresets.openrouter.map(group => (
                          <optgroup key={group.category} label={group.category}>
                            {group.models.map(m => (
                              <option key={m.id} value={m.id}>{m.name}</option>
                            ))}
                          </optgroup>
                        ))
                      ) : (
                        (modelPresets[localSettings.provider as keyof typeof modelPresets] as any[])?.map(m => (
                          <option key={m.id} value={m.id}>{m.name}</option>
                        ))
                      )}
                      <option value="custom" className="text-primary font-bold">-- CUSTOM / MANUAL ID --</option>
                    </select>
                    <ChevronDown className="absolute right-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
                  </div>
                </div>

                {(localSettings.provider === 'openrouter' 
                  ? !modelPresets.openrouter.some(g => g.models.some(m => m.id === (localSettings.customModelId || localSettings.model)))
                  : !(modelPresets[localSettings.provider as keyof typeof modelPresets] as any[])?.some(m => m.id === (localSettings.customModelId || localSettings.model))
                || localSettings.customModelId) && (
                  <div className="animate-slide-down">
                    <label className="block text-xs font-bold text-text-muted uppercase mb-1.5 ml-1">Custom Model ID</label>
                    <div className="relative">
                      <Key className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted opacity-50" />
                      <input 
                        type="text"
                        value={localSettings.customModelId || localSettings.model}
                        onChange={(e) => setLocalSettings({...localSettings, customModelId: e.target.value})}
                        placeholder="Masukkan ID model secara manual..."
                        className="w-full pl-11 pr-4 py-3 bg-bg-primary border border-border rounded-xl text-sm focus:border-primary/50 outline-none transition-all font-mono"
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="pt-2 flex items-start gap-3 p-4 bg-amber-50 rounded-xl border border-amber-100">
              <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800 leading-relaxed">
                <strong>Catatan:</strong> Pastikan backend server Anda sudah menyala jika menggunakan model lokal. Perubahan akan segera diterapkan pada sesi simulasi berikutnya.
              </p>
            </div>
          </div>

          {/* Judge Panel Configuration */}
          <div className="bg-white rounded-2xl border border-border shadow-sm p-6 space-y-6">
            <h3 className="text-sm font-black text-text-primary uppercase tracking-widest mb-4">Default Panel Hakim</h3>
            
            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-xs font-bold text-text-muted uppercase mb-2 ml-1">Jumlah Hakim Default</label>
                <div className="flex gap-2">
                  {[3, 5, 7, 9].map(n => (
                    <button 
                      key={n}
                      onClick={() => setLocalSettings({...localSettings, hakimCount: n})}
                      className={`flex-1 py-2 rounded-xl text-sm font-bold border-2 transition-all ${localSettings.hakimCount === n ? 'border-primary bg-primary/5 text-primary' : 'border-border text-text-muted'}`}
                    >
                      {n}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-bold text-text-muted uppercase mb-2 ml-1">Mode Simulasi Default</label>
                <div className="flex gap-2">
                  <button 
                    onClick={() => setLocalSettings({...localSettings, simMode: 'ai'})}
                    className={`flex-1 py-2 rounded-xl text-sm font-bold border-2 transition-all ${localSettings.simMode === 'ai' ? 'border-primary bg-primary/5 text-primary' : 'border-border text-text-muted'}`}
                  >
                    AI vs AI
                  </button>
                  <button 
                    onClick={() => setLocalSettings({...localSettings, simMode: 'human'})}
                    className={`flex-1 py-2 rounded-xl text-sm font-bold border-2 transition-all ${localSettings.simMode === 'human' ? 'border-primary bg-primary/5 text-primary' : 'border-border text-text-muted'}`}
                  >
                    Interaktif
                  </button>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-xs font-bold text-text-muted uppercase mb-3 ml-1">Urutan Persona Default</label>
              <div className="grid grid-cols-3 gap-3">
                {(localSettings.judgePersonas || []).map((persona, idx) => (
                  <div key={idx} className="space-y-1.5">
                    <span className="text-[10px] font-black text-text-muted uppercase ml-1">Posisi {idx + 1}</span>
                    <select 
                      value={persona}
                      onChange={(e) => {
                        const newPersonas = [...localSettings.judgePersonas];
                        newPersonas[idx] = e.target.value;
                        setLocalSettings({...localSettings, judgePersonas: newPersonas});
                      }}
                      className="w-full bg-bg-primary border border-border rounded-xl px-3 py-2 text-xs font-bold text-text-primary outline-none focus:border-primary/50"
                    >
                      {JUDGE_PERSONA_OPTIONS.map(opt => (
                        <option key={opt} value={opt}>{opt.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SettingsPage;
