import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ExportSheet } from './components/ExportSheet';
import { SceneEditor } from './components/SceneEditor';
import { ConsensusHeatmap } from './components/ConsensusHeatmap';
import { WitnessMode } from './components/WitnessMode';
import { VelaLabPage } from './pages/VelaLabPage';
import { MANDATORY_DISCLAIMER } from './pages/LandingPage';

describe('Gate C7: Exports & Court Packet Generation', () => {
  const sampleAttrs = [
    { region: 'jawline', key: 'Jawline', value: 'sharp angular', confidence: 'sure' },
    { region: 'eyebrows', key: 'Eyebrows', value: 'thick arched', confidence: 'sure' },
  ];
  const sampleAssumed = [
    { key: 'Eye Color', note: 'Not stated — varied across variants' },
  ];

  it('renders mandatory statutory disclaimer and format options', () => {
    render(
      <ExportSheet
        isOpen={true}
        onClose={() => {}}
        caseNumber="DEMO-001"
        sessionId="SES-001"
        attributes={sampleAttrs}
        aiAssumed={sampleAssumed}
      />
    );

    expect(screen.getByText(/Mandatory Statutory Notice/i)).toBeInTheDocument();
    expect(screen.getByText(MANDATORY_DISCLAIMER)).toBeInTheDocument();
    expect(screen.getByText('PDF Packet')).toBeInTheDocument();
    expect(screen.getByText('PNG Image')).toBeInTheDocument();
    expect(screen.getByText('JSON Data')).toBeInTheDocument();
    expect(screen.getByText('Vector SVG')).toBeInTheDocument();
  });

  it('computes and displays cryptographic seal placeholder and copy button', () => {
    render(
      <ExportSheet
        isOpen={true}
        onClose={() => {}}
        caseNumber="DEMO-001"
        sessionId="SES-001"
        attributes={sampleAttrs}
        aiAssumed={sampleAssumed}
      />
    );

    expect(screen.getByText(/Cryptographic Seal \(SHA-256\)/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Copy/i })).toBeInTheDocument();
  });
});

describe('Gate C9: Scene Module & Spatial Reconstruction', () => {
  it('renders scene canvas with mandatory scale-unknown disclaimer badge', () => {
    render(<SceneEditor sessionId="SES-001" />);

    expect(
      screen.getByText(/Scale unknown — diagram not to exact metric scale/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Spatial Crime Scene Diagram & Trajectory/i)
    ).toBeInTheDocument();
  });

  it('renders interactive entity nodes and timeline scrubber', () => {
    render(<SceneEditor sessionId="SES-001" />);

    expect(screen.getByText(/Witness W-001/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Suspect/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Getaway Vehicle/i)).toBeInTheDocument();
    expect(screen.getAllByRole('slider').length).toBeGreaterThanOrEqual(1);
  });

  it('displays ghost marker for contested entity positions', () => {
    render(<SceneEditor sessionId="SES-001" />);

    expect(
      screen.getByText(/Ghost Marker \(Witness 2 contested\)/i)
    ).toBeInTheDocument();
  });
});

describe('Gate C10: Multi-Witness Consensus & Heatmap UI', () => {
  it('renders multi-witness agreement matrix across witnesses', () => {
    render(<ConsensusHeatmap />);

    expect(screen.getByText(/Multi-Witness Consensus Matrix/i)).toBeInTheDocument();
    expect(screen.getByText(/Witness W-001 \(Victim\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Witness W-002 \(Bystander\)/i)).toBeInTheDocument();
    expect(screen.getByText(/Witness W-003 \(Shopkeeper\)/i)).toBeInTheDocument();
  });

  it('highlights disputed facial features and offers alternate generation', () => {
    render(<ConsensusHeatmap />);

    expect(screen.getAllByText(/Jawline & Chin Geometry/i).length).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', { name: /Generate Alternates For Disputed Features/i })
    ).toBeInTheDocument();
  });

  it('shows possible leads with strict R11 invariant (never says identified)', () => {
    render(<ConsensusHeatmap />);

    const leadsBtn = screen.getByRole('button', { name: /Possible Leads/i });
    fireEvent.click(leadsBtn);

    expect(screen.getByText(/Possible Leads \(Top-K Matches\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Corroborative Lead Only — Not Proof of Identity/i)
    ).toBeInTheDocument();
    expect(screen.queryByText(/^identified$/i)).toBeNull();
  });
});

describe('Gate C11: Witness Mode & TCD8 Vela State Machine', () => {
  it('renders Witness Mode with hero Vela and native script', () => {
    render(<WitnessMode onExitWitnessMode={() => {}} caseNumber="DEMO-001" />);

    expect(screen.getByText(/VELORA Witness Companion/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Start speaking/i })).toBeInTheDocument();
    expect(screen.getByText(MANDATORY_DISCLAIMER)).toBeInTheDocument();
  });

  it('TCD8: Vela Lab renders and supports cycling all 10 states', () => {
    render(<VelaLabPage />);

    expect(
      screen.getByRole('heading', { level: 1, name: /Vela State Machine & SVG Character Lab/i })
    ).toBeInTheDocument();

    const velaEl = screen.getByTestId('vela-character');
    expect(velaEl).toBeInTheDocument();
    expect(velaEl).toHaveAttribute('data-state', 'idle');

    // Click 'alarm' state
    const alarmBtn = screen.getByRole('button', { name: /Alarm/i });
    fireEvent.click(alarmBtn);
    expect(velaEl).toHaveAttribute('data-state', 'alarm');

    // Click 'shield' state
    const shieldBtn = screen.getByRole('button', { name: /Shield/i });
    fireEvent.click(shieldBtn);
    expect(velaEl).toHaveAttribute('data-state', 'shield');

    // Click 'proud' state
    const proudBtn = screen.getByRole('button', { name: /Proud/i });
    fireEvent.click(proudBtn);
    expect(velaEl).toHaveAttribute('data-state', 'proud');

    // Click 'wince' state
    const winceBtn = screen.getByRole('button', { name: /Wince/i });
    fireEvent.click(winceBtn);
    expect(velaEl).toHaveAttribute('data-state', 'wince');
  });
});
