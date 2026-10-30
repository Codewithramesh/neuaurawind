import { useState } from "react";
import { human } from "./api";
import {
  Loader2,
  Mic,
  MessageSquareText,
  ThumbsUp,
  Activity,
  ListTodo,
  AudioLines,
  ArrowRight,
  ChevronRight,
  Clock3,
  Lightbulb,
  Sparkles,
  Settings2,
} from "lucide-react";
import { useResource } from "./useResource";
import { SectionTitle, ErrorNotice, Empty, InsightCard } from "./ui";
import type { Overview, Settings } from "./types";
import type { Page } from "./navigation";

export function OverviewPage({
  onRecord,
  onOpen,
  onNavigate,
  settings,
}: {
  onRecord: () => void;
  onOpen: (id: string) => void;
  onNavigate: (p: Page) => void;
  settings: Settings | null;
}) {
  const [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const { data, error } = useResource<Overview>(
    "/overview?" +
      new URLSearchParams({
        ...(from ? { date_from: from } : {}),
        ...(to ? { date_to: to } : {}),
      }),
  );
  if (!data)
    return (
      <>
        <SectionTitle
          eyebrow="YOUR BUSINESS AT A GLANCE"
          title="A clearer picture"
          description="The signals that matter. The context behind them."
        />
        <ErrorNotice message={error} />
        <Loader2 className="spin" />
      </>
    );
  const metrics = [
    {
      label: "Conversations",
      value: data.total_conversations,
      icon: MessageSquareText,
      help: `${data.processing} in processing`,
      color: "blue",
    },
    {
      label: "Positive feedback",
      value: data.positive,
      icon: ThumbsUp,
      help: "Evidence-backed signals",
      color: "green",
    },
    {
      label: "Needs attention",
      value: data.negative,
      icon: Activity,
      help: `${data.failed} failed processing jobs`,
      color: "orange",
    },
    {
      label: "Open actions",
      value: data.open_tasks,
      icon: ListTodo,
      help: "Outstanding approved tasks",
      color: "purple",
    },
  ];
  return (
    <>
      <SectionTitle
        eyebrow="YOUR BUSINESS AT A GLANCE"
        title="A clearer picture"
        description="The signals that matter. The context behind them."
        action={
          <button className="button primary" onClick={onRecord}>
            <Mic size={17} /> New conversation
          </button>
        }
      />
      {data && (
        <div className="processing-notice">
          <div>
            <strong>{data.awaiting_review} sessions awaiting review</strong>
            <p>{data.sample_note}</p>
          </div>
        </div>
      )}
      <ErrorNotice message={error} />
      <div className="date-row">
        <span>
          <span className="live-dot" /> Your business signals
        </span>
        <span className="range-label">
          <Clock3 size={14} /> {from || to ? "Selected range" : "All time"}{" "}
          <span className="muted">· Updated automatically</span>
        </span>
      </div>
      <div className="filters">
        <label className="date-filter">
          Dashboard from
          <input
            aria-label="Dashboard from"
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label className="date-filter">
          Dashboard to
          <input
            aria-label="Dashboard to"
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button
          className="text-button"
          onClick={() => {
            setFrom("");
            setTo("");
          }}
        >
          Clear dashboard dates
        </button>
      </div>
      <div className="metrics-grid">
        {metrics.map(({ label, value, icon: Icon, help, color }) => (
          <div className="metric-card" key={label}>
            <div>
              <span>{label}</span>
              <span className={`metric-icon ${color}`}>
                <Icon size={18} />
              </span>
            </div>
            <strong>{value.toLocaleString()}</strong>
            <small>
              <span className={`tiny-dot ${color}`} />
              {help}
            </small>
          </div>
        ))}
      </div>
      {data.total_conversations === 0 && (
        <div className="welcome-banner">
          <div className="welcome-art">
            <AudioLines size={37} />
            <span className="orbit one" />
            <span className="orbit two" />
          </div>
          <div className="welcome-copy">
            <span className="eyebrow">GOOD DECISIONS START WITH LISTENING</span>
            <h2>Your next insight starts here.</h2>
            <p>
              Record an authorized conversation. We’ll connect the feedback,
              <br className="desktop-only" /> find the patterns, and help you
              decide what comes next.
            </p>
            <div className="welcome-steps">
              <span>
                <b>01</b> Capture
              </span>
              <ChevronRight size={12} />
              <span>
                <b>02</b> Understand
              </span>
              <ChevronRight size={12} />
              <span>
                <b>03</b> Act
              </span>
            </div>
          </div>
          <button className="button dark" onClick={onRecord}>
            Record your first conversation <ArrowRight size={16} />
          </button>
        </div>
      )}
      <div className="dashboard-grid">
        <section className="panel trend-panel">
          <div className="panel-heading">
            <div>
              <h2>Conversation pulse</h2>
              <p>A little context, over time.</p>
            </div>
            <span className="subtle-tag">Last 14 days</span>
          </div>
          <div className="chart-legend">
            <span>
              <i className="legend blue" /> Conversations
            </span>
            <span>
              <i className="legend green" /> Positive
            </span>
            <span>
              <i className="legend orange" /> Negative
            </span>
          </div>
          <TrendChart data={data.trend} />
          <div className="chart-caption">
            {data.total_conversations === 0
              ? "Your activity will appear here after your first conversation."
              : `${data.succeeded} conversations processed successfully · ${data.processing} queued or processing`}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Top conversation themes</h2>
              <p>What your customers bring up.</p>
            </div>
            <Lightbulb size={18} className="muted" />
          </div>
          {!data.complaints.length && !data.requests.length ? (
            <Empty
              icon={AudioLines}
              title="Patterns are waiting to emerge"
              description="Recurring complaints and requests will surface as your conversations grow."
            />
          ) : (
            <div className="themes">
              {[...data.complaints, ...data.requests]
                .slice(0, 6)
                .map((x, i) => (
                  <div key={`${x.topic}-${i}`}>
                    <span>
                      <b>{String(i + 1).padStart(2, "0")}</b>
                      {human(x.topic)}
                    </span>
                    <span className="subtle-tag">{x.count} sessions</span>
                  </div>
                ))}
            </div>
          )}
          <button className="panel-link" onClick={() => onNavigate("insights")}>
            Explore all insights <ArrowRight size={14} />
          </button>
        </section>
      </div>
      <section className="panel recent-panel">
        <div className="panel-heading">
          <div>
            <h2>
              From conversation to clarity <Sparkles size={16} />
            </h2>
            <p>Fresh insights, with the evidence behind them.</p>
          </div>
          <button
            className="text-button"
            onClick={() => onNavigate("insights")}
          >
            View all insights <ArrowRight size={14} />
          </button>
        </div>
        {data.recent_insights.length ? (
          data.recent_insights
            .slice(0, 3)
            .map((i) => <InsightCard key={i.id} insight={i} onOpen={onOpen} />)
        ) : (
          <div className="insight-empty">
            <span className="insight-empty-icon">
              <Sparkles size={24} />
            </span>
            <div>
              <h3>Real conversations. Meaningful insights.</h3>
              <p>
                Customer preferences, operational issues, and opportunities will
                appear here.
                <br />
                Every insight is linked to its source, so you can see the whole
                story.
              </p>
            </div>
            <span className="outlined-tag">No insights yet</span>
          </div>
        )}
      </section>
      {settings &&
        (!settings.transcription.ready || !settings.extraction.ready) && (
          <div className="setup-strip">
            <span className="setup-symbol">
              <Settings2 size={18} />
            </span>
            <div>
              <strong>Finish connecting your intelligence engines</strong>
              <p>
                {!settings.transcription.ready
                  ? "Speech model needs installation. "
                  : ""}
                {!settings.extraction.ready ? "AI provider needs setup. " : ""}
                Recordings stay visible if processing needs your attention.
              </p>
            </div>
            <button
              className="text-button"
              onClick={() => onNavigate("settings")}
            >
              View setup <ArrowRight size={14} />
            </button>
          </div>
        )}
    </>
  );
}

export function TrendChart({ data }: { data: Overview["trend"] }) {
  const maximum = Math.max(
    4,
    ...data.flatMap((d) => [d.conversations, d.positive, d.negative]),
  );
  return (
    <div className="trend-chart">
      <div className="y-axis">
        {[maximum, Math.round(maximum / 2), 0].map((n, i) => (
          <span key={i}>{n}</span>
        ))}
      </div>
      <div className="chart-main">
        <div className="grid-line top" />
        <div className="grid-line middle" />
        <div className="grid-line bottom" />
        <svg
          viewBox="0 0 700 145"
          role="img"
          aria-label="Conversation and feedback counts over the last 14 days"
          preserveAspectRatio="none"
        >
          {(["conversations", "positive", "negative"] as const).map(
            (key, i) => (
              <polyline
                key={key}
                points={data
                  .map(
                    (d, j) =>
                      `${(j * 700) / 13},${140 - (d[key] / maximum) * 125}`,
                  )
                  .join(" ")}
                fill="none"
                stroke={["#7767e9", "#5e9e84", "#dba271"][i]}
                strokeWidth="2.5"
                strokeDasharray={i > 0 ? "4 5" : undefined}
              />
            ),
          )}
        </svg>
        <div className="x-axis">
          {data
            .filter((_, i) => i % 3 === 0 || i === 13)
            .map((d) => (
              <span key={d.date}>
                {new Date(d.date + "T12:00:00").toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                })}
              </span>
            ))}
        </div>
      </div>
      <details className="chart-data">
        <summary>View chart data</summary>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Conversations</th>
              <th>Positive</th>
              <th>Negative</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.date}>
                <td>{d.date}</td>
                <td>{d.conversations}</td>
                <td>{d.positive}</td>
                <td>{d.negative}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}
