import React, { useState, useCallback, useRef } from "react";

/* -----------------------------------------------------------------------
   Types
   ----------------------------------------------------------------------- */

interface FieldEvidence {
  value: unknown;
  evidence: string;
  confidence: number;
}

interface DraftFields {
  education_level?: string | null;
  graduation_year?: number | null;
  branch?: string | null;
  skills?: string[];
  preferred_locations?: string[];
  opportunity_types?: string[];
  interests?: string[];
}

interface ProfileData {
  id?: string;
  user_id: string;
  education_level?: string | null;
  graduation_year?: number | null;
  branch?: string | null;
  skills: string[];
  preferred_locations: string[];
  opportunity_types: string[];
  interests: string[];
  resume_confirmed: boolean;
  resume_extracted?: DraftFields | null;
  resume_evidence?: Record<string, FieldEvidence> | null;
}

type UploadState =
  | { phase: "idle" }
  | { phase: "uploading" }
  | { phase: "draft"; draft: DraftFields; evidence: Record<string, FieldEvidence>; pageCount: number; charCount: number }
  | { phase: "confirmed" }
  | { phase: "error"; message: string };

import { getApiBaseUrl } from "../config";

const API = `${getApiBaseUrl()}/api/v1/profile`;

async function fetchProfile(userId: string): Promise<ProfileData | null> {
  try {
    const res = await fetch(`${API}/${userId}`);
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

async function uploadResume(userId: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API}/${userId}/resume`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed (${res.status})`);
  }
  return await res.json();
}

async function confirmProfile(userId: string, fields: DraftFields): Promise<ProfileData> {
  const res = await fetch(`${API}/${userId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!res.ok) throw new Error(`Confirm failed (${res.status})`);
  return await res.json();
}

/* -----------------------------------------------------------------------
   Sub-components
   ----------------------------------------------------------------------- */

const ConfidenceBadge: React.FC<{ confidence: number }> = ({ confidence }) => {
  const pct = Math.round(confidence * 100);
  const cls = pct >= 90 ? "conf-high" : pct >= 70 ? "conf-mid" : "conf-low";
  return <span className={`confidence-badge ${cls}`}>{pct}%</span>;
};

const EvidenceQuote: React.FC<{ text: string }> = ({ text }) => (
  <span className="evidence-quote" title={text}>
    "{text.length > 60 ? text.slice(0, 57) + "…" : text}"
  </span>
);

/* -----------------------------------------------------------------------
   Main ProfileView Component
   ----------------------------------------------------------------------- */

export const ProfileView: React.FC = () => {
  /* --- State ---------------------------------------------------------- */
  const [userId, setUserId] = useState("00000000-0000-0000-0000-000000000001");
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [upload, setUpload] = useState<UploadState>({ phase: "idle" });
  const [editFields, setEditFields] = useState<DraftFields>({});
  const [isDragOver, setIsDragOver] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  /* --- Load Profile --------------------------------------------------- */
  const loadProfile = useCallback(async () => {
    setLoadingProfile(true);
    const p = await fetchProfile(userId);
    setProfile(p);
    if (p?.resume_extracted && !p.resume_confirmed) {
      setUpload({
        phase: "draft",
        draft: p.resume_extracted,
        evidence: p.resume_evidence ?? {},
        pageCount: 0,
        charCount: 0,
      });
      setEditFields({ ...p.resume_extracted });
    } else if (p?.resume_confirmed) {
      setUpload({ phase: "confirmed" });
    }
    setLoadingProfile(false);
  }, [userId]);

  /* --- File Upload ---------------------------------------------------- */
  const handleFile = useCallback(
    async (file: File) => {
      if (file.type !== "application/pdf") {
        setUpload({ phase: "error", message: "Only PDF files are accepted." });
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setUpload({ phase: "error", message: "File exceeds 10 MB limit." });
        return;
      }
      setUpload({ phase: "uploading" });
      try {
        const data = await uploadResume(userId, file);
        setUpload({
          phase: "draft",
          draft: data.draft_fields,
          evidence: data.evidence,
          pageCount: data.page_count,
          charCount: data.char_count,
        });
        setEditFields({ ...data.draft_fields });
      } catch (err: unknown) {
        setUpload({ phase: "error", message: err instanceof Error ? err.message : "Upload failed" });
      }
    },
    [userId],
  );

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  /* --- Confirm -------------------------------------------------------- */
  const handleConfirm = async () => {
    try {
      const p = await confirmProfile(userId, editFields);
      setProfile(p);
      setUpload({ phase: "confirmed" });
    } catch (err: unknown) {
      setUpload({ phase: "error", message: err instanceof Error ? err.message : "Confirmation failed" });
    }
  };

  /* --- Edit helpers --------------------------------------------------- */
  const setField = <K extends keyof DraftFields>(k: K, v: DraftFields[K]) =>
    setEditFields((prev) => ({ ...prev, [k]: v }));

  const setSkillsStr = (raw: string) => setField("skills", raw.split(",").map((s) => s.trim()).filter(Boolean));
  const setLocsStr = (raw: string) => setField("preferred_locations", raw.split(",").map((s) => s.trim()).filter(Boolean));
  const setInterestsStr = (raw: string) => setField("interests", raw.split(",").map((s) => s.trim()).filter(Boolean));

  /* --- Render --------------------------------------------------------- */
  return (
    <div className="profile-view">
      {/* ---- User ID Selector ---- */}
      <div className="card">
        <h3 className="card-title">Profile &amp; Résumé Intelligence</h3>
        <p className="card-desc">
          Upload your résumé, review extracted facts with AI-generated confidence scores, edit if needed, then confirm to finalize your profile.
        </p>
        <div className="pv-row" style={{ marginTop: 16 }}>
          <label className="pv-label">User ID</label>
          <input
            id="profile-user-id"
            className="pv-input"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            style={{ flex: 1 }}
          />
          <button id="profile-load-btn" className="pv-btn pv-btn-secondary" onClick={loadProfile} disabled={loadingProfile}>
            {loadingProfile ? "Loading…" : "Load Profile"}
          </button>
        </div>
      </div>

      {/* ---- Upload Zone ---- */}
      {upload.phase !== "confirmed" && (
        <div
          id="resume-dropzone"
          className={`card upload-zone ${isDragOver ? "drag-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <input ref={fileRef} type="file" accept="application/pdf" onChange={onFileChange} hidden />
          {upload.phase === "uploading" ? (
            <div className="upload-spinner">
              <div className="spinner" />
              <span>Extracting résumé…</span>
            </div>
          ) : (
            <>
              <div className="upload-icon">📄</div>
              <div className="upload-label">
                Drag &amp; drop your résumé PDF here, or <strong>click to browse</strong>
              </div>
              <div className="upload-hint">PDF only · Max 10 MB · Deterministic extraction first, then AI structuring</div>
            </>
          )}
        </div>
      )}

      {/* ---- Error ---- */}
      {upload.phase === "error" && (
        <div className="card pv-error">
          <strong>⚠ Upload Error:</strong> {upload.message}
        </div>
      )}

      {/* ---- Draft Review ---- */}
      {upload.phase === "draft" && (
        <div className="card draft-panel">
          <div className="draft-header">
            <h3 className="card-title">📋 Review Extracted Draft</h3>
            <span className="draft-badge">UNCONFIRMED DRAFT</span>
          </div>
          <p className="card-desc" style={{ marginBottom: 16 }}>
            These fields were extracted from your résumé. Review, edit as needed, and confirm to apply to your profile.
            {upload.charCount > 0 && <> · {upload.charCount.toLocaleString()} characters from {upload.pageCount} page{upload.pageCount !== 1 ? "s" : ""}</>}
          </p>

          {/* Education */}
          <div className="pv-field-group">
            <div className="pv-field-header">
              <label className="pv-label">Education Level</label>
              {upload.evidence["education_level"] && (
                <>
                  <ConfidenceBadge confidence={upload.evidence["education_level"].confidence} />
                  <EvidenceQuote text={upload.evidence["education_level"].evidence} />
                </>
              )}
            </div>
            <input
              id="draft-education-level"
              className="pv-input"
              value={editFields.education_level ?? ""}
              onChange={(e) => setField("education_level", e.target.value || null)}
            />
          </div>

          {/* Graduation Year */}
          <div className="pv-field-group">
            <div className="pv-field-header">
              <label className="pv-label">Graduation Year</label>
              {upload.evidence["graduation_year"] && (
                <>
                  <ConfidenceBadge confidence={upload.evidence["graduation_year"].confidence} />
                  <EvidenceQuote text={upload.evidence["graduation_year"].evidence} />
                </>
              )}
            </div>
            <input
              id="draft-graduation-year"
              className="pv-input"
              type="number"
              value={editFields.graduation_year ?? ""}
              onChange={(e) => setField("graduation_year", e.target.value ? parseInt(e.target.value) : null)}
            />
          </div>

          {/* Branch */}
          <div className="pv-field-group">
            <div className="pv-field-header">
              <label className="pv-label">Branch / Major</label>
              {upload.evidence["branch"] && (
                <>
                  <ConfidenceBadge confidence={upload.evidence["branch"].confidence} />
                  <EvidenceQuote text={upload.evidence["branch"].evidence} />
                </>
              )}
            </div>
            <input
              id="draft-branch"
              className="pv-input"
              value={editFields.branch ?? ""}
              onChange={(e) => setField("branch", e.target.value || null)}
            />
          </div>

          {/* Skills */}
          <div className="pv-field-group">
            <div className="pv-field-header">
              <label className="pv-label">Skills</label>
              {upload.evidence["skills"] && (
                <>
                  <ConfidenceBadge confidence={upload.evidence["skills"].confidence} />
                  <EvidenceQuote text={upload.evidence["skills"].evidence} />
                </>
              )}
            </div>
            <input
              id="draft-skills"
              className="pv-input"
              value={(editFields.skills ?? []).join(", ")}
              onChange={(e) => setSkillsStr(e.target.value)}
              placeholder="Comma-separated skills"
            />
            {(editFields.skills ?? []).length > 0 && (
              <div className="pv-tags">
                {editFields.skills!.map((s) => (
                  <span key={s} className="pv-tag">{s}</span>
                ))}
              </div>
            )}
          </div>

          {/* Preferred Locations */}
          <div className="pv-field-group">
            <label className="pv-label">Preferred Locations</label>
            <input
              id="draft-locations"
              className="pv-input"
              value={(editFields.preferred_locations ?? []).join(", ")}
              onChange={(e) => setLocsStr(e.target.value)}
              placeholder="Comma-separated locations"
            />
          </div>

          {/* Interests */}
          <div className="pv-field-group">
            <label className="pv-label">Interests</label>
            <input
              id="draft-interests"
              className="pv-input"
              value={(editFields.interests ?? []).join(", ")}
              onChange={(e) => setInterestsStr(e.target.value)}
              placeholder="Comma-separated interests"
            />
          </div>

          {/* Confirm Button */}
          <div className="pv-actions">
            <button id="profile-confirm-btn" className="pv-btn pv-btn-primary" onClick={handleConfirm}>
              ✓ Confirm &amp; Apply to Profile
            </button>
            <button className="pv-btn pv-btn-secondary" onClick={() => setUpload({ phase: "idle" })}>
              Discard Draft
            </button>
          </div>
        </div>
      )}

      {/* ---- Confirmed State ---- */}
      {upload.phase === "confirmed" && profile && (
        <div className="card confirmed-panel">
          <div className="confirmed-header">
            <h3 className="card-title">✅ Profile Confirmed</h3>
            <span className="confirmed-badge">AUTHORITATIVE</span>
          </div>
          <div className="confirmed-grid">
            <div className="confirmed-item">
              <span className="confirmed-label">Education</span>
              <span className="confirmed-value">{profile.education_level ?? "—"}</span>
            </div>
            <div className="confirmed-item">
              <span className="confirmed-label">Graduation</span>
              <span className="confirmed-value">{profile.graduation_year ?? "—"}</span>
            </div>
            <div className="confirmed-item">
              <span className="confirmed-label">Branch</span>
              <span className="confirmed-value">{profile.branch ?? "—"}</span>
            </div>
            <div className="confirmed-item">
              <span className="confirmed-label">Skills</span>
              <span className="confirmed-value">
                {profile.skills.length > 0 ? (
                  <span className="pv-tags">{profile.skills.map((s) => <span key={s} className="pv-tag">{s}</span>)}</span>
                ) : "—"}
              </span>
            </div>
            <div className="confirmed-item">
              <span className="confirmed-label">Locations</span>
              <span className="confirmed-value">{profile.preferred_locations.join(", ") || "—"}</span>
            </div>
            <div className="confirmed-item">
              <span className="confirmed-label">Interests</span>
              <span className="confirmed-value">{profile.interests.join(", ") || "—"}</span>
            </div>
          </div>
          <div className="pv-actions" style={{ marginTop: 16 }}>
            <button className="pv-btn pv-btn-secondary" onClick={() => setUpload({ phase: "idle" })}>
              Re-upload Résumé
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfileView;
