import { describe, it, expect } from 'vitest';
import {
  checkAudioSupport,
  getSupportedAudioMimeType,
  DEMO_SAMPLE_TRANSCRIPTS,
} from './audioRecorder';

describe('Audio Recorder & Speech Handling', () => {
  it('correctly inspects audio support in test environment', () => {
    const status = checkAudioSupport();
    expect(typeof status.supported).toBe('boolean');
    expect(typeof status.isSecure).toBe('boolean');
  });

  it('selects valid supported MIME type or empty fallback', () => {
    const mime = getSupportedAudioMimeType();
    expect(typeof mime).toBe('string');
  });

  it('provides coherent sample transcripts for all three regional languages', () => {
    expect(DEMO_SAMPLE_TRANSCRIPTS.ta.original).toContain('30 வயது');
    expect(DEMO_SAMPLE_TRANSCRIPTS.hi.original).toContain('30 वर्ष');
    expect(DEMO_SAMPLE_TRANSCRIPTS.en.original).toContain('30 years old');
    expect(DEMO_SAMPLE_TRANSCRIPTS.ta.english).toContain('dark sedan');
  });
});
