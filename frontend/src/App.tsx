import React, { useEffect } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AppShell } from './components/layout/AppShell';
import { LandingPage } from './pages/LandingPage';
import { SignUpPage } from './pages/SignUpPage';
import { SignInPage } from './pages/SignInPage';
import { OnboardingPage } from './pages/OnboardingPage';
import { ForgotPasswordPage, ResetPasswordPage } from './pages/PasswordResetPages';
import { DashboardPage } from './pages/DashboardPage';
import { NewAnalysisPage } from './pages/NewAnalysisPage';
import { AnalysisWorkspacePage } from './pages/AnalysisWorkspacePage';
import { PracticePage } from './pages/PracticePage';
import { TutorialPage } from './pages/TutorialPage';
import { LibraryPage } from './pages/LibraryPage';
import { ProgressPage } from './pages/ProgressPage';
import { SettingsPage } from './pages/SettingsPage';
import { ShareViewPage, TeacherConsolePage } from './pages/TeacherConsolePage';
import { NotFoundPage } from './pages/PlaceholderPages';
import { useAuthStore } from './stores/authStore';
import { tryRefreshAccessToken } from './lib/api';

export const AppRoutes: React.FC = () => (
  <AppShell>
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/signup" element={<SignUpPage />} />
      <Route path="/signin" element={<SignInPage />} />
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/dashboard" element={<DashboardPage />} />
      <Route path="/analyze" element={<NewAnalysisPage />} />
      <Route path="/workspace/:jobId" element={<AnalysisWorkspacePage />} />
      <Route path="/practice/:jobId" element={<PracticePage />} />
      <Route path="/tutorial" element={<TutorialPage />} />
      <Route path="/library" element={<LibraryPage />} />
      <Route path="/progress" element={<ProgressPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/teacher" element={<TeacherConsolePage />} />
      <Route path="/share/:token" element={<ShareViewPage />} />
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  </AppShell>
);

export const App: React.FC = () => {
  const theme = useAuthStore((s) => s.theme);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  // Restore session silently via httpOnly refresh cookie when CSRF cookie exists
  useEffect(() => {
    if (document.cookie.includes('vg_csrf_token=')) {
      tryRefreshAccessToken().catch(() => {});
    }
  }, []);

  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
};

export default App;
