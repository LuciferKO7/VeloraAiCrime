import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { App, DISCLAIMER_V1 } from './App';

describe('App Shell', () => {
  it('renders the application heading', () => {
    render(<App />);
    expect(
      screen.getByRole('heading', { level: 1, name: /AI Witness-to-Face & Scene Platform/i })
    ).toBeInTheDocument();
  });

  it('renders the mandatory standing disclaimer banner', () => {
    render(<App />);
    const banner = screen.getByRole('banner');
    expect(banner).toBeInTheDocument();
    expect(banner).toHaveTextContent(DISCLAIMER_V1);
  });
});
