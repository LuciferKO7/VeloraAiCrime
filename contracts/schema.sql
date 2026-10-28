PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  full_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('investigator','artist','supervisor','auditor','admin')),
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  failed_logins INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  created_at TEXT NOT NULL,
  last_login_at TEXT
);

CREATE TABLE cases (
  id TEXT PRIMARY KEY,
  case_number TEXT NOT NULL UNIQUE, -- e.g. FIR number
  title TEXT NOT NULL,
  station TEXT,
  offence_summary TEXT,
  data_mode TEXT NOT NULL DEFAULT 'demo' CHECK (data_mode IN ('demo','real')),
  default_appearance_group TEXT NOT NULL DEFAULT 'unspecified' CHECK (default_appearance_group IN ('south_asian','east_asian','southeast_asian','white','black','middle_eastern','latino','mixed_other','unspecified')),
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','archived')),
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE case_access (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  user_id TEXT NOT NULL REFERENCES users(id),
  access_level TEXT NOT NULL CHECK (access_level IN ('view','edit')),
  granted_by TEXT NOT NULL REFERENCES users(id),
  granted_at TEXT NOT NULL,
  revoked_at TEXT,
  UNIQUE (case_id, user_id)
);

CREATE TABLE witnesses (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  alias TEXT NOT NULL, -- e.g. W-001, never a real name
  preferred_language TEXT NOT NULL CHECK (preferred_language IN ('en','ta','hi','te','kn','ml','bn','mr')),
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  UNIQUE (case_id, alias)
);

CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  witness_id TEXT NOT NULL REFERENCES witnesses(id),
  kind TEXT NOT NULL CHECK (kind IN ('face','scene')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','abandoned')),
  current_round INTEGER NOT NULL DEFAULT 0,
  current_snapshot_id TEXT, -- latest attribute_snapshots.id (no FK: circular)
  locked_features_json TEXT NOT NULL DEFAULT '[]',
  selected_image_id TEXT,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE TABLE statements (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  speaker TEXT NOT NULL CHECK (speaker IN ('witness','officer','assistant','system')),
  original_text TEXT NOT NULL,
  original_lang TEXT NOT NULL CHECK (original_lang IN ('en','ta','hi','te','kn','ml','bn','mr')),
  english_text TEXT NOT NULL,
  translation_engine TEXT, -- 'none' | 'indictrans2' | 'gemini' | 'ollama'
  input_mode TEXT NOT NULL CHECK (input_mode IN ('text','voice')),
  audio_sha256 TEXT,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE attribute_snapshots (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  version INTEGER NOT NULL, -- 1,2,3... per session
  attributes_json TEXT NOT NULL, -- FaceAttributes (§6.1) or null for scene sessions
  derived_from_statement_id TEXT REFERENCES statements(id),
  llm_call_id TEXT,
  change_source TEXT NOT NULL CHECK (change_source IN ('statement','user_edit','edit_chat','system')),
  created_at TEXT NOT NULL,
  UNIQUE (session_id, version)
);

CREATE TABLE rounds (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  round_no INTEGER NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('initial','evolve','edit','transform','finalize')),
  params_json TEXT NOT NULL DEFAULT '{}',
  attribute_snapshot_id TEXT REFERENCES attribute_snapshots(id),
  status TEXT NOT NULL CHECK (status IN ('pending','running','done','failed')),
  error TEXT,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL,
  finished_at TEXT,
  UNIQUE (session_id, round_no)
);

CREATE TABLE model_registry (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('image_gen','inpaint','identity_adapter','face_parser','face_embedder','upscaler','attribute_verifier','preference_model','llm_parser','asr','translator','prompt_lexicon','glossary')),
  version TEXT NOT NULL,
  source TEXT,
  license TEXT,
  checksum TEXT,
  metrics_json TEXT NOT NULL DEFAULT '{}',
  is_active INTEGER NOT NULL DEFAULT 0,
  registered_at TEXT NOT NULL,
  UNIQUE (name, version)
);

CREATE TABLE images (
  id TEXT PRIMARY KEY, -- = ml_service image_id (single ID space)
  session_id TEXT NOT NULL REFERENCES sessions(id),
  round_id TEXT NOT NULL REFERENCES rounds(id),
  parent_image_id TEXT REFERENCES images(id),
  variant_index INTEGER NOT NULL DEFAULT 0,
  kind TEXT NOT NULL CHECK (kind IN ('variant','edit','age','disguise','profile','final')),
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  seed INTEGER,
  prompt_text TEXT,
  negative_prompt TEXT,
  variant_axes_json TEXT NOT NULL DEFAULT '{}',
  sha256 TEXT NOT NULL,
  sketch_sha256 TEXT,
  storage_path TEXT NOT NULL,
  sketch_path TEXT,
  model_versions_json TEXT NOT NULL DEFAULT '{}',
  attr_adherence REAL,
  identity_similarity REAL,
  speculative INTEGER NOT NULL DEFAULT 0,
  is_final INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_images_session ON images(session_id);

CREATE TABLE feedback_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  round_id TEXT REFERENCES rounds(id),
  image_id TEXT REFERENCES images(id),
  event_type TEXT NOT NULL CHECK (event_type IN ('pick','reject','more_like','less_like','edit_request','lock_feature','unlock_feature','confidence_set','undo')),
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE llm_calls (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  session_id TEXT,
  task TEXT NOT NULL CHECK (task IN ('parse','edit_parse','question','translate','scene_extract','synth_describe','glossary_suggest','smoke','other')),
  provider TEXT NOT NULL CHECK (provider IN ('gemini','ollama')),
  model TEXT NOT NULL,
  route_reason TEXT NOT NULL CHECK (route_reason IN ('demo_allowed','real_local_only','fallback_after_error','forced_by_env')),
  prompt_text TEXT,
  response_text TEXT,
  latency_ms INTEGER,
  tokens_in INTEGER,
  tokens_out INTEGER,
  status TEXT NOT NULL CHECK (status IN ('ok','error','schema_invalid')),
  error TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE glossary_terms (
  id TEXT PRIMARY KEY,
  language TEXT NOT NULL,
  term TEXT NOT NULL,
  maps_to_json TEXT NOT NULL, -- {"attribute":"jaw_shape","value":"square"}
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  suggested_by_llm_call_id TEXT,
  suggested_at TEXT NOT NULL,
  reviewed_by TEXT REFERENCES users(id),
  reviewed_at TEXT,
  UNIQUE (language, term)
);

CREATE TABLE exports (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  image_id TEXT REFERENCES images(id),
  scene_id TEXT,
  format TEXT NOT NULL CHECK (format IN ('png','pdf','json','svg')),
  file_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  disclaimer_version TEXT NOT NULL,
  model_versions_json TEXT NOT NULL DEFAULT '{}',
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE scenes (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id),
  session_id TEXT NOT NULL UNIQUE REFERENCES sessions(id),
  title TEXT,
  scene_json TEXT NOT NULL, -- Scene (§6.2)
  version INTEGER NOT NULL DEFAULT 1,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE gallery_faces (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('synthetic','consented_volunteer')),
  consent_ref TEXT,
  image_path TEXT NOT NULL,
  embedding BLOB NOT NULL, -- float32[512], L2-normalised
  embedding_model_version TEXT NOT NULL,
  added_by TEXT NOT NULL REFERENCES users(id),
  added_at TEXT NOT NULL
);

CREATE TABLE match_searches (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  image_id TEXT NOT NULL REFERENCES images(id),
  top_k INTEGER NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE match_results (
  id TEXT PRIMARY KEY,
  search_id TEXT NOT NULL REFERENCES match_searches(id),
  gallery_face_id TEXT NOT NULL REFERENCES gallery_faces(id),
  rank INTEGER NOT NULL,
  similarity REAL NOT NULL
);

CREATE TABLE eval_runs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('parser','verifier','lexicon','convergence','bias_audit','end_to_end')),
  config_json TEXT NOT NULL DEFAULT '{}',
  metrics_json TEXT NOT NULL,
  created_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL
);

CREATE TABLE audit_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_id TEXT,
  username TEXT,
  role TEXT,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id TEXT,
  case_id TEXT,
  purpose TEXT,
  ip TEXT,
  user_agent TEXT,
  status_code INTEGER,
  details_json TEXT NOT NULL DEFAULT '{}',
  prev_hash TEXT NOT NULL, -- 64 zeros for seq=1
  entry_hash TEXT NOT NULL UNIQUE
);

CREATE INDEX idx_audit_case ON audit_log(case_id);
CREATE INDEX idx_audit_user ON audit_log(user_id);
CREATE INDEX idx_audit_ts ON audit_log(ts);

CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit_log is append-only'); END;
