import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../../App';
import { Badge, ClayButton, Input, Stepper, type StepItem } from '../../components/ui';
import { RubricCard } from '../../components/workspace/RubricCard';
import { useAuthStore } from '../../stores/authStore';

describe('VisionGuard UI, Routing & Rubric Components', () => {
  beforeEach(() => {
    useAuthStore.setState({ theme: 'light', language: 'en', user: null, accessToken: null });
  });

  it('renders Landing page and toggles light/dark theme', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <AppRoutes />
      </MemoryRouter>
    );

    expect(screen.getByText(/Explain science diagrams/i)).toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /Switch to dark theme/i });
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('renders 404 screen on unknown routes', () => {
    render(
      <MemoryRouter initialEntries={['/nonexistent-route']}>
        <AppRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText(/Unmapped Diagram Coordinate/i)).toBeInTheDocument();
  });

  it('renders UI primitives and RubricCard accurately', () => {
    const steps: StepItem[] = [
      { id: '1', label: 'Preprocess', status: 'done' },
      { id: '2', label: 'Visual Audit', status: 'active' },
    ];
    render(
      <div>
        <Badge variant="warning">UNVERIFIED</Badge>
        <ClayButton status="loading">Working</ClayButton>
        <Input label="Email" error="Invalid email format" />
        <Stepper steps={steps} />
        <RubricCard
          rubric={{
            score_out_of_10: 8.5,
            matched_concepts: ['Cell Wall', 'Chloroplast'],
            missing_details: ['Nucleus'],
            misconceptions: [],
            feedback_summary: 'Strong understanding of plant organelles.',
          }}
        />
      </div>
    );

    expect(screen.getByText('UNVERIFIED')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Working/i })).toBeDisabled();
    expect(screen.getByText('Invalid email format')).toBeInTheDocument();
    expect(screen.getByText('8.5')).toBeInTheDocument();
    expect(screen.getByText('Chloroplast')).toBeInTheDocument();
  });
});
