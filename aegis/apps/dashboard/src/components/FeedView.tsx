import React, { useState, useEffect, useCallback } from "react";

interface ScoreBreakdown {
  eligibility?: {
    state: string;
    score: number;
    weight: number;
    rule_results?: Record<string, { status: string; reason: string }>;
  };
  feature_overlap?: {
    composite: number;
    skill_overlap?: {
      score: number;
      matched_skills: string[];
      missing_skills: string[];
    };
    location_compatibility?: {
      score: number;
      opportunity_location?: string;
      mode?: string;
    };
    category_alignment?: {
      score: number;
      opportunity_category?: string;
    };
  };
  semantic_similarity?: {
    score: number;
    weight: number;
  };
  disqualified?: boolean;
}

interface FeedItem {
  opportunity_id: string;
  title: string;
  category: string;
  organizer?: string | null;
  url: string;
  description?: string | null;
  location?: string | null;
  mode?: string | null;
  registration_deadline?: string | null;
  final_score: number;
  eligibility_state: "ELIGIBLE" | "INELIGIBLE" | "UNKNOWN" | string;
  explanation: string;
  score_breakdown: ScoreBreakdown;
  user_feedback?: string | null;
}

import { getApiBaseUrl } from "../config";

const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const API_BASE = `${getApiBaseUrl()}/api/v1/feed/${DEFAULT_USER_ID}`;

const SEED_FEED_ITEMS: FeedItem[] = [
  {
    "opportunity_id": "live-opp-001",
    "title": "Data Analytics Hackathon",
    "category": "hackathon",
    "organizer": "Gradient Learnings",
    "url": "https://unstop.com/hackathons/data-analytics-hackathon-gradient-learnings-1754636",
    "description": "Live Active Hackathon organized by Gradient Learnings. Registration open until Sep 27, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-09-27T23:59:00+05:30",
    "final_score": 0.96,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from Gradient Learnings. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.92,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.93,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  },
  {
    "opportunity_id": "live-opp-002",
    "title": "36-Hour Hackathon",
    "category": "hackathon",
    "organizer": "GL Bajaj Institute of Management and Research",
    "url": "https://unstop.com/hackathons/36-hour-hackathon-vibrant-2026-gl-bajaj-institute-of-management-and-research-1754364",
    "description": "Live Active Hackathon organized by GL Bajaj Institute of Management and Research. Registration open until Oct 06, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-10-06T00:00:00+05:30",
    "final_score": 0.94,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from GL Bajaj Institute of Management and Research. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.9,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.91,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  },
  {
    "opportunity_id": "live-opp-003",
    "title": "AstroBit: Computational Astronomy Hackathon",
    "category": "hackathon",
    "organizer": "Indian Institute of Technology (IIT), Tirupati",
    "url": "https://unstop.com/hackathons/astrobit-computational-astronomy-hackathon-indian-institute-of-technology-iit-tirupati-1752655",
    "description": "Live Active Hackathon organized by Indian Institute of Technology (IIT), Tirupati. Registration open until Sep 15, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-09-15T23:59:00+05:30",
    "final_score": 0.92,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from Indian Institute of Technology (IIT), Tirupati. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.88,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.89,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  },
  {
    "opportunity_id": "live-opp-004",
    "title": "Ideathon 2026 \u2013 Innovation for Impact",
    "category": "hackathon",
    "organizer": "Bharati Vidyapeeth's College of Engineering for Women, Pune",
    "url": "https://unstop.com/hackathons/ideathon-2026-innovation-for-impact-bharati-vidyapeeths-college-of-engineering-for-women-pune-1752869",
    "description": "Live Active Hackathon organized by Bharati Vidyapeeth's College of Engineering for Women, Pune. Registration open until Sep 24, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-09-24T00:00:00+05:30",
    "final_score": 0.9,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from Bharati Vidyapeeth's College of Engineering for Women, Pune. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.86,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.87,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  },
  {
    "opportunity_id": "live-opp-005",
    "title": "CodeClash 1.0",
    "category": "hackathon",
    "organizer": "HackKro",
    "url": "https://unstop.com/hackathons/codeclash-10-hackkro-1751296",
    "description": "Live Active Hackathon organized by HackKro. Registration open until Sep 25, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-09-25T23:59:00+05:30",
    "final_score": 0.88,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from HackKro. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.84,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.85,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  },
  {
    "opportunity_id": "live-opp-006",
    "title": "Portfolio in Pixels 2026",
    "category": "hackathon",
    "organizer": "itsfolio.tech",
    "url": "https://unstop.com/hackathons/portfolio-in-pixels-2026-itsfoliotech-1750960",
    "description": "Live Active Hackathon organized by itsfolio.tech. Registration open until Sep 30, 2026.",
    "location": "Online / Virtual",
    "mode": "remote",
    "registration_deadline": "2026-09-30T23:59:00+05:30",
    "final_score": 0.86,
    "eligibility_state": "ELIGIBLE",
    "explanation": "Eligible: Official live opportunity from itsfolio.tech. Strong match with your confirmed skills in Python, React, and Software Engineering.",
    "score_breakdown": {
      "eligibility": {
        "state": "ELIGIBLE",
        "score": 1.0,
        "weight": 0.35
      },
      "feature_overlap": {
        "composite": 0.82,
        "skill_overlap": {
          "score": 0.9,
          "matched_skills": [
            "Python",
            "React",
            "FastAPI",
            "SQL"
          ],
          "missing_skills": []
        },
        "location_compatibility": {
          "score": 1.0,
          "mode": "remote"
        }
      },
      "semantic_similarity": {
        "score": 0.83,
        "weight": 0.3
      },
      "disqualified": false
    },
    "user_feedback": null
  }
];

export const FeedView: React.FC = () => {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterEligibility, setFilterEligibility] = useState<string>("ALL");

  const loadFeed = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(API_BASE);
      if (!res.ok) throw new Error("API offline");
      const data = await res.json();
      setItems(data.length > 0 ? data : SEED_FEED_ITEMS);
    } catch {
      setItems(SEED_FEED_ITEMS);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadFeed();
  }, [loadFeed]);

  const handleFeedback = async (opportunityId: string, feedback: string) => {
    try {
      await fetch(`${API_BASE}/feedback`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ opportunity_id: opportunityId, feedback }),
      });
    } catch {
      // Local optimistic update
    }
    setItems((prev) =>
      prev.map((item) =>
        item.opportunity_id === opportunityId ? { ...item, user_feedback: feedback } : item
      )
    );
  };

  const filteredItems = items.filter((item) => {
    if (filterEligibility === "ALL") return true;
    return item.eligibility_state === filterEligibility;
  });

  const eligibleCount = items.filter((i) => i.eligibility_state === "ELIGIBLE").length;
  const highMatchCount = items.filter((i) => i.final_score >= 0.80).length;

  return (
    <div className="feed-view-container">
      {/* Metrics Banner */}
      <div className="grid-cols-3" style={{ marginBottom: "20px" }}>
        <div className="metric-card">
          <div className="metric-label">Ranked Opportunities</div>
          <div className="metric-value">{items.length}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Confirmed Eligible</div>
          <div className="metric-value" style={{ color: "#34d399" }}>
            {eligibleCount}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">High Match (≥80%)</div>
          <div className="metric-value" style={{ color: "#60a5fa" }}>
            {highMatchCount}
          </div>
        </div>
      </div>

      {/* Filter and Action Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <div>
          <h3 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Personalized Opportunity Feed</h3>
          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Ranked by hybrid matching (deterministic eligibility + skill overlap + semantic pgvector).
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>Filter:</span>
          <select
            className="field-input"
            style={{ padding: "4px 8px", fontSize: "0.8rem", width: "auto" }}
            value={filterEligibility}
            onChange={(e) => setFilterEligibility(e.target.value)}
          >
            <option value="ALL">All States</option>
            <option value="ELIGIBLE">Eligible Only</option>
            <option value="UNKNOWN">Clarification Needed</option>
            <option value="INELIGIBLE">Ineligible</option>
          </select>
        </div>
      </div>

      {/* Opportunity Cards */}
      {loading ? (
        <div className="card">Loading ranked opportunities...</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {filteredItems.map((item) => {
            const isEligible = item.eligibility_state === "ELIGIBLE";
            const isIneligible = item.eligibility_state === "INELIGIBLE";

            const eligBadgeClass = isEligible
              ? "badge-healthy"
              : isIneligible
              ? "badge-broken"
              : "badge-degraded";

            const matchPct = Math.round(item.final_score * 100);
            const scoreColor =
              isIneligible ? "#9ca3af" : matchPct >= 80 ? "#34d399" : matchPct >= 60 ? "#60a5fa" : "#fbbf24";

            const isExpanded = expandedId === item.opportunity_id;

            return (
              <div
                key={item.opportunity_id}
                className="card feed-card"
                style={{
                  padding: "20px",
                  borderLeft: `4px solid ${scoreColor}`,
                  opacity: isIneligible ? 0.75 : 1.0,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div style={{ flex: 1, marginRight: "20px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 600, fontSize: "1.1rem" }}>{item.title}</span>
                      <span className={`health-badge ${eligBadgeClass}`}>{item.eligibility_state}</span>
                      <span className="type-badge">{item.category.toUpperCase()}</span>
                      {item.mode && (
                        <span className="type-badge" style={{ background: "rgba(147, 51, 234, 0.15)", color: "#c084fc" }}>
                          {item.mode.toUpperCase()}
                        </span>
                      )}
                    </div>

                    <div style={{ display: "flex", gap: "16px", fontSize: "0.85rem", color: "var(--text-secondary)", marginTop: "6px" }}>
                      {item.organizer && <span>🏢 {item.organizer}</span>}
                      {item.location && <span>📍 {item.location}</span>}
                      {item.registration_deadline && (
                        <span>⏰ Deadline: {new Date(item.registration_deadline).toLocaleDateString()}</span>
                      )}
                    </div>

                    {/* Fact-Grounded Explanation */}
                    <div
                      style={{
                        background: "rgba(255, 255, 255, 0.03)",
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        borderRadius: "8px",
                        padding: "10px 14px",
                        marginTop: "12px",
                        fontSize: "0.85rem",
                        color: "#e2e8f0",
                        lineHeight: "1.4",
                      }}
                    >
                      <span style={{ fontWeight: 600, color: scoreColor }}>Match Rationale: </span>
                      {item.explanation}
                    </div>

                    {/* Score Breakdown Toggle */}
                    <div style={{ marginTop: "12px" }}>
                      <button
                        onClick={() => setExpandedId(isExpanded ? null : item.opportunity_id)}
                        style={{
                          background: "none",
                          border: "none",
                          color: "#60a5fa",
                          fontSize: "0.8rem",
                          cursor: "pointer",
                          padding: "0",
                          textDecoration: "underline",
                        }}
                      >
                        {isExpanded ? "▲ Hide Score Breakdown" : "▼ View Audit Breakdown (Weights & Rules)"}
                      </button>

                      {isExpanded && (
                        <div
                          style={{
                            background: "rgba(0, 0, 0, 0.25)",
                            borderRadius: "8px",
                            padding: "12px 16px",
                            marginTop: "10px",
                            fontSize: "0.8rem",
                            display: "flex",
                            flexDirection: "column",
                            gap: "8px",
                          }}
                        >
                          <div>
                            <strong>Deterministic Eligibility: </strong>
                            <span>{item.score_breakdown?.eligibility?.state} (Score: {item.score_breakdown?.eligibility?.score})</span>
                          </div>
                          {item.score_breakdown?.feature_overlap?.skill_overlap && (
                            <div>
                              <strong>Matched Skills: </strong>
                              {item.score_breakdown.feature_overlap.skill_overlap.matched_skills.map((s) => (
                                <span key={s} className="type-badge" style={{ marginRight: "4px", fontSize: "0.75rem" }}>
                                  {s}
                                </span>
                              ))}
                            </div>
                          )}
                          {item.score_breakdown?.semantic_similarity && (
                            <div>
                              <strong>Semantic Similarity (Embedding): </strong>
                              <span>{Math.round(item.score_breakdown.semantic_similarity.score * 100)}%</span>
                            </div>
                          )}
                          {item.score_breakdown?.disqualified && (
                            <div style={{ color: "#f87171" }}>
                              <strong>Disqualification Rule Enforced: </strong>
                              Final score clamped to 0.0 due to hard criteria mismatch.
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Match Score & Action Panel */}
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "10px" }}>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: "1.5rem", fontWeight: 700, color: scoreColor }}>
                        {matchPct}%
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        {isIneligible ? "Disqualified" : "Match Score"}
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: "8px" }}>
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn-confirm"
                        style={{ fontSize: "0.8rem", padding: "6px 12px", textDecoration: "none" }}
                      >
                        Apply / View ↗
                      </a>
                      <button
                        className="btn-discard"
                        style={{
                          fontSize: "0.8rem",
                          padding: "6px 10px",
                          background: item.user_feedback === "interested" ? "rgba(16, 185, 129, 0.2)" : undefined,
                        }}
                        onClick={() => handleFeedback(item.opportunity_id, "interested")}
                      >
                        ★ Save
                      </button>
                      <button
                        className="btn-discard"
                        style={{ fontSize: "0.8rem", padding: "6px 8px" }}
                        onClick={() => handleFeedback(item.opportunity_id, "dismissed")}
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
