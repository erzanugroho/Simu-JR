import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ProjectProvider } from './context/ProjectContext';
import { SimulationProvider } from './context/SimulationContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import MainLayout from './components/layout/MainLayout';
import DashboardPage from './pages/DashboardPage';
import SimulationPage from './pages/SimulationPage';
import ProjectDetailPage from './pages/ProjectDetailPage';
import SettingsPage from './pages/SettingsPage';

function App() {
  return (
    <ErrorBoundary>
    <ProjectProvider>
      <SimulationProvider>
        <BrowserRouter>
        <Routes>
          <Route path="/" element={
            <MainLayout>
              <DashboardPage />
            </MainLayout>
          } />
          <Route path="/projects" element={
            <MainLayout>
              <DashboardPage view="projects" />
            </MainLayout>
          } />
          <Route path="/simulasi" element={
            <MainLayout>
              <SimulationPage />
            </MainLayout>
          } />
          <Route path="/projects/:id" element={
            <MainLayout>
              <ProjectDetailPage />
            </MainLayout>
          } />
          <Route path="/settings" element={
            <MainLayout>
              <SettingsPage />
            </MainLayout>
          } />
          <Route path="*" element={
            <MainLayout>
              <DashboardPage />
            </MainLayout>
          } />
        </Routes>
      </BrowserRouter>
      </SimulationProvider>
    </ProjectProvider>
    </ErrorBoundary>
  );
}

export default App;
