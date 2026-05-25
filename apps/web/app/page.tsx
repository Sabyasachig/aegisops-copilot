import {
  ArrowUpRight,
  BrainCircuit,
  Clock3,
  Layers3,
  Radar,
  ShieldAlert,
  Sparkles,
  TriangleAlert
} from "lucide-react";

import {
  agentStages,
  dashboardMetrics,
  operatingPrinciples
} from "../lib/dashboard-data";
import { loadDashboardSnapshot } from "../lib/api";

export default async function HomePage() {
  const snapshot = await loadDashboardSnapshot();

  return (
    <main className="dashboard-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <span className="eyebrow">AegisOps Copilot</span>
          <h1>Multi-agent incident response with human control.</h1>
          <p>
            Triage faster, coordinate evidence, and draft mitigation plans without letting the model act unsafely.
            LangGraph drives the workflow, LangSmith records the trail, and the UI keeps the operator in command.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="#incidents">
              Review active incidents
              <ArrowUpRight size={18} />
            </a>
            <a className="secondary-action" href="#architecture">
              Inspect architecture
            </a>
          </div>
        </div>

        <div className="hero-status-card">
          <div className="status-header">
            <div>
              <span className="status-label">Live command channel</span>
              <strong>Incident #INC-2081</strong>
            </div>
            <span className="status-pill live">Tracing active</span>
          </div>
          <div className="status-grid">
            <div>
              <span>Workflow step</span>
              <strong>Drafting mitigation plan</strong>
            </div>
            <div>
              <span>Next gate</span>
              <strong>Human approval required</strong>
            </div>
            <div>
              <span>Primary owner</span>
              <strong>Revenue Engineering</strong>
            </div>
            <div>
              <span>Current trace</span>
              <strong>{snapshot.provider ? `${snapshot.provider.provider} / ${snapshot.provider.model_name}` : "Groq / llama-3.1-8b-instant"}</strong>
            </div>
          </div>
        </div>
      </section>

      <section className="metric-grid" aria-label="Key metrics">
        {dashboardMetrics.map((metric) => (
          <article className={`metric-card ${metric.tone}`} key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <p>{metric.delta}</p>
          </article>
        ))}
      </section>

      <section className="workspace-grid" id="incidents">
        <div className="incident-column">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Incident queue</span>
              <h2>Active work in the command room.</h2>
            </div>
            <span className="section-chip">
              <Clock3 size={14} />
              Updated in real time
            </span>
          </div>

          <div className="incident-list">
            {snapshot.incidents.map((incident) => (
              <article className="incident-card" key={incident.id}>
                <div className="incident-card-top">
                  <div>
                    <span className={`severity severity-${incident.severity}`}>{incident.severity}</span>
                    <h3>{incident.title}</h3>
                    <p>{incident.summary}</p>
                  </div>
                  <span className="incident-id">{incident.id}</span>
                </div>

                <div className="incident-meta">
                  <div>
                    <span>Service</span>
                    <strong>{incident.service}</strong>
                  </div>
                  <div>
                    <span>Status</span>
                    <strong>{incident.status}</strong>
                  </div>
                  <div>
                    <span>Owner</span>
                    <strong>{incident.owner}</strong>
                  </div>
                  <div>
                    <span>Updated</span>
                    <strong>{incident.updatedAt}</strong>
                  </div>
                </div>

                <div className="incident-next-action">
                  <TriangleAlert size={16} />
                  <span>{incident.nextAction}</span>
                </div>
              </article>
            ))}
          </div>
        </div>

        <aside className="control-column" id="architecture">
          <div className="section-heading">
            <div>
              <span className="eyebrow">Agent pipeline</span>
              <h2>Explicit workflow stages, not one opaque prompt.</h2>
            </div>
          </div>

          <div className="agent-stack">
            {agentStages.map((stage) => (
              <article className="agent-stage" key={stage.name}>
                <div className="stage-header">
                  <div className={`stage-accent ${stage.accent}`} />
                  <div>
                    <h3>{stage.name}</h3>
                    <p>{stage.description}</p>
                  </div>
                </div>
                <span className={`status-pill ${stage.state}`}>{stage.state}</span>
              </article>
            ))}
          </div>

          <div className="principles-card">
            <div className="section-heading compact">
              <div>
                <span className="eyebrow">Operating principles</span>
                <h2>Guardrails that make the project credible.</h2>
              </div>
            </div>
            <ul>
              {operatingPrinciples.map((principle) => (
                <li key={principle}>
                  <Sparkles size={14} />
                  <span>{principle}</span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </section>

      <section className="storyboard-grid">
        <article className="story-card">
          <BrainCircuit size={22} />
          <div>
            <h3>LangGraph orchestrates the state machine.</h3>
            <p>Each node has a narrow job, which makes the workflow debuggable and easy to extend.</p>
          </div>
        </article>
        <article className="story-card">
          <Radar size={22} />
          <div>
            <h3>LangSmith captures the execution trail.</h3>
            <p>Every run can be inspected, compared, and evaluated without losing the operational context.</p>
          </div>
        </article>
        <article className="story-card">
          <Layers3 size={22} />
          <div>
            <h3>The API, UI, and agent core are cleanly separated.</h3>
            <p>That separation keeps the demo easy to reason about and production-ready to evolve.</p>
          </div>
        </article>
        <article className="story-card warning">
          <ShieldAlert size={22} />
          <div>
            <h3>Risky actions always stop for a human review.</h3>
            <p>This is what makes the product useful in real operations instead of just impressive in a demo.</p>
          </div>
        </article>
      </section>
    </main>
  );
}
