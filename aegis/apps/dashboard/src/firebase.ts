import { initializeApp, getApps, getApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  signOut,
  onAuthStateChanged,
  User,
  Auth,
} from "firebase/auth";

// Firebase Configuration (Uses Vite Env variables or default fallback config)
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "AIzaSyDemoAegisKey_FirebaseAuth2026",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "aegis-platform.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "aegis-platform",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "aegis-platform.appspot.com",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "102938475610",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "1:102938475610:web:aegis2026demo",
};

// Initialize Firebase App
const app = getApps().length > 0 ? getApp() : initializeApp(firebaseConfig);

// Initialize Firebase Auth & Google Provider
export const auth: Auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
googleProvider.setCustomParameters({ prompt: "select_account" });

export interface AuthState {
  user: User | null;
  loading: boolean;
  error: string | null;
}

/**
 * Trigger Google Sign In Popup
 */
export const signInWithGoogle = async (): Promise<User | null> => {
  try {
    const result = await signInWithPopup(auth, googleProvider);
    return result.user;
  } catch (error: any) {
    if (error.code === "auth/popup-closed-by-user" || error.code === "auth/cancelled-popup-request") {
      console.info("Google Sign-In popup closed by user.");
      return null;
    }
    console.warn("Firebase Auth notice:", error.message);
    
    // Only fall back to local demo profile if real API key is unconfigured
    const hasCustomKey = Boolean(import.meta.env.VITE_FIREBASE_API_KEY && !import.meta.env.VITE_FIREBASE_API_KEY.includes("Demo"));
    if (!hasCustomKey) {
      const mockUser = {
        uid: "google-firebase-user-9912",
        displayName: "Hyderabad Innovator",
        email: "student@aegis-platform.dev",
        photoURL: "https://lh3.googleusercontent.com/a/ACg8ocL-demo-avatar=s96-c",
        emailVerified: true,
      } as unknown as User;
      return mockUser;
    }
    throw error;
  }
};

/**
 * Sign Out Current Firebase User
 */
export const logoutFirebase = async (): Promise<void> => {
  await signOut(auth);
};

/**
 * Subscribe to Firebase Auth state changes
 */
export const subscribeToAuth = (callback: (user: User | null) => void) => {
  return onAuthStateChanged(auth, callback);
};
