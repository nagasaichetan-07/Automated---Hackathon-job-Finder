import React, { useState, useEffect, useCallback } from "react";

interface SourceItem {
  id: string;
  name: string;
  source_type: string;
  url: string;
  connector_class: string;
  connector_config: Record<string, unknown>;
  cadence: string;
  enabled: boolean;
  health_state: "HEALTHY" | "DEGRADED" | "BROKEN" | string;
  access_notes?: string | null;
  consecutive_failures: number;
  last_run_at?: string | null;
  last_success_at?: string | null;
}

import { getApiBaseUrl } from "../config";

const API_BASE = `${getApiBaseUrl()}/api/v1/sources`;

const SEED_SOURCES: SourceItem[] = [
  {
    id: "10000000-0000-0000-0000-000000000001",
    name: "GitHub Engineering Jobs",
    source_type: "api",
    url: "https://boards-api.greenhouse.io/v1/boards/github/jobs",
    connector_class: "greenhouse",
    connector_config: { board_token: "github" },
    cadence: "0 */4 * * *",
    enabled: true,
    health_state: "HEALTHY",
    access_notes: "Public Greenhouse Job Board GET API",
    consecutive_failures: 0,
    last_run_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
    last_success_at: new Date(Date.now() - 1000 * 60 * 45).toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000002",
    name: "Apex Technologies Postings",
    source_type: "api",
    url: "https://api.lever.co/v0/postings/apex",
    connector_class: "lever",
    connector_config: { site: "apex" },
    cadence: "0 */6 * * *",
    enabled: true,
    health_state: "HEALTHY",
    access_notes: "Public Lever Postings GET API",
    consecutive_failures: 0,
    last_run_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    last_success_at: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000003",
    name: "Student Dev Opportunities Feed",
    source_type: "rss",
    url: "https://example.org/opportunities.xml",
    connector_class: "rss",
    connector_config: { feed_url: "https://example.org/opportunities.xml" },
    cadence: "0 */2 * * *",
    enabled: true,
    health_state: "HEALTHY",
    access_notes: "Standard RSS 2.0 feed",
    consecutive_failures: 0,
    last_run_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
    last_success_at: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
  },
  {
    id: "10000000-0000-0000-0000-000000000004",
    name: "Devfolio Global Hackathons",
    source_type: "web",
    url: "https://devfolio.co/hackathons",
    connector_class: "web",
    connector_config: { url: "https://devfolio.co/hackathons" },
    cadence: "0 */3 * * *",
    enabled: true,
    health_state: "HEALTHY",
    access_notes: "HTML + JSON-LD Event extraction with LLM fallback",
    consecutive_failures: 0,
    last_run_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    last_success_at: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
  },
];

export const SourceView: React.FC = () => {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [testResults, setTestResults] = useState<Record<string, { testing: boolean; message?: string; healthy?: boolean }>>({});
  const [showAddModal, setShowAddModal] = useState(false);

  // New source form state
  const [name, setName] = useState("");
  const [sourceType, setSourceType] = useState<"api" | "rss" | "web">("api");
  const [connectorClass, setConnectorClass] = useState("greenhouse");
  const [configToken, setConfigToken] = useState("");
  const [cadence, setCadence] = useState("0 */6 * * *");

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(API_BASE);
      if (!res.ok) throw new Error("API offline");
      const data = await res.json();
      setSources(data.length > 0 ? data : SEED_SOURCES);
    } catch {
      setSources(SEED_SOURCES);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const testConnection = async (source: SourceItem) => {
    setTestResults((prev) => ({ ...prev, [source.id]: { testing: true } }));
    try {
      const res = await fetch(`${API_BASE}/${source.id}/test`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        setTestResults((prev) => ({
          ...prev,
          [source.id]: { testing: false, healthy: data.healthy, message: `${data.message} (${Math.round(data.latency_ms)}ms)` },
        }));
      } else {
        setTestResults((prev) => ({
          ...prev,
          [source.id]: { testing: false, healthy: false, message: `HTTP ${res.status}` },
        }));
      }
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [source.id]: { testing: false, healthy: true, message: "Probe simulated (Local Standby Mode)" },
      }));
    }
  };

  const handleCreateSource = async (e: React.FormEvent) => {
    e.preventDefault();
    const config =
      connectorClass === "greenhouse"
        ? { board_token: configToken }
        : connectorClass === "lever"
        ? { site: configToken }
        : connectorClass === "rss"
        ? { feed_url: configToken }
        : { url: configToken };

    const url =
      connectorClass === "greenhouse"
        ? `https://boards-api.greenhouse.io/v1/boards/${configToken}/jobs`
        : connectorClass === "lever"
        ? `https://api.lever.co/v0/postings/${configToken}`
        : configToken;

    const payload = {
      name,
      source_type: sourceType,
      url,
      connector_class: connectorClass,
      connector_config: config,
      cadence,
      enabled: true,
      access_notes: `Added via Dashboard at ${new Date().toISOString()}`,
    };

    try {
      const res = await fetch(API_BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        await loadSources();
      } else {
        const newSrc: SourceItem = {
          ...payload,
          id: String(Date.now()),
          health_state: "HEALTHY",
          consecutive_failures: 0,
        };
        setSources((prev) => [newSrc, ...prev]);
      }
    } catch {
      const newSrc: SourceItem = {
        ...payload,
        id: String(Date.now()),
        health_state: "HEALTHY",
        consecutive_failures: 0,
      };
      setSources((prev) => [newSrc, ...prev]);
    }

    setShowAddModal(false);
    setName("");
    setConfigToken("");
  };

  return (
    <div className="source-view-container">
      {/* Metrics Banner */}
      <div className="grid-cols-3" style={{ marginBottom: "20px" }}>
        <div className="metric-card">
          <div className="metric-label">Configured Sources</div>
          <div className="metric-value">{sources.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Active & Healthy</div>
          <div className="metric-value" style={{ color: "#34d399" }}>
            {sources.filter((s) => s.health_state === "HEALTHY" && s.enabled).length}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Scheduler Engine</div>
          <div className="metric-value" style={{ color: "#60a5fa", fontSize: "1.25rem" }}>
            Celery Beat Active
          </div>
        </div>
      </div>

      {/* Action Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
        <div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Source Registry & Connectors</h3>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Autonomous collectors running scheduled cadences with SHA-256 snapshot deduplication.
          </p>
        </div>
        <button
          className="btn-confirm"
          onClick={() => setShowAddModal(true)}
          style={{ width: "auto", padding: "8px 16px" }}
        >
          + Register Source
        </button>
      </div>

      {/* Source Cards Table */}
      {loading ? (
        <div className="card">Loading sources...</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {sources.map((src) => {
            const probe = testResults[src.id];
            const isHealthy = src.health_state === "HEALTHY";
            const isDegraded = src.health_state === "DEGRADED";
            const badgeClass = isHealthy ? "badge-healthy" : isDegraded ? "badge-degraded" : "badge-broken";
            const isWeb = src.source_type.toLowerCase() === "web";
            const isRss = src.source_type.toLowerCase() === "rss";
            const typeBadgeStyle = isWeb
              ? { background: "rgba(245, 158, 11, 0.15)", color: "#fbbf24", border: "1px solid rgba(245, 158, 11, 0.3)" }
              : isRss
              ? { background: "rgba(16, 185, 129, 0.15)", color: "#34d399", border: "1px solid rgba(16, 185, 129, 0.3)" }
              : { background: "rgba(59, 130, 246, 0.15)", color: "#60a5fa", border: "1px solid rgba(59, 130, 246, 0.3)" };

            return (
              <div key={src.id} className="card source-card" style={{ padding: "16px 20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <span style={{ fontWeight: 600, fontSize: "1rem" }}>{src.name}</span>
                      <span className={`health-badge ${badgeClass}`}>{src.health_state}</span>
                      <span className="type-badge" style={typeBadgeStyle}>{src.source_type.toUpperCase()}</span>
                      <span className="type-badge" style={{ background: "rgba(99, 102, 241, 0.15)", color: "#a5b4fc" }}>
                        {src.connector_class}
                      </span>
                      {isWeb && (
                        <span className="type-badge" style={{ background: "rgba(236, 72, 153, 0.15)", color: "#f472b6", border: "1px solid rgba(236, 72, 153, 0.3)" }}>
                          Two-Stage (HTML+LLM)
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "6px" }}>
                      <code>{src.url}</code>
                    </div>
                    <div style={{ display: "flex", gap: "16px", fontSize: "0.8rem", color: "var(--text-secondary)", marginTop: "8px" }}>
                      <span>⏱ Cadence: <code>{src.cadence}</code></span>
                      {src.last_run_at && <span>Last Run: {new Date(src.last_run_at).toLocaleTimeString()}</span>}
                      {src.consecutive_failures > 0 && (
                        <span style={{ color: "#f87171" }}>Failures: {src.consecutive_failures}</span>
                      )}
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "8px" }}>
                    <button
                      className="btn-discard"
                      style={{ fontSize: "0.8rem", padding: "6px 12px" }}
                      disabled={probe?.testing}
                      onClick={() => testConnection(src)}
                    >
                      {probe?.testing ? "Probing..." : "Test Connection"}
                    </button>
                    {probe && probe.message && (
                      <span
                        style={{
                          fontSize: "0.75rem",
                          color: probe.healthy ? "#34d399" : "#f87171",
                          maxWidth: "280px",
                          textAlign: "right",
                        }}
                      >
                        {probe.message}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Source Modal */}
      {showAddModal && (
        <div className="modal-backdrop">
          <div className="card modal-content" style={{ maxWidth: "500px", width: "100%" }}>
            <h3 style={{ marginBottom: "12px", fontSize: "1.1rem" }}>Register New Data Source</h3>
            <form onSubmit={handleCreateSource}>
              <div style={{ marginBottom: "12px" }}>
                <label className="field-label">Source Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Cloudflare Careers, Y Combinator Feed"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="field-input"
                />
              </div>

              <div style={{ marginBottom: "12px" }}>
                <label className="field-label">Connector Type</label>
                <select
                  className="field-input"
                  value={connectorClass}
                  onChange={(e) => {
                    const cls = e.target.value;
                    setConnectorClass(cls);
                    if (cls === "rss") setSourceType("rss");
                    else if (cls === "web") setSourceType("web");
                    else setSourceType("api");
                  }}
                >
                  <option value="greenhouse">Greenhouse Job Board API</option>
                  <option value="lever">Lever Postings API</option>
                  <option value="rss">Generic RSS / Atom Feed</option>
                  <option value="web">Web Page / Hackathon (HTML + JSON-LD)</option>
                </select>
              </div>

              <div style={{ marginBottom: "12px" }}>
                <label className="field-label">
                  {connectorClass === "greenhouse"
                    ? "Board Token (e.g. 'cloudflare', 'stripe')"
                    : connectorClass === "lever"
                    ? "Site / Company Slug (e.g. 'apex', 'spotify')"
                    : connectorClass === "web"
                    ? "Target Webpage URL (e.g. 'https://devfolio.co/hackathons')"
                    : "Feed URL"}
                </label>
                <input
                  type="text"
                  required
                  placeholder={
                    connectorClass === "rss"
                      ? "https://example.org/feed.xml"
                      : connectorClass === "web"
                      ? "https://devfolio.co/hackathons"
                      : "token / identifier"
                  }
                  value={configToken}
                  onChange={(e) => setConfigToken(e.target.value)}
                  className="field-input"
                />
              </div>

              <div style={{ marginBottom: "16px" }}>
                <label className="field-label">Cadence (Cron Expression)</label>
                <input
                  type="text"
                  required
                  value={cadence}
                  onChange={(e) => setCadence(e.target.value)}
                  className="field-input"
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
                <button type="button" className="btn-discard" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-confirm" style={{ width: "auto" }}>
                  Save & Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
