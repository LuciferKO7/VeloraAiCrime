import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { App, DISCLAIMER_V1 } from './App';

describe('VELORA Four-Shell Application & Workflow', () => {
  it('renders the mandatory standing disclaimer banner on launch', () => {
    render(<App />);
    const banner = screen.getByRole('banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(DISCLAIMER_V1);
  });

  it('renders the landing page headline by default', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { level: 1, name: /See the connections/i })
    ).toBeInTheDocument();
  });

  it('renders the primary call to action button', () => {
    render(<App />);
    const ctaButtons = screen.getAllByRole('button', { name: /Enter VELORA/i });
    expect(ctaButtons.length).toBeGreaterThan(0);
  });

  it('navigates to Command Center shell when Enter VELORA is clicked', () => {
    render(<App />);
    const ctaButtons = screen.getAllByRole('button', { name: /Enter VELORA/i });
    fireEvent.click(ctaButtons[0]);

    expect(
      screen.getByRole('heading', { level: 1, name: /Command Center/i })
    ).toBeInTheDocument();
  });

  it('can directly mount into cases or studio shell modes', () => {
    render(<App initialView="cases" />);
    expect(
      screen.getByRole('heading', { level: 1, name: /Command Center/i })
    ).toBeInTheDocument();
  });

  it('can mount into Trust Center shell mode', () => {
    render(<App initialView="trust" />);
    expect(
      screen.getByRole('heading', { level: 1, name: /Trust & Governance Center/i })
    ).toBeInTheDocument();
  });
});
