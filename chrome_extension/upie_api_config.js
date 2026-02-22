// upie_api_config.js

export const API_BASE = "http://127.0.0.1:8000";

export const ENDPOINTS = {
  EXECUTE: `${API_BASE}/brain/execute`,
  INGEST: `${API_BASE}/api/v1/ingest`,
  INGEST_CONVERSATION: `${API_BASE}/api/v1/ingest/conversation`,
  HEALTH: `${API_BASE}/health`
};
