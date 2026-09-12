/**
 * Dynamically resolves the API Base URL.
 * When deployed on Vercel/production, uses relative paths (current origin) to prevent
 * browser Local Network Access (LNA) security prompts.
 * When running locally, defaults to http://localhost:8000.
 */
export const getApiBaseUrl = (): string => {
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1") {
      return ""; // Use relative origin on Vercel deployment
    }
  }
  return import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
};
