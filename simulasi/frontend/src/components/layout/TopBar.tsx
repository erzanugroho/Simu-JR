import React from 'react';
import { Search, Bell, UserCircle, HelpCircle } from 'lucide-react';

const TopBar: React.FC = () => {
  return (
    <header className="h-16 bg-white border-b border-border flex items-center justify-between px-8">
      {/* Search Bar */}
      <div className="flex-1 max-w-xl">
        <div className="relative group">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted group-focus-within:text-primary transition-colors" />
          <input 
            type="text" 
            placeholder="Cari simulasi, kasus, atau dokumen hukum..."
            className="w-full bg-bg-secondary border border-transparent focus:bg-white focus:border-primary/20 rounded-full py-2 pl-10 pr-4 text-sm transition-all outline-none"
          />
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-6">
        <button className="text-text-muted hover:text-primary transition-colors relative">
          <Bell className="w-5 h-5" />
          <span className="absolute -top-1 -right-1 w-2 h-2 bg-pemerintah rounded-full border-2 border-white"></span>
        </button>
        <button className="text-text-muted hover:text-primary transition-colors">
          <HelpCircle className="w-5 h-5" />
        </button>
        
        <div className="h-8 w-[1px] bg-border mx-2"></div>

        <div className="flex items-center gap-3 pl-2">
          <div className="text-right hidden sm:block">
            <p className="text-xs font-bold text-text-primary">Admin Judicial</p>
            <p className="text-[10px] text-text-muted font-medium">Chief Analyst</p>
          </div>
          <div className="w-9 h-9 rounded-full bg-bg-secondary border border-border flex items-center justify-center text-primary overflow-hidden">
            <UserCircle className="w-full h-full text-slate-300" />
          </div>
        </div>
      </div>
    </header>
  );
};

export default TopBar;
