/**
 * Centralized Demo Dataset for VELORA Emergency Hackathon Demonstration
 * Case: DEMO-2026-041
 * Subject: Vehicle incident — reconstructed witness account
 *
 * All records here are strictly FICTIONAL DEMONSTRATION DATA.
 * NOT A REAL INCIDENT — NOT REAL EVIDENCE — INVESTIGATIVE AID ONLY.
 */

import type { CaseItem } from '../pages/CommandCenterPage';
import type { SceneEntity } from '../components/SceneEditor';

export const DEMO_CASE_METADATA: CaseItem = {
  id: 'case-demo-2026-041',
  case_number: 'DEMO-2026-041',
  title: 'Vehicle incident — reconstructed witness account',
  station: 'Metropolitan Forensic Hub — Central Precinct',
  status: 'active',
  data_mode: 'demo',
  default_appearance_group: 'unspecified',
  updated_at: new Date().toISOString(),
};

export const DEMO_WITNESS_STATEMENTS = [
  {
    id: 'wit-01',
    alias: 'Witness W-001 (Store Clerk)',
    role: 'Primary Eyewitness',
    language: 'Tamil (தமிழ்) & English',
    audioSeconds: 42,
    rawText: 'அவர் சுமார் 28 முதல் 32 வயது, கூர்மையான தாடை அமைப்பு, அடர்ந்த வளைந்த புருவங்கள் மற்றும் இருண்ட ஜாக்கெட் அணிந்திருந்தார். இருண்ட நான்கு கதவு செடான் காரில் ஏறி கிழக்கே சென்றார்.',
    englishTranslation: 'He appeared between 28 and 32 years of age, sharp angular jawline, prominent thick arched eyebrows, dark jacket. He entered a dark four-door sedan and departed eastward.',
    confidence: 'High visual clarity at storefront entrance',
  },
  {
    id: 'wit-02',
    alias: 'Witness W-002 (Pedestrian Bystander)',
    role: 'Corroborating Eyewitness',
    language: 'English',
    audioSeconds: 36,
    rawText: 'I saw him walk briskly past the storefront towards the curb. Sharp square jawline, heavy eyebrows, dark short hair. A dark four-door sedan was idling with lights on.',
    englishTranslation: 'I saw him walk briskly past the storefront towards the curb. Sharp square jawline, heavy eyebrows, dark short hair. A dark four-door sedan was idling with lights on.',
    confidence: 'Observed profile view from 15 meters across crosswalk',
  },
  {
    id: 'wit-03',
    alias: 'Witness W-003 (Adjoining Shopkeeper)',
    role: 'Contextual Witness',
    language: 'Hindi (हिन्दी) & English',
    audioSeconds: 31,
    rawText: 'स्टोर के बाहर एक व्यक्ति दिखा। जबड़ा कुछ गोल लगा या टोपी के कारण छाया थी। उसने गहरी जैकेट पहनी थी और काली सेडान में बैठा।',
    englishTranslation: 'Saw an individual outside the store. Jawline appeared somewhat rounded or shadowed under a dark cap/hood. Wore dark clothing and entered a dark sedan.',
    confidence: 'Partial view from doorway; noted discrepancy regarding headwear',
  },
];

export const DEMO_FACIAL_ATTRIBUTES = [
  { region: 'face_shape', key: 'Jawline & Chin', value: 'Sharp angular contour', confidence: 'sure' as const, locked: true },
  { region: 'eyebrows', key: 'Eyebrows', value: 'Thick dark arched', confidence: 'sure' as const, locked: true },
  { region: 'eyes', key: 'Orbit & Eye Shape', value: 'Deep-set almond', confidence: 'somewhat' as const, locked: false },
  { region: 'age', key: 'Estimated Age', value: '28–32 years band', confidence: 'sure' as const, locked: false },
  { region: 'hair', key: 'Hair / Coverage', value: 'Short dark cropped (disputed cap by W-003)', confidence: 'somewhat' as const, locked: false },
  { region: 'nose', key: 'Nose Bridge', value: 'Straight narrow bridge', confidence: 'somewhat' as const, locked: false },
];

export const DEMO_AI_ASSUMED_UNSTATED = [
  { key: 'Eye Iris Color', note: 'Unstated by witnesses — rendered across regional dark hazel / dark brown gradient' },
  { key: 'Skin Tone / Melanin', note: 'Unstated — sampled within regional demographic baseline without subjective bias' },
  { key: 'Ear Lobe Morphology', note: 'Partially obscured by hair/shadow — neutralized to standard bilateral anatomical average' },
];

export const DEMO_RECOGNITION_VARIANTS = [
  {
    id: 'v1',
    title: 'Primary Composite (Frontal)',
    view: 'frontal',
    axes: 'sharp angular jaw · thick arched brows · neutral short hair',
    score: 0.92,
    picked: true,
  },
  {
    id: 'v2',
    title: 'Profile Composite (Right Lateral)',
    view: 'profile',
    axes: 'prominent brow ridge · straight bridge · defined jaw angle',
    score: 0.88,
    picked: false,
  },
  {
    id: 'v3',
    title: 'Alternate Jaw Variant (W-003 Contested)',
    view: 'frontal',
    axes: 'moderate rounded jaw · softened chin projection',
    score: 0.79,
    picked: false,
  },
  {
    id: 'v4',
    title: 'Headwear / Cap Variant',
    view: 'three-quarter',
    axes: 'dark low-profile cap · upper forehead shadowed',
    score: 0.81,
    picked: false,
  },
  {
    id: 'v5',
    title: 'Three-Quarter View (Left Oblique)',
    view: 'three-quarter',
    axes: 'deep-set orbits · slight asymmetry in jawline angle',
    score: 0.85,
    picked: false,
  },
  {
    id: 'v6',
    title: 'Speculative Maturity Adjustment (+5 Years)',
    view: 'frontal',
    axes: 'subtle nasolabial deepening · mature jaw contour',
    score: 0.74,
    picked: false,
  },
];

export const DEMO_SCENE_ENTITIES: SceneEntity[] = [
  {
    id: 'ent-storefront',
    kind: 'landmark',
    label: 'Storefront Entrance & Counter',
    x: 0.28,
    y: 0.24,
    heading_deg: 180,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-w1',
    kind: 'person',
    label: 'Witness W-001 (Viewing Angle)',
    x: 0.34,
    y: 0.32,
    heading_deg: 135,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-w2',
    kind: 'person',
    label: 'Witness W-002 (Crosswalk)',
    x: 0.20,
    y: 0.68,
    heading_deg: 45,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-w3',
    kind: 'person',
    label: 'Witness W-003 (Adjoining Door)',
    x: 0.46,
    y: 0.22,
    heading_deg: 200,
    confidence: 'somewhat',
    is_conflicted: false,
  },
  {
    id: 'ent-suspect',
    kind: 'person',
    label: 'Person of Interest (Pedestrian Path)',
    x: 0.42,
    y: 0.46,
    heading_deg: 110,
    confidence: 'sure',
    is_conflicted: false,
  },
  {
    id: 'ent-sedan',
    kind: 'vehicle',
    label: 'Dark 4-Door Sedan (Target Vehicle)',
    x: 0.72,
    y: 0.54,
    heading_deg: 90,
    confidence: 'sure',
    is_conflicted: true,
    conflict_ghost: { x: 0.82, y: 0.62 },
  },
];

/**
 * 9-Panel Narrative Storyboard Composition
 * Fictional Scene Reconstruction per §3 specifications
 */
export const DEMO_STORYBOARD_PANELS = [
  {
    step: 1,
    title: '1. Establishing Storefront View',
    subtitle: 'Commercial entryway & pedestrian sidewalk at curb',
    camera: 'Wide Angle (West Looking East)',
    timeLabel: 'T+00:00 (Baseline)',
    description: 'Initial scene view showing commercial storefront entrance, sidewalk line, and stationary environment prior to incident.',
  },
  {
    step: 2,
    title: '2. Vehicle Approach',
    subtitle: 'Dark four-door sedan decelerating near storefront',
    camera: 'Street-Level Perspective',
    timeLabel: 'T+00:15',
    description: 'Dark four-door sedan approaches westbound lane at low speed (~20 km/h) with daytime running lights on.',
  },
  {
    step: 3,
    title: '3. Sedan Lateral Profile',
    subtitle: 'Side elevation of dark four-door sedan at curb',
    camera: 'Direct Side Elevation',
    timeLabel: 'T+00:25',
    description: 'Vehicle comes to temporary stop alongside curb directly opposite the storefront pedestrian zone.',
  },
  {
    step: 4,
    title: '4. Vehicle Passing Witnesses',
    subtitle: 'Sedan rolling past primary witness field of view',
    camera: 'Sidewalk Oblique',
    timeLabel: 'T+00:32',
    description: 'Witnesses W-001 and W-002 observe the vehicle traverse their forward arc of sight.',
  },
  {
    step: 5,
    title: '5. Witnesses Stationary Observation',
    subtitle: 'Witness positions fixed during visual contact',
    camera: 'Storefront Doorway Viewpoint',
    timeLabel: 'T+00:38',
    description: 'All three witnesses remain stationary at observed vantage points, confirming unshifted lines of sight.',
  },
  {
    step: 6,
    title: '6. Vehicle Detail: Rear Quarter',
    subtitle: 'Close observation of sedan C-pillar & rear profile',
    camera: 'Close-Up Detail Angle',
    timeLabel: 'T+00:44',
    description: 'Close architectural view showing clean dark paint, tinted rear glass, and standard manufacturer rim design.',
  },
  {
    step: 7,
    title: '7. Vehicle Detail: Front Quarter',
    subtitle: 'Wheel arch, front fender, and hood line',
    camera: 'Close-Up Front Lateral',
    timeLabel: 'T+00:48',
    description: 'Secondary detail confirming four-door configuration, standard headlights, and lack of visible bumper stickers.',
  },
  {
    step: 8,
    title: '8. Vehicle Departure',
    subtitle: 'Sedan accelerating east toward main intersection',
    camera: 'Long-Focal Departure Perspective',
    timeLabel: 'T+00:58',
    description: 'Subject enters vehicle; sedan accelerates smoothly eastward past the next commercial cross-street.',
  },
  {
    step: 9,
    title: '9. Return to Scene Tranquility',
    subtitle: 'Establishing view returned with reconstructed vectors',
    camera: 'Wide Angle Overview with Overlay',
    timeLabel: 'T+01:15 (Post-Event)',
    description: 'Scene returned to ambient state with complete spatial vectors preserved for court packet discovery.',
  },
];

export const DEMO_POSSIBLE_LEADS = [
  {
    id: 'lead-041-A',
    rank: 1,
    similarityPct: 83,
    vectorDistance: '0.17 cosine',
    basis: 'High correlation on jawline angle and thick arched brow morphology',
    disclaimer: 'Unverified candidate match — judicial review required',
  },
  {
    id: 'lead-041-B',
    rank: 2,
    similarityPct: 76,
    vectorDistance: '0.24 cosine',
    basis: 'Correlated on deep-set orbit depth and straight nasal bridge',
    disclaimer: 'Unverified candidate match — human investigator review mandatory',
  },
  {
    id: 'lead-041-C',
    rank: 3,
    similarityPct: 71,
    vectorDistance: '0.29 cosine',
    basis: 'Moderate match on estimated age band and bilateral ear orientation',
    disclaimer: 'Unverified candidate match — strictly corroborative lead only',
  },
];

export const DEMO_AUDIT_BLOCKS = [
  {
    seq: 1,
    action: 'CASE_INITIALIZATION',
    officer: 'Investigator (Demo Session)',
    timestamp: '2026-10-29T09:15:00Z',
    sha256: '9a7b1c3d4e5f60718293a4b5c6d7e8f90123456789abcdef0123456789abcdef',
    status: 'valid' as const,
    details: 'Case DEMO-2026-041 initialized with access purpose: "Reconstructed witness account"',
  },
  {
    seq: 2,
    action: 'WITNESS_STATEMENT_INGEST',
    officer: 'Investigator (Demo Session)',
    timestamp: '2026-10-29T09:22:15Z',
    sha256: '4f8e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d3c2b1a0f9e8d7c6b5a4f3e',
    status: 'valid' as const,
    details: 'Ingested audio statements for witnesses W-001, W-002, W-003 (Tamil/Hindi/English)',
  },
  {
    seq: 3,
    action: 'FORENSIC_ATTRIBUTE_EXTRACTION',
    officer: 'System (Forensic Parser)',
    timestamp: '2026-10-29T09:28:40Z',
    sha256: '1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f809',
    status: 'valid' as const,
    details: 'Extracted 6 facial attributes with locked agreement; segregated 3 unstated features to AI Assumed',
  },
  {
    seq: 4,
    action: 'SPATIAL_SCENE_RECONSTRUCTION',
    officer: 'Investigator (Demo Session)',
    timestamp: '2026-10-29T09:35:10Z',
    sha256: 'e5d4c3b2a1f09e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a2f1e0d9c8b7a6f5e4d',
    status: 'valid' as const,
    details: 'Constructed 6-entity spatial diagram and 9-panel vehicle trajectory storyboard',
  },
  {
    seq: 5,
    action: 'COMPOSITE_FINALIZATION',
    officer: 'Supervisor (Demo Authorization)',
    timestamp: '2026-10-29T09:42:00Z',
    sha256: '7c8cff5ad1ff2fd4a4ffb454ff6b6b7c8cff5ad1ff2fd4a4ffb454ff6b6b7c8c',
    status: 'valid' as const,
    details: 'Court discovery packet finalized with cryptographic seal and Section 65B certification',
  },
];
