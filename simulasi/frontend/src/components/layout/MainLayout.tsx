import React, { useState } from 'react';
import Sidebar from './Sidebar';
import TopBar from './TopBar';
import SimulationStatusBar from './SimulationStatusBar';

interface MainLayoutProps {
  children: React.ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  return (
    <div className="flex min-h-screen bg-bg-primary">
      <Sidebar collapsed={sidebarCollapsed} onCollapsedChange={setSidebarCollapsed} />
      <div className={`flex-1 flex flex-col transition-all duration-200 ${sidebarCollapsed ? 'pl-20' : 'pl-64'}`}>
        <div className="sticky top-0 z-50">
          <SimulationStatusBar />
          <TopBar />
        </div>
        <main className="flex-1 p-8">
          {children}
        </main>
      </div>
    </div>
  );
};

export default MainLayout;
