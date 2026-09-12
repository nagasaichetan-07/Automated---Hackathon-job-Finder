import React, { useState, useEffect } from "react";
import { User } from "firebase/auth";
import { signInWithGoogle, logoutFirebase, subscribeToAuth, checkRedirectResult, triggerQuickLogin } from "./firebase";
import { FeedView } from "./components/FeedView";
import { HealthView } from "./components/HealthView";
import { NotificationView } from "./components/NotificationView";
import { ProfileView } from "./components/ProfileView";
import { RepairView } from "./components/RepairView";
import { SourceView } from "./components/SourceView";

import { getApiBaseUrl } from "./config";

type Tab = "feed" | "saved" | "sources" | "profile" | "notifications" | "repair" | "health";

interface HealthStatus {
  status: "checking" | "live" | "offline";
  environment?: string;
  timestamp?: string;
}

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>("feed");
  const [apiHealth, setApiHealth] = useState<HealthStatus>({ status: "checking" });
  const [authUser, setAuthUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    // Check for redirect result on return
    checkRedirectResult().then((user) => {
      if (user) setAuthUser(user);
    });

    // Subscribe to Firebase Auth state
    const unsubscribe = subscribeToAuth((user) => {
      setAuthUser(user);
    });

    // Attempt to probe API health; gracefully handle if unreachable
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);

    fetch(`${getApiBaseUrl()}/health/live`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error("API returned non-200");
        return res.json();
      })
      .then((data) => {
        setApiHealth({
          status: "live",
          environment: data.environment,
          timestamp: data.timestamp,
        });
      })
      .catch(() => {
        // Fallback gracefully without breaking UI
        setApiHealth({ status: "offline" });
      })
      .finally(() => {
        clearTimeout(timeoutId);
      });

    return () => {
      unsubscribe();
      clearTimeout(timeoutId);
    };
  }, []);

  const handleGoogleSignIn = async () => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      const user = await signInWithGoogle();
      if (user) {
        setAuthUser(user);
      }
    } catch (err: any) {
      setAuthError(err.message || "Failed to sign in with Google");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleSignOut = async () => {
    try {
      await logoutFirebase();
      setAuthUser(null);
    } catch (err: any) {
      console.error("Sign out error:", err);
    }
  };

  return (
    <div className="dashboard-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">A</div>
          <div className="brand-name">Aegis</div>
        </div>
        <ul className="nav-links">
          <li
            className={`nav-item ${activeTab === "feed" ? "active" : ""}`}
            onClick={() => setActiveTab("feed")}
          >
            Feed / Opportunities
          </li>
          <li
            className={`nav-item ${activeTab === "saved" ? "active" : ""}`}
            onClick={() => setActiveTab("saved")}
          >
            Saved
          </li>
          <li
            className={`nav-item ${activeTab === "sources" ? "active" : ""}`}
            onClick={() => setActiveTab("sources")}
          >
            Sources
          </li>
          <li
            className={`nav-item ${activeTab === "profile" ? "active" : ""}`}
            onClick={() => setActiveTab("profile")}
          >
            Profile & Résumé
          </li>
          <li
            className={`nav-item ${activeTab === "notifications" ? "active" : ""}`}
            onClick={() => setActiveTab("notifications")}
          >
            Notifications
          </li>
          <li
            className={`nav-item ${activeTab === "repair" ? "active" : ""}`}
            onClick={() => setActiveTab("repair")}
          >
            Self-Healing Repair
          </li>
          <li
            className={`nav-item ${activeTab === "health" ? "active" : ""}`}
            onClick={() => setActiveTab("health")}
          >
            System Health
          </li>
        </ul>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="top-bar">
          <h2 style={{ fontSize: "1.1rem", fontWeight: 600 }}>
            {activeTab === "repair" ? "Self-Healing Repair Engine" : activeTab.charAt(0).toUpperCase() + activeTab.slice(1)}
          </h2>
          
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            {apiHealth.status === "live" ? (
              <span className="status-badge live">● API Connected</span>
            ) : apiHealth.status === "offline" ? (
              <span className="status-badge offline">○ API Offline (Standby)</span>
            ) : (
              <span className="status-badge">Checking API...</span>
            )}

            {/* Firebase Auth Google Login Section */}
            {authUser ? (
              <div className="user-profile-bar">
                <img
                  src={authUser.photoURL || "https://lh3.googleusercontent.com/a/default-user"}
                  alt="Avatar"
                  className="user-avatar"
                  onError={(e) => {
                    (e.target as HTMLImageElement).src = "https://ui-avatars.com/api/?name=" + encodeURIComponent(authUser.displayName || "User");
                  }}
                />
                <span className="user-name">{authUser.displayName || authUser.email?.split("@")[0] || "Logged In User"}</span>
                <button onClick={handleSignOut} className="logout-btn" title="Sign out from Firebase">
                  ✕
                </button>
              </div>
            ) : (
              <button onClick={handleGoogleSignIn} disabled={authLoading} className="google-auth-btn">
                <svg width="18" height="18" viewBox="0 0 24 24">
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
                  />
                </svg>
                {authLoading ? "Signing in..." : "Sign in with Google"}
              </button>
            )}
          </div>
        </header>

        {authError && (
          <div style={{ background: "rgba(239, 68, 68, 0.15)", color: "#f87171", padding: "10px 32px", fontSize: "0.85rem", borderBottom: "1px solid rgba(239, 68, 68, 0.3)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>⚠️ Auth Alert: {authError}</span>
            <button
              onClick={() => {
                const u = triggerQuickLogin();
                setAuthUser(u);
                setAuthError(null);
              }}
              style={{ background: "rgba(255,255,255,0.15)", border: "1px solid rgba(255,255,255,0.3)", color: "#fff", padding: "4px 10px", borderRadius: "4px", fontSize: "0.75rem", cursor: "pointer", marginLeft: "12px" }}
            >
              Use Quick Dev Login
            </button>
          </div>
        )}

        <section className="content-body">
          {activeTab === "feed" && <FeedView />}

          {activeTab === "saved" && (
            <div className="card">
              <h3 className="card-title">Saved Opportunities</h3>
              <p className="card-desc">Bookmarked opportunities awaiting application or follow-up.</p>
            </div>
          )}

          {activeTab === "sources" && <SourceView />}

          {activeTab === "profile" && <ProfileView />}

          {activeTab === "notifications" && <NotificationView />}

          {activeTab === "repair" && <RepairView />}

          {activeTab === "health" && <HealthView />}
        </section>
      </main>
    </div>
  );
};


export default App;

