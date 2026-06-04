"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  CheckCircle2,
  Loader2,
  Eye,
  EyeOff,
  Shield,
  Settings,
  User,
  Save,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/stores/authStore";
import { useUIStore } from "@/stores/uiStore";
import { apiClient } from "@/lib/api";
import { ProjectSidebar } from "@/components/ProjectSidebar";
import type { UserProfile } from "@/types/auth";

type Tab = "account" | "security" | "preferences";

const DESIGN_CODES = ["BS8110", "EC2"] as const;
const PREF_KEY = "structai-preferences";

interface Preferences {
  defaultDesignCode: "BS8110" | "EC2";
  sidebarDefault: "expanded" | "collapsed";
  chatAutoOpen: boolean;
}

function loadPrefs(): Preferences {
  if (typeof window === "undefined")
    return { defaultDesignCode: "BS8110", sidebarDefault: "expanded", chatAutoOpen: true };
  try {
    return JSON.parse(localStorage.getItem(PREF_KEY) ?? "{}") as Preferences;
  } catch {
    return { defaultDesignCode: "BS8110", sidebarDefault: "expanded", chatAutoOpen: true };
  }
}

function savePrefs(prefs: Preferences) {
  localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
}

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

// ── Account Tab ──────────────────────────────────────────────────────────────

function AccountTab({ user }: { user: UserProfile }) {
  const { setAuth, token } = useAuthStore();
  const [editing, setEditing] = useState(false);
  const [fullName, setFullName] = useState(user.full_name ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const { data } = await apiClient.patch<UserProfile>("/api/users/me", {
        full_name: fullName,
      });
      setAuth(data, token!, data.organisation);
      setEditing(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch {
      setError("Failed to save changes. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setFullName(user.full_name ?? "");
    setEditing(false);
    setError(null);
  };

  return (
    <div className="space-y-6">
      {success && (
        <div className="flex items-center gap-2 px-3 py-2 bg-success/10 border border-success/30 rounded-lg text-xs text-success animate-fade-in-up">
          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
          Profile updated successfully.
        </div>
      )}

      {/* Profile identity */}
      <div className="flex items-start gap-4">
        <div className="h-16 w-16 rounded-xl bg-primary flex items-center justify-center flex-shrink-0">
          <span className="text-xl font-semibold text-primary-foreground">
            {getInitials(user.full_name)}
          </span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-base font-semibold">{user.full_name ?? "—"}</h2>
            {user.is_verified && (
              <CheckCircle2 className="h-4 w-4 text-success flex-shrink-0" aria-label="Verified" />
            )}
            <span className="text-xs font-mono text-muted-foreground capitalize bg-muted px-2 py-0.5 rounded-md">
              {user.role}
            </span>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">{user.email}</p>
          {user.organisation && (
            <p className="text-xs font-mono text-muted-foreground mt-0.5">
              {user.organisation.name}
            </p>
          )}
        </div>
      </div>

      <div className="h-px bg-border" />

      {/* Editable fields */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Account Details</h3>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-xs text-primary hover:text-primary/80 transition-colors"
            >
              Edit
            </button>
          )}
        </div>

        {error && (
          <p className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2">
            {error}
          </p>
        )}

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Full Name</label>
            {editing ? (
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
                autoFocus
              />
            ) : (
              <p className="text-sm px-3 py-2 bg-muted/50 rounded-md text-foreground">
                {user.full_name ?? <span className="text-muted-foreground italic">Not set</span>}
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Email Address</label>
            <p className="text-sm px-3 py-2 bg-muted/30 rounded-md text-muted-foreground">
              {user.email}
              <span className="ml-2 text-[10px] font-mono">(contact admin to change)</span>
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Organisation</label>
            <p className="text-sm px-3 py-2 bg-muted/30 rounded-md text-muted-foreground">
              {user.organisation?.name ?? <span className="italic">None</span>}
            </p>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Role</label>
            <p className="text-sm px-3 py-2 bg-muted/30 rounded-md text-muted-foreground capitalize">
              {user.role}
            </p>
          </div>
        </div>

        {editing && (
          <div className="flex gap-2 pt-1">
            <button
              onClick={handleCancel}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm border border-border text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="flex items-center gap-1.5 px-4 py-2 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-60"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              Save Changes
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Security Tab ─────────────────────────────────────────────────────────────

function SecurityTab({ user }: { user: UserProfile }) {
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPw !== confirmPw) {
      setError("Passwords do not match.");
      return;
    }
    if (newPw.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await apiClient.patch("/api/users/me", { password: newPw });
      setCurrentPw("");
      setNewPw("");
      setConfirmPw("");
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch {
      setError("Failed to update password. Check your current password and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {success && (
        <div className="flex items-center gap-2 px-3 py-2 bg-success/10 border border-success/30 rounded-lg text-xs text-success animate-fade-in-up">
          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
          Password updated successfully.
        </div>
      )}

      {/* Password section */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium">Change Password</h3>

        <form onSubmit={handleChangePassword} className="space-y-3 max-w-sm">
          {error && (
            <p className="text-xs text-destructive bg-destructive/10 border border-destructive/30 rounded-md px-3 py-2">
              {error}
            </p>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Current Password</label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                value={currentPw}
                onChange={(e) => setCurrentPw(e.target.value)}
                className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors pr-9"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showPw ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">New Password</label>
            <input
              type={showPw ? "text" : "password"}
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
              placeholder="Min. 8 characters"
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground font-mono">Confirm New Password</label>
            <input
              type={showPw ? "text" : "password"}
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              className="w-full bg-muted rounded-md px-3 py-2 text-sm outline-none border border-border focus:border-primary transition-colors"
              placeholder="Repeat new password"
            />
          </div>

          <button
            type="submit"
            disabled={saving || !currentPw || !newPw || !confirmPw}
            className="flex items-center gap-2 px-4 py-2 rounded-md text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Update Password
          </button>
        </form>
      </div>

      <div className="h-px bg-border" />

      {/* 2FA */}
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium">Two-Factor Authentication</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              Add an extra layer of security to your account with a TOTP authenticator app.
            </p>
          </div>
          <span className="text-[10px] font-mono text-muted-foreground bg-muted px-2 py-1 rounded-md whitespace-nowrap flex-shrink-0">
            Coming soon
          </span>
        </div>
      </div>

      <div className="h-px bg-border" />

      {/* Account status */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium">Account Status</h3>
        <div className="grid grid-cols-2 gap-3 max-w-sm">
          <div className="px-3 py-2.5 bg-muted/50 rounded-lg">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Email</p>
            <div className="flex items-center gap-1.5 mt-1">
              {user.is_verified ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  <span className="text-xs text-success font-medium">Verified</span>
                </>
              ) : (
                <span className="text-xs text-warning font-medium">Unverified</span>
              )}
            </div>
          </div>
          <div className="px-3 py-2.5 bg-muted/50 rounded-lg">
            <p className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">Account</p>
            <div className="flex items-center gap-1.5 mt-1">
              <div className="h-1.5 w-1.5 rounded-full bg-success" />
              <span className="text-xs text-foreground font-medium capitalize">{user.role}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Preferences Tab ───────────────────────────────────────────────────────────

function PreferencesTab() {
  const [prefs, setPrefs] = useState<Preferences>(() => {
    const defaults: Preferences = {
      defaultDesignCode: "BS8110",
      sidebarDefault: "expanded",
      chatAutoOpen: true,
    };
    return { ...defaults, ...loadPrefs() };
  });
  const [saved, setSaved] = useState(false);

  const update = <K extends keyof Preferences>(key: K, value: Preferences[K]) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    savePrefs(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  };

  return (
    <div className="space-y-6">
      {saved && (
        <div className="flex items-center gap-2 px-3 py-2 bg-success/10 border border-success/30 rounded-lg text-xs text-success animate-fade-in-up">
          <CheckCircle2 className="h-3.5 w-3.5 flex-shrink-0" />
          Preference saved.
        </div>
      )}

      <div className="space-y-5 max-w-sm">
        {/* Default design code */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground font-mono block">
            Default Design Code
          </label>
          <div className="flex gap-2">
            {DESIGN_CODES.map((code) => (
              <button
                key={code}
                onClick={() => update("defaultDesignCode", code)}
                className={cn(
                  "flex-1 py-2 rounded-md text-sm font-mono font-medium border transition-colors",
                  prefs.defaultDesignCode === code
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                )}
              >
                {code}
              </button>
            ))}
          </div>
        </div>

        <div className="h-px bg-border" />

        {/* Sidebar default */}
        <div className="space-y-2">
          <label className="text-xs text-muted-foreground font-mono block">
            Sidebar Default State
          </label>
          <div className="flex gap-2">
            {(["expanded", "collapsed"] as const).map((opt) => (
              <button
                key={opt}
                onClick={() => update("sidebarDefault", opt)}
                className={cn(
                  "flex-1 py-2 rounded-md text-sm font-medium border transition-colors capitalize",
                  prefs.sidebarDefault === opt
                    ? "bg-primary text-primary-foreground border-primary"
                    : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                )}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        <div className="h-px bg-border" />

        {/* Chat auto-open */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Auto-open chat on project open</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Opens the agent chat panel automatically when you switch to a project.
            </p>
          </div>
          <button
            onClick={() => update("chatAutoOpen", !prefs.chatAutoOpen)}
            className={cn(
              "relative inline-flex h-5 w-9 items-center rounded-full border-2 transition-colors flex-shrink-0 ml-4",
              prefs.chatAutoOpen
                ? "bg-primary border-primary"
                : "bg-muted border-border"
            )}
            role="switch"
            aria-checked={prefs.chatAutoOpen}
          >
            <span
              className={cn(
                "inline-block h-3 w-3 rounded-full bg-white shadow transition-transform",
                prefs.chatAutoOpen ? "translate-x-4" : "translate-x-0.5"
              )}
            />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Profile Page ─────────────────────────────────────────────────────────────

const TABS: { id: Tab; label: string; icon: React.ElementType }[] = [
  { id: "account", label: "Account", icon: User },
  { id: "security", label: "Security", icon: Shield },
  { id: "preferences", label: "Preferences", icon: Settings },
];

export default function ProfilePage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const { setSidebarExpanded } = useUIStore();
  const [activeTab, setActiveTab] = useState<Tab>("account");

  // Collapse sidebar when entering profile
  useEffect(() => {
    setSidebarExpanded(false);
  }, [setSidebarExpanded]);

  if (!user) return null;

  return (
    <div className="h-screen flex overflow-hidden">
      <ProjectSidebar />

      <div className="flex-1 flex flex-col min-w-0 overflow-hidden bg-background">
        {/* Top bar */}
        <header className="h-12 flex items-center gap-3 px-6 border-b border-border bg-card flex-shrink-0">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
            aria-label="Back to workspace"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Workspace
          </button>
          <span className="text-muted-foreground/40">/</span>
          <span className="text-xs font-medium">Profile</span>
        </header>

        {/* Content */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="max-w-2xl mx-auto px-6 py-10">
            {/* Profile header */}
            <div className="mb-8">
              <div className="flex items-center gap-4 mb-1">
                <div className="h-12 w-12 rounded-xl bg-primary flex items-center justify-center flex-shrink-0">
                  <span className="text-base font-semibold text-primary-foreground">
                    {getInitials(user.full_name)}
                  </span>
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h1 className="text-lg font-semibold">
                      {user.full_name ?? user.email}
                    </h1>
                    {user.is_verified && (
                      <CheckCircle2 className="h-4 w-4 text-success" aria-label="Verified account" />
                    )}
                    <span className="text-xs font-mono text-muted-foreground capitalize bg-muted px-2 py-0.5 rounded-md">
                      {user.role}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{user.email}</p>
                  {user.organisation && (
                    <p className="text-xs font-mono text-muted-foreground mt-0.5">
                      {user.organisation.name}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Tab strip */}
            <div className="flex gap-0.5 mb-6 border-b border-border">
              {TABS.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  role="tab"
                  aria-selected={activeTab === id}
                  className={cn(
                    "flex items-center gap-1.5 px-4 py-2.5 text-sm transition-colors relative",
                    activeTab === id
                      ? "text-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  )}
                >
                  <Icon className="h-3.5 w-3.5 flex-shrink-0" />
                  {label}
                  {activeTab === id && (
                    <span className="absolute bottom-0 left-0 right-0 h-px bg-primary" />
                  )}
                </button>
              ))}
            </div>

            {/* Tab content */}
            <div role="tabpanel">
              {activeTab === "account" && <AccountTab user={user} />}
              {activeTab === "security" && <SecurityTab user={user} />}
              {activeTab === "preferences" && <PreferencesTab />}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
