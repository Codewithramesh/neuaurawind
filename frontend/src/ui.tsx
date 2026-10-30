import type { ReactNode } from "react";
import {
  AudioLines,
  MessageSquareText,
  ThumbsUp,
  ThumbsDown,
  Lightbulb,
  ArrowRight,
} from "lucide-react";
import { human } from "./api";
import type { Insight } from "./types";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <AudioLines size={23} />
      </span>
      <span>
        NEUAURA<span className="brand-period">.</span>
      </span>
    </div>
  );
}

export function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <span />
      {human(status)}
    </span>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return message ? (
    <div className="error-notice" role="alert">
      {message}
    </div>
  ) : null;
}

export function Empty({
  icon: Icon = MessageSquareText,
  title,
  description,
  action,
}: {
  icon?: typeof MessageSquareText;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon size={25} />
      </span>
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function SectionTitle({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow: string;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>
          {title}
          <span className="title-dot">.</span>
        </h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}

export function InsightCard({
  insight,
  onOpen,
}: {
  insight: Insight;
  onOpen: (id: string) => void;
}) {
  return (
    <article className="insight-card">
      <div className={`insight-symbol ${insight.sentiment}`}>
        {insight.sentiment === "positive" ? (
          <ThumbsUp size={18} />
        ) : insight.sentiment === "negative" ? (
          <ThumbsDown size={18} />
        ) : (
          <Lightbulb size={18} />
        )}
      </div>
      <div>
        <div className="inline-tags">
          <span className="category">{human(insight.category)}</span>
          <span className="muted">
            {insight.basis === "inferred" ? "Inference" : "Explicit feedback"} ·{" "}
            {Math.round(insight.confidence * 100)}% model estimate ·
            uncalibrated
          </span>
        </div>
        <h3>{insight.title}</h3>
        {insight.impact && (
          <p>
            <strong>Potential relevance:</strong> {insight.impact}
          </p>
        )}
        {insight.recommendation && (
          <p>
            <strong>Proposed investigation or action:</strong>{" "}
            {insight.recommendation}
          </p>
        )}
        {insight.priority_rationale && (
          <p>
            <strong>Priority rationale:</strong> {insight.priority_rationale}
          </p>
        )}
        {insight.success_metric && (
          <p>
            <strong>Measure:</strong> {insight.success_metric}
          </p>
        )}
        <p>{insight.description}</p>
        {insight.evidence[0] && (
          <blockquote>“{insight.evidence[0].quote}”</blockquote>
        )}
        {insight.uncertainty && (
          <p className="uncertainty">{insight.uncertainty}</p>
        )}
        <button
          className="text-button"
          onClick={() => onOpen(insight.conversation_id)}
        >
          View source conversation <ArrowRight size={14} />
        </button>
      </div>
    </article>
  );
}
