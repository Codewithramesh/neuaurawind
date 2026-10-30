import { useState, useEffect, useCallback } from "react";
import {
  LayoutDashboard,
  MessageSquareText,
  Lightbulb,
  ListTodo,
  Cpu,
  ShieldCheck,
  Settings2,
  LogOut,
  Menu,
  ChevronRight,
  CircleHelp,
  Loader2,
} from "lucide-react";
import { api, setCSRF, setStoreScope, human } from "./api";
import type { UserContext, Settings } from "./types";
import type { Page } from "./navigation";
import { Brand, ErrorNotice } from "./ui";
import { Auth } from "./Auth";
import { OverviewPage } from "./Overview";
import { ConversationsPage } from "./Conversations";
import { InsightsPage } from "./Insights";
import { TasksPage } from "./Tasks";
import { DevicesPage } from "./Devices";
import { SettingsPage } from "./Settings";
import { Recorder } from "./Recorder";
import { ParticipantConsent } from "./ParticipantConsent";
import { GovernanceSettings } from "./GovernanceSettings";
import { ConversationPanel } from "./ConversationPanel";

const navigation: {
  page: Page;
  label: string;
  icon: typeof LayoutDashboard;
}[] = [
  { page: "overview", label: "Overview", icon: LayoutDashboard },
  { page: "conversations", label: "Conversations", icon: MessageSquareText },
  { page: "insights", label: "Insights", icon: Lightbulb },
  { page: "tasks", label: "Action center", icon: ListTodo },
  { page: "devices", label: "Devices", icon: Cpu },
];

export default function App() {
  const [hash, setHash] = useState(location.hash);
  useEffect(() => {
    const change = () => setHash(location.hash);
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  if (hash.startsWith("#consent/"))
    return (
      <main className="consent-page">
        <ParticipantConsent token={hash.slice(9)} />
      </main>
    );
  return <Workspace />;
}
function Workspace() {
  const [selectedStore, setSelectedStore] = useState("");
  const [context, setContext] = useState<UserContext | null>(null),
    [initializing, setInitializing] = useState(true),
    [bootstrap, setBootstrap] = useState(false),
    [page, setPage] = useState<Page>("overview"),
    [recording, setRecording] = useState(false),
    [detail, setDetail] = useState<string | null>(null),
    [menu, setMenu] = useState(false);
  const [connected, setConnected] = useState(true);
  useEffect(() => {
    if (!context) return;
    const check = async () => {
      try {
        await api("/health");
        setConnected(true);
      } catch {
        setConnected(false);
      }
    };
    const timer = setInterval(() => {
      if (!document.hidden) void check();
    }, 15000);
    return () => clearInterval(timer);
  }, [context]);
  const [settings, setSettings] = useState<Settings | null>(null),
    [notice, setNotice] = useState("");
  const loadContext = useCallback(async () => {
    const [me, setup] = await Promise.all([
      api<UserContext>("/auth/me"),
      api<Settings>("/settings"),
    ]);
    setCSRF(me.csrf);
    setContext(me);
    setSelectedStore((current) => {
      const next = me.stores?.some((s) => s.id === current)
        ? current
        : me.stores?.[0]?.id || "";
      setStoreScope(next);
      return next;
    });
    setSettings(setup);
  }, []);
  useEffect(() => {
    (async () => {
      try {
        const health = await api<{ bootstrap_required: boolean }>("/health");
        setBootstrap(health.bootstrap_required);
        if (!health.bootstrap_required) await loadContext();
      } catch (e) {
        if ((e as { status?: number }).status !== 401)
          setNotice((e as Error).message);
      } finally {
        setInitializing(false);
      }
    })();
  }, [loadContext]);
  if (initializing)
    return (
      <div className="loading-screen">
        <Brand />
        <Loader2 className="spin" />
        <p>Connecting to your workspace…</p>
      </div>
    );
  if (!context)
    return (
      <Auth
        bootstrap={bootstrap}
        notice={notice}
        onReady={async () => {
          setBootstrap(false);
          await loadContext();
        }}
      />
    );
  const open = (id: string) => {
    setDetail(id);
    setRecording(false);
  };
  const navigate = (target: Page) => {
    setPage(target);
    setMenu(false);
  };
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className={`sidebar ${menu ? "visible" : ""}`}>
        <Brand />
        <div className="workspace-switch">
          <div className="workspace-avatar">
            {context.organization.name[0].toUpperCase()}
          </div>
          <div>
            <strong>{context.organization.name}</strong>
            <small>Business workspace</small>
          </div>
          <ChevronRight size={15} />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {navigation.map(({ page: p, label, icon: Icon }) => (
            <button
              key={p}
              className={page === p ? "active" : ""}
              onClick={() => navigate(p)}
              aria-current={page === p ? "page" : undefined}
            >
              <Icon size={19} />
              <span>{label}</span>
              {p === "insights" && <span className="new-tag">AI</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <ShieldCheck size={21} />
            <strong>Built for trust</strong>
            <p>
              Authorized conversations.
              <br />
              Evidence you can verify.
            </p>
            <span>
              <i />{" "}
              {settings?.extraction.cloud_enabled
                ? "Cloud processing enabled"
                : "Local processing"}
            </span>
          </div>
          <button
            className={`settings-nav ${page === "settings" ? "active" : ""}`}
            onClick={() => navigate("settings")}
          >
            <Settings2 size={19} /> Settings
          </button>
          <button
            className="user-profile"
            onClick={async () => {
              try {
                await api("/auth/logout", { method: "POST" });
                setCSRF("");
                setStoreScope("");
                setSelectedStore("");
                setContext(null);
                setNotice("");
              } catch (error) {
                setNotice((error as Error).message);
              }
            }}
            title="Sign out"
          >
            <span className="user-avatar">
              {context.user.email[0].toUpperCase()}
            </span>
            <span>
              <strong>{human(context.user.role || "staff")}</strong>
              <small>{context.user.email}</small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      {menu && (
        <button
          className="sidebar-scrim"
          aria-label="Close navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <div className="workspace-main">
        <header className="topbar">
          <button
            className="icon-button mobile-menu"
            onClick={() => setMenu(true)}
            aria-label="Open navigation"
          >
            <Menu size={22} />
          </button>
          <div className="breadcrumb">
            Workspace <ChevronRight size={13} />{" "}
            <strong>{page === "tasks" ? "Action center" : human(page)}</strong>
          </div>
          <div className="topbar-right">
            <label className="store-picker">
              Store
              <select
                aria-label="Selected store"
                value={selectedStore}
                disabled={recording || !!detail}
                onChange={(e) => {
                  setStoreScope(e.target.value);
                  setSelectedStore(e.target.value);
                }}
              >
                {context.stores?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <span className={`live-pill ${connected ? "" : "disconnected"}`}>
              <i /> {connected ? "Workspace connected" : "Connection lost"}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              onClick={() => navigate("settings")}
              aria-label="Setup and privacy help"
            >
              <CircleHelp size={18} />
            </button>
            <div className="avatar-small">
              {context.user.email[0].toUpperCase()}
            </div>
          </div>
        </header>
        <main id="main" key={selectedStore}>
          <ErrorNotice message={notice} />
          {page === "overview" && (
            <OverviewPage
              onRecord={() => setRecording(true)}
              onOpen={open}
              onNavigate={navigate}
              settings={settings}
            />
          )}
          {page === "conversations" && (
            <ConversationsPage
              onRecord={() => setRecording(true)}
              onOpen={open}
            />
          )}
          {page === "insights" && <InsightsPage onOpen={open} />}
          {page === "tasks" && <TasksPage onOpen={open} />}
          {page === "devices" && (
            <DevicesPage
              canAdmin={["owner", "admin"].includes(context.user.role)}
            />
          )}
          {page === "settings" && (
            <GovernanceSettings settings={settings} onChange={loadContext} />
          )}
          {page === "settings" && (
            <SettingsPage
              onChange={async () => {
                await loadContext();
              }}
            />
          )}
        </main>
        <footer className="app-footer">
          <span>NEUAURA · Conversation intelligence</span>
          <span>
            <ShieldCheck size={12} /> Your workspace, your data.
          </span>
        </footer>
      </div>
      {recording && (
        <Recorder
          settings={
            settings
              ? {
                  ...settings,
                  stores: [...settings.stores].sort(
                    (a, b) =>
                      Number(b.id === selectedStore) -
                      Number(a.id === selectedStore),
                  ),
                }
              : null
          }
          onClose={() => setRecording(false)}
          onComplete={open}
        />
      )}
      {detail && (
        <ConversationPanel
          id={detail}
          canReview={["owner", "admin", "manager"].includes(context.user.role)}
          onClose={() => setDetail(null)}
          onDeleted={() => setDetail(null)}
        />
      )}
    </div>
  );
}
