/**
 * VELORA Genuine Audio Capture & Speech Service Client
 * Provides genuine MediaRecorder recording, secure context validation,
 * microphone track lifecycle cleanup, and honest offline speech service handling.
 */

export interface AudioSupportStatus {
  supported: boolean;
  isSecure: boolean;
  error?: string;
}

export interface RecordingResult {
  blob: Blob;
  mimeType: string;
  durationSec: number;
  sizeBytes: number;
}

export interface TranscriptionResponse {
  text: string;
  language: string;
  duration_sec?: number;
  confidence?: number;
  is_simulated?: boolean;
}

/**
 * Validates browser media capability and secure context requirements.
 */
export function checkAudioSupport(): AudioSupportStatus {
  // Check secure context (localhost or https required by Web Audio/getUserMedia)
  const isSecure = typeof window !== 'undefined' ? Boolean(window.isSecureContext) : false;
  if (!isSecure && typeof window !== 'undefined' && window.location.hostname !== 'localhost') {
    return {
      supported: false,
      isSecure: false,
      error: 'Insecure context: microphone capture requires HTTPS or localhost.',
    };
  }

  if (
    typeof navigator === 'undefined' ||
    !navigator.mediaDevices ||
    typeof navigator.mediaDevices.getUserMedia !== 'function'
  ) {
    return {
      supported: false,
      isSecure,
      error: 'getUserMedia is not supported by this browser.',
    };
  }

  if (typeof window !== 'undefined' && typeof window.MediaRecorder === 'undefined') {
    return {
      supported: false,
      isSecure,
      error: 'MediaRecorder API is not supported by this browser.',
    };
  }

  return { supported: true, isSecure: true };
}

/**
 * Selects best supported audio MIME type across browsers (Chrome, Firefox, Safari, Edge).
 */
export function getSupportedAudioMimeType(): string {
  if (typeof window === 'undefined' || typeof window.MediaRecorder === 'undefined') {
    return 'audio/webm';
  }
  const candidateTypes = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/aac',
  ];
  for (const t of candidateTypes) {
    if (MediaRecorder.isTypeSupported(t)) {
      return t;
    }
  }
  return '';
}

/**
 * Active recording handle preserving stream and recorder for track cleanup.
 */
export class AudioRecordingSession {
  private mediaRecorder: MediaRecorder | null = null;
  private mediaStream: MediaStream | null = null;
  private chunks: BlobPart[] = [];
  private startTime: number = 0;

  public async start(): Promise<void> {
    const support = checkAudioSupport();
    if (!support.supported) {
      throw new Error(support.error || 'Audio recording unsupported');
    }

    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });
    } catch (err: unknown) {
      if (err instanceof Error) {
        if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
          throw new Error('Microphone permission was denied by user or browser policy.');
        }
        if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
          throw new Error('No microphone hardware detected on this device.');
        }
        if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
          throw new Error('Microphone is busy or locked by another application.');
        }
        throw new Error(`Microphone error (${err.name}): ${err.message}`);
      }
      throw new Error('Failed to access microphone.');
    }

    const mimeType = getSupportedAudioMimeType();
    const options: MediaRecorderOptions = mimeType ? { mimeType } : {};

    try {
      this.mediaRecorder = new MediaRecorder(this.mediaStream, options);
    } catch {
      // Fallback without explicit mimeType
      this.mediaRecorder = new MediaRecorder(this.mediaStream);
    }

    this.chunks = [];
    this.startTime = Date.now();

    this.mediaRecorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        this.chunks.push(event.data);
      }
    };

    // Request data in 250ms timeslices for reliable streaming collection
    this.mediaRecorder.start(250);
  }

  public async stop(): Promise<RecordingResult> {
    return new Promise((resolve, reject) => {
      if (!this.mediaRecorder || this.mediaRecorder.state === 'inactive') {
        this.cleanupTracks();
        reject(new Error('No active recording in progress.'));
        return;
      }

      this.mediaRecorder.onstop = () => {
        const durationSec = Math.max(0.5, (Date.now() - this.startTime) / 1000);
        const mimeType = this.mediaRecorder?.mimeType || 'audio/webm';
        const blob = new Blob(this.chunks, { type: mimeType });

        this.cleanupTracks();

        if (blob.size < 100) {
          reject(new Error('Recorded audio was empty (<100 bytes). Please speak into microphone.'));
          return;
        }

        resolve({
          blob,
          mimeType,
          durationSec: Number(durationSec.toFixed(1)),
          sizeBytes: blob.size,
        });
      };

      this.mediaRecorder.stop();
    });
  }

  public cleanupTracks(): void {
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch {
          // ignore cleanup errors
        }
      });
      this.mediaStream = null;
    }
    this.mediaRecorder = null;
  }
}

/**
 * Attempts real speech-to-text service via backend hub or direct speech proxy (:8002).
 * Strictly throws if unreachable — NEVER pretends fake success on failed network request.
 */
export async function sendAudioForTranscription(
  audioBlob: Blob,
  targetLang: string = 'ta'
): Promise<TranscriptionResponse> {
  const formData = new FormData();
  formData.append('audio', audioBlob, 'witness_statement.webm');
  formData.append('language', targetLang);

  // Try proxy endpoint first
  const endpoints = ['/api/v1/speech/transcribe', 'http://localhost:8002/transcribe'];

  for (const url of endpoints) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        body: formData,
        headers: {
          'X-Access-Purpose': 'Witness statement audio transcription',
        },
      });

      if (response.ok) {
        const data = await response.json();
        return {
          text: data.text || data.transcription || '',
          language: data.language || targetLang,
          duration_sec: data.duration_sec,
          confidence: data.confidence,
        };
      }
    } catch {
      // Endpoint unreachable; continue to next
    }
  }

  throw new Error(
    'Speech Service (:8002) is offline. Audio was captured locally (' +
      (audioBlob.size / 1024).toFixed(1) +
      ' KB), but speech recognition service cannot be reached. You can enter manual transcript or load sample transcript.'
  );
}

/**
 * Fictional regional sample statements for offline hackathon demonstration
 * Case DEMO-2026-041 (Vehicle incident)
 */
export const DEMO_SAMPLE_TRANSCRIPTS: Record<
  string,
  { original: string; english: string; languageName: string }
> = {
  ta: {
    languageName: 'Tamil (தமிழ்)',
    original:
      'அவர் சுமார் 30 வயது, கூர்மையான தாடை, அடர்ந்த புருவங்கள் மற்றும் கருப்பு ஜாக்கெட் அணிந்திருந்தார். டார்க் செடான் காரில் ஏறினார்.',
    english:
      'He was about 30 years old, sharp angular jawline, thick arched eyebrows, wearing a dark jacket. Got into a dark sedan.',
  },
  hi: {
    languageName: 'Hindi (हिन्दी)',
    original:
      'वह लगभग 30 वर्ष का था, तीखा जबड़ा, घनी भौहें और उसने गहरे रंग की जैकेट पहनी थी। वह काली सेडान में सवार हुआ।',
    english:
      'He was about 30 years old, sharp jawline, thick eyebrows, and wore a dark jacket. He got into a dark sedan.',
  },
  en: {
    languageName: 'English',
    original:
      'Unknown male adult, approximately 30 years old, sharp angular jaw, thick arched brows, dark jacket, entered a dark four-door sedan.',
    english:
      'Unknown male adult, approximately 30 years old, sharp angular jaw, thick arched brows, dark jacket, entered a dark four-door sedan.',
  },
};
