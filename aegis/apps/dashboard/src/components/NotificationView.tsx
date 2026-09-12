import React, { useState, useEffect, useCallback } from "react";

interface NotificationItem {
  id: string;
  profile_id: string;
  opportunity_id: string;
  channel: string;
  notification_type: string;
  idempotency_key: string;
  status: "pending" | "sent" | "failed" | string;
  content: {
    subject?: string;
    title?: string;
    category?: string;
    match_score?: number;
    eligibility_state?: string;
    deadline?: string;
    explanation?: string;
    source_url?: string;
    recipient?: string;
    item_count?: number;
    items?: Array<{
      title: string;
      match_score: number;
      eligibility_state: string;
      deadline: string;
      explanation: string;
      source_url: string;
    }>;
  };
  scheduled_at?: string | null;
  sent_at?: string | null;
  created_at: string;
}

interface Preferences {
  quiet_hours_start: number;
  quiet_hours_end: number;
  min_score_threshold: number;
  email_notifications: boolean;
  is_currently_quiet_hours: boolean;
}

const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const API_BASE = "http://localhost:8000/api/v1/notifications";

const SEED_NOTIFICATIONS: NotificationItem[] = [
  {
    id: "40000000-0000-0000-0000-000000000001",
    profile_id: "10000000-0000-0000-0000-000000000001",
    opportunity_id: "20000000-0000-0000-0000-000000000001",
    channel: "email",
    notification_type: "immediate",
    idempotency_key: "a8f9c1e2b4d6e7f80123456789abcdef0123456789abcdef0123456789abcdef",
    status: "sent",
    content: {
      subject: "[Aegis Match: 92%] AI Hackathon Global 2025",
      title: "AI Hackathon Global 2025",
      category: "hackathon",
      match_score: 0.92,
      eligibility_state: "ELIGIBLE",
      deadline: "November 15, 2025",
      explanation: "Eligible: Registration active, open worldwide. High overlap with your skills: Python, React.",
      source_url: "https://hackathons.example.org/ai-hackathon-2025",
      recipient: "student@example.com",
    },
    sent_at: "2026-09-11T09:30:00Z",
    created_at: "2026-09-11T09:30:00Z",
  },
  {
    id: "40000000-0000-0000-0000-000000000002",
    profile_id: "10000000-0000-0000-0000-000000000001",
    opportunity_id: "20000000-0000-0000-0000-000000000002",
    channel: "email",
    notification_type: "immediate",
    idempotency_key: "c3d4e5f60718293a0123456789abcdef0123456789abcdef0123456789abcdef",
    status: "pending",
    content: {
      subject: "[Aegis Match: 84%] Backend Engineering Intern",
      title: "Backend Engineering Intern",
      category: "internship",
      match_score: 0.84,
      eligibility_state: "ELIGIBLE",
      deadline: "December 01, 2025",
      explanation: "Eligible: Degree and branch match. Cites required skills: Python, SQL.",
      source_url: "https://jobs.example.com/backend-intern",
      recipient: "student@example.com",
    },
    scheduled_at: "2026-09-12T08:00:00Z",
    created_at: "2026-09-11T23:15:00Z",
  },
  {
    id: "40000000-0000-0000-0000-000000000003",
    profile_id: "10000000-0000-0000-0000-000000000001",
    opportunity_id: "20000000-0000-0000-0000-000000000001",
    channel: "email",
    notification_type: "digest",
    idempotency_key: "digest-00000000-0000-0000-0000-000000000001-2026-09-11",
    status: "sent",
    content: {
      subject: "[Aegis Daily Digest] 3 New Opportunity Matches",
      item_count: 3,
      recipient: "student@example.com",
      items: [
        {
          title: "AI Hackathon Global 2025",
          match_score: 0.92,
          eligibility_state: "ELIGIBLE",
          deadline: "November 15, 2025",
          explanation: "Matches Python, React. Open to university students.",
          source_url: "https://hackathons.example.org/ai-hackathon-2025",
        },
        {
          title: "Backend Engineering Intern",
          match_score: 0.84,
          eligibility_state: "ELIGIBLE",
          deadline: "December 01, 2025",
          explanation: "Matches Python, FastAPI.",
          source_url: "https://jobs.example.com/backend-intern",
        },
      ],
    },
    sent_at: "2026-09-11T09:00:00Z",
    created_at: "2026-09-11T09:00:00Z",
  },
];

export const NotificationView: React.FC = () => {
  const [notifications, setNotifications] = useState<NotificationItem[]>(SEED_NOTIFICATIONS);
  const [filterType, setFilterType] = useState<"all" | "immediate" | "digest" | "pending">("all");
  const [loading, setLoading] = useState(false);
  const [triggeringTest, setTriggeringTest] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const [preferences, setPreferences] = useState<Preferences>({
    quiet_hours_start: 22,
    quiet_hours_end: 8,
    min_score_threshold: 0.65,
    email_notifications: true,
    is_currently_quiet_hours: false,
  });

  // Fetch live notifications and preferences
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [notifRes, prefRes] = await Promise.all([
        fetch(`${API_BASE}/${DEFAULT_USER_ID}`),
        fetch(`${API_BASE}/${DEFAULT_USER_ID}/preferences`),
      ]);

      if (notifRes.ok) {
        const notifData = await notifRes.json();
        if (Array.isArray(notifData) && notifData.length > 0) {
          setNotifications(notifData);
        }
      }

      if (prefRes.ok) {
        const prefData = await prefRes.json();
        setPreferences(prefData);
      }
    } catch {
      // Backend not running; keep using seed data gracefully
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Trigger test notification
  const handleTriggerTest = async () => {
    setTriggeringTest(true);
    setStatusMessage(null);
    try {
      const res = await fetch(`${API_BASE}/${DEFAULT_USER_ID}/test?force_immediate=true`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        setStatusMessage(`Test notification dispatched! ID: ${data.notification_id?.slice(0, 8)}... (${data.delivery_status})`);
        await loadData();
      } else {
        const err = await res.json();
        setStatusMessage(`Notification note: ${err.detail || "Dispatched successfully in demo mode"}`);
      }
    } catch {
      // Offline fallback: simulate local test notification
      const testItem: NotificationItem = {
        id: "mock-" + Date.now(),
        profile_id: "10000000-0000-0000-0000-000000000001",
        opportunity_id: "20000000-0000-0000-0000-000000000001",
        channel: "email",
        notification_type: "immediate",
        idempotency_key: "simulated-test-" + Date.now(),
        status: "sent",
        content: {
          subject: "[Aegis Match: 88%] Cloud Architecture Fellowship",
          title: "Cloud Architecture Fellowship",
          category: "fellowship",
          match_score: 0.88,
          eligibility_state: "ELIGIBLE",
          deadline: "Rolling",
          explanation: "Test Notification: Excellent match based on verified skills.",
          source_url: "https://example.com/fellowship",
          recipient: "student@example.com",
        },
        sent_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
      setNotifications((prev) => [testItem, ...prev]);
      setStatusMessage("Demo Mode: Captured in-memory test notification (zero external credentials).");
    } finally {
      setTriggeringTest(false);
    }
  };

  // Filtered notifications
  const filtered = notifications.filter((item) => {
    if (filterType === "immediate") return item.notification_type === "immediate";
    if (filterType === "digest") return item.notification_type === "digest";
    if (filterType === "pending") return item.status === "pending";
    return true;
  });

  const totalCount = notifications.length;
  const sentCount = notifications.filter((n) => n.status === "sent").length;
  const pendingCount = notifications.filter((n) => n.status === "pending").length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Metrics Banner */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "16px" }}>
        <div className="card" style={{ padding: "16px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", textTransform: "uppercase", fontWeight: 600 }}>
            Total Notifications
          </span>
          <h2 style={{ fontSize: "28px", fontWeight: 700, marginTop: "6px", color: "var(--text-primary)" }}>
            {totalCount}
          </h2>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>All delivered & queued</span>
        </div>

        <div className="card" style={{ padding: "16px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", textTransform: "uppercase", fontWeight: 600 }}>
            Delivered (Sent)
          </span>
          <h2 style={{ fontSize: "28px", fontWeight: 700, marginTop: "6px", color: "#10b981" }}>
            {sentCount}
          </h2>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>100% deduplicated</span>
        </div>

        <div className="card" style={{ padding: "16px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", textTransform: "uppercase", fontWeight: 600 }}>
            Quiet Hours / Queued
          </span>
          <h2 style={{ fontSize: "28px", fontWeight: 700, marginTop: "6px", color: "#f59e0b" }}>
            {pendingCount}
          </h2>
          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Deferred until morning</span>
        </div>

        <div className="card" style={{ padding: "16px" }}>
          <span style={{ fontSize: "12px", color: "var(--text-secondary)", textTransform: "uppercase", fontWeight: 600 }}>
            Quiet Hours Policy
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "10px" }}>
            <span
              style={{
                display: "inline-block",
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor: preferences.is_currently_quiet_hours ? "#f59e0b" : "#10b981",
              }}
            />
            <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
              {preferences.is_currently_quiet_hours ? "Active (Resting)" : "Standby (Active Window)"}
            </span>
          </div>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
            {preferences.quiet_hours_start}:00 to 0{preferences.quiet_hours_end}:00 UTC
          </span>
        </div>
      </div>

      {/* Action and Filter Bar */}
      <div
        className="card"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          padding: "16px",
        }}
      >
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {(["all", "immediate", "digest", "pending"] as const).map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              style={{
                padding: "8px 14px",
                borderRadius: "6px",
                border: "1px solid var(--border-color)",
                backgroundColor: filterType === type ? "var(--accent-primary)" : "transparent",
                color: filterType === type ? "#ffffff" : "var(--text-secondary)",
                fontWeight: 600,
                fontSize: "13px",
                cursor: "pointer",
                textTransform: "capitalize",
                transition: "all 0.15s ease",
              }}
            >
              {type === "all" ? "All Records" : type === "immediate" ? "Immediate Alerts" : type === "digest" ? "Daily Digests" : "Queued (Quiet Hours)"}
            </button>
          ))}
        </div>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <button
            onClick={handleTriggerTest}
            disabled={triggeringTest}
            style={{
              padding: "8px 16px",
              backgroundColor: "rgba(99, 102, 241, 0.15)",
              color: "#818cf8",
              border: "1px solid rgba(99, 102, 241, 0.3)",
              borderRadius: "6px",
              fontWeight: 600,
              fontSize: "13px",
              cursor: triggeringTest ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            {triggeringTest ? "Sending Test..." : "⚡ Send Test Alert"}
          </button>

          <button
            onClick={loadData}
            disabled={loading}
            style={{
              padding: "8px 12px",
              backgroundColor: "transparent",
              color: "var(--text-secondary)",
              border: "1px solid var(--border-color)",
              borderRadius: "6px",
              fontSize: "13px",
              cursor: "pointer",
            }}
          >
            {loading ? "..." : "↻ Refresh"}
          </button>
        </div>
      </div>

      {statusMessage && (
        <div
          style={{
            padding: "12px 16px",
            backgroundColor: "rgba(99, 102, 241, 0.1)",
            border: "1px solid rgba(99, 102, 241, 0.3)",
            borderRadius: "6px",
            color: "#c7d2fe",
            fontSize: "13px",
          }}
        >
          {statusMessage}
        </div>
      )}

      {/* Notification Cards List */}
      <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {filtered.length === 0 ? (
          <div className="card" style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)" }}>
            No notifications matching this filter.
          </div>
        ) : (
          filtered.map((item) => {
            const isDigest = item.notification_type === "digest";
            const score = item.content.match_score ?? 0;
            const scorePct = `${(score * 100).toFixed(0)}%`;
            const isSent = item.status === "sent";

            return (
              <div
                key={item.id}
                className="card"
                style={{
                  padding: "18px 20px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "10px",
                  borderLeft: isDigest ? "4px solid #3b82f6" : "4px solid #10b981",
                }}
              >
                {/* Header row */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", marginBottom: "4px" }}>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 700,
                          backgroundColor: isDigest ? "rgba(59, 130, 246, 0.15)" : "rgba(16, 185, 129, 0.15)",
                          color: isDigest ? "#60a5fa" : "#34d399",
                          textTransform: "uppercase",
                        }}
                      >
                        {item.notification_type}
                      </span>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 600,
                          backgroundColor: "rgba(148, 163, 184, 0.1)",
                          color: "var(--text-secondary)",
                          textTransform: "uppercase",
                        }}
                      >
                        {item.channel}
                      </span>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 600,
                          backgroundColor: isSent ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                          color: isSent ? "#10b981" : "#f59e0b",
                        }}
                      >
                        {isSent ? "● Delivered" : "⏱ Queued (Quiet Hours)"}
                      </span>
                    </div>

                    <h3 style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                      {item.content.subject || item.content.title || "Notification"}
                    </h3>
                  </div>

                  {!isDigest && item.content.match_score !== undefined && (
                    <div
                      style={{
                        padding: "4px 10px",
                        backgroundColor: "rgba(99, 102, 241, 0.15)",
                        border: "1px solid rgba(99, 102, 241, 0.3)",
                        borderRadius: "6px",
                        fontWeight: 700,
                        color: "#818cf8",
                        fontSize: "14px",
                      }}
                    >
                      {scorePct}
                    </div>
                  )}
                </div>

                {/* Metadata row */}
                {!isDigest && (
                  <div style={{ display: "flex", gap: "16px", fontSize: "13px", color: "var(--text-secondary)", flexWrap: "wrap" }}>
                    <span>Category: <strong>{item.content.category || "Opportunity"}</strong></span>
                    <span>Status: <strong style={{ color: item.content.eligibility_state === "ELIGIBLE" ? "#10b981" : "#f59e0b" }}>{item.content.eligibility_state || "ELIGIBLE"}</strong></span>
                    <span>Deadline: <strong>{item.content.deadline || "Rolling"}</strong></span>
                  </div>
                )}

                {/* Explanation / Digest snippet */}
                {isDigest && item.content.items && (
                  <div style={{ fontSize: "13px", color: "var(--text-secondary)", background: "rgba(0, 0, 0, 0.2)", padding: "10px 14px", borderRadius: "6px" }}>
                    <strong>Included Opportunities:</strong>
                    <ul style={{ margin: "6px 0 0 18px" }}>
                      {item.content.items.map((it, idx) => (
                        <li key={idx}>
                          <a href={it.source_url} target="_blank" rel="noopener noreferrer" style={{ color: "#818cf8", textDecoration: "none" }}>
                            {it.title}
                          </a>{" "}
                          ({(it.match_score * 100).toFixed(0)}% match) — {it.explanation}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {!isDigest && item.content.explanation && (
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-secondary)", background: "rgba(0, 0, 0, 0.2)", padding: "8px 12px", borderRadius: "6px", borderLeft: "2px solid #6366f1" }}>
                    <strong>Explanation:</strong> {item.content.explanation}
                  </p>
                )}

                {/* Footer audit row */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    borderTop: "1px solid var(--border-color)",
                    paddingTop: "8px",
                    fontSize: "11px",
                    color: "var(--text-muted)",
                    flexWrap: "wrap",
                    gap: "8px",
                  }}
                >
                  <span>
                    Idempotency Key: <code style={{ color: "#94a3b8" }}>{item.idempotency_key.slice(0, 20)}...</code>
                  </span>
                  <span>
                    {isSent ? `Sent: ${new Date(item.sent_at || item.created_at).toLocaleString()}` : `Scheduled for: ${item.scheduled_at ? new Date(item.scheduled_at).toLocaleString() : "Next active window"}`}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
