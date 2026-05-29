import type { ReactNode } from "react"
import { Archive, Check, Clipboard, Clock, Database, FileText, Flag, Inbox, ShieldAlert, X } from "lucide-react"

import { Button } from "../components/ui/button"
import type { MemoryProposal } from "../types/memory"
import type { HandoffPackResponse, TaskCheckpoint, TaskDetail, TaskEvent, TaskSession, TaskState } from "../types/tasks"

type TaskWorkbenchPageProps = {
  activeTasks: TaskSession[]
  selectedTaskId: string | null
  detail: TaskDetail | null
  handoff: HandoffPackResponse | null
  memoryProposals: MemoryProposal[]
  isTaskLoading: boolean
  isInboxLoading: boolean
  isHandoffCopying: boolean
  onSelectTask: (taskId: string | null) => void
  onCopyHandoff: () => void
  onFinishTask: () => void
  onArchiveTask: () => void
  onAcceptProposal: (id: string) => void
  onDismissProposal: (id: string) => void
}

export function TaskWorkbenchPage({
  activeTasks,
  selectedTaskId,
  detail,
  handoff,
  memoryProposals,
  isTaskLoading,
  isInboxLoading,
  isHandoffCopying,
  onSelectTask,
  onCopyHandoff,
  onFinishTask,
  onArchiveTask,
  onAcceptProposal,
  onDismissProposal,
}: TaskWorkbenchPageProps) {
  const task = detail?.task ?? activeTasks.find((item) => item.id === selectedTaskId) ?? null
  const state = detail?.state ?? null
  const events = detail?.events ?? []
  const checkpoints = detail?.checkpoints ?? []
  const freshness = handoff?.pack.freshness ?? null
  const isTerminal = task?.status === "closed" || task?.status === "archived" || task?.status === "expired"

  return (
    <section className="task-workbench">
      <div className="task-shell">
        <aside className="task-sidebar" aria-label="任务选择">
          <div className="task-panel-head">
            <span className="view-kicker">Task Capsule</span>
            <h1>任务工作台</h1>
          </div>

          <label className="task-selector">
            <span>Active Task</span>
            <select value={selectedTaskId ?? ""} onChange={(event) => onSelectTask(event.target.value || null)}>
              {activeTasks.length === 0 ? <option value="">无 active task</option> : null}
              {activeTasks.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>

          <div className={`task-status-block status-${task?.status ?? "empty"}`}>
            <span>Task Status</span>
            <strong>{task?.status ?? "empty"}</strong>
            {task ? <small>{task.activeAgent || "unassigned"}</small> : null}
          </div>

          <FreshnessBanner freshness={freshness} />

          <div className="task-action-stack">
            <Button type="button" variant="primary" onClick={onCopyHandoff} disabled={!task || isHandoffCopying}>
              <Clipboard size={16} />
              {isHandoffCopying ? "复制中" : "Copy Handoff"}
            </Button>
            <Button type="button" variant="secondary" onClick={onFinishTask} disabled={!task || isTerminal}>
              <Check size={16} />
              Finish Task
            </Button>
            <Button type="button" variant="danger" onClick={onArchiveTask} disabled={!task || task.status === "archived"}>
              <Archive size={16} />
              Archive Task
            </Button>
          </div>
        </aside>

        <div className="task-main">
          {isTaskLoading ? <div className="soft-empty task-loading">加载任务中</div> : null}
          {!isTaskLoading && !task ? <div className="soft-empty task-loading">没有 active task</div> : null}

          {task && state ? (
            <>
              <section className="task-focus">
                <div>
                  <span className="view-kicker">Current Goal</span>
                  <h2>{state.currentGoal || task.userGoal}</h2>
                </div>
                <p>{task.userGoal}</p>
              </section>

              <section className="task-state-grid" aria-label="任务状态">
                <TaskList title="Done" values={state.done} tone="done" />
                <TaskList title="In Progress" values={state.inProgress} tone="progress" />
                <TaskList title="Next Steps" values={state.nextSteps} tone="next" />
                <TaskList title="Open Questions" values={state.openQuestions} tone="question" />
              </section>

              <section className="task-signal-grid" aria-label="任务信号">
                <SignalPanel icon={<Flag size={17} />} title="Decisions" values={state.decisions} />
                <SignalPanel icon={<ShieldAlert size={17} />} title="Risks" values={state.risks} />
                <SignalPanel icon={<FileText size={17} />} title="Files Touched" values={state.filesTouched} />
              </section>

              <div className="task-stream-grid">
                <EventTimeline events={events} />
                <CheckpointList checkpoints={checkpoints} state={state} />
              </div>
            </>
          ) : null}
        </div>

        <aside className="task-inbox" aria-label="MemoryProposal inbox">
          <div className="task-panel-head compact">
            <span className="view-kicker">MemoryProposal</span>
            <h2>Inbox</h2>
          </div>
          {isInboxLoading ? <p className="task-muted">加载中</p> : null}
          {!isInboxLoading && memoryProposals.length === 0 ? <p className="task-muted">暂无 pending proposal</p> : null}
          <div className="memory-proposal-list">
            {memoryProposals.map((proposal) => (
              <article key={proposal.id} className="memory-proposal-item">
                <div>
                  <span>{proposal.type}</span>
                  <strong>{proposal.title}</strong>
                </div>
                <div className="proposal-route">
                  <Database size={13} />
                  <span>{proposal.targetStore}</span>
                  <span>{proposal.scope}</span>
                  {proposal.confidence != null ? <span>{Math.round(proposal.confidence * 100)}%</span> : null}
                </div>
                <p>{proposal.body}</p>
                <small>{proposal.evidenceRefs.join(" / ") || proposal.taskSessionId || "no evidence"}</small>
                {proposal.decisionRef || proposal.reviewNote ? (
                  <small>{[proposal.decisionRef, proposal.reviewNote].filter(Boolean).join(" · ")}</small>
                ) : null}
                <div className="proposal-actions">
                  <Button type="button" size="sm" variant="secondary" onClick={() => onDismissProposal(proposal.id)}>
                    <X size={14} />
                    Dismiss
                  </Button>
                  <Button type="button" size="sm" variant="primary" onClick={() => onAcceptProposal(proposal.id)}>
                    <Check size={14} />
                    Accept
                  </Button>
                </div>
              </article>
            ))}
          </div>
        </aside>
      </div>
    </section>
  )
}

function FreshnessBanner({ freshness }: { freshness: HandoffPackResponse["pack"]["freshness"] | null }) {
  if (!freshness) {
    return (
      <div className="freshness-banner">
        <Clock size={16} />
        <span>freshness unknown</span>
      </div>
    )
  }

  return (
    <div className={`freshness-banner freshness-${freshness.state}`}>
      <Clock size={16} />
      <span>{freshness.state}</span>
      {freshness.warning ? <small>{freshness.warning}</small> : <small>{formatDate(freshness.referenceAt)}</small>}
    </div>
  )
}

function TaskList({ title, values, tone }: { title: string; values: string[]; tone: string }) {
  return (
    <section className={`task-list-panel tone-${tone}`}>
      <h3>{title}</h3>
      {values.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function SignalPanel({ icon, title, values }: { icon: ReactNode; title: string; values: string[] }) {
  return (
    <section className="task-signal-panel">
      <div>
        {icon}
        <h3>{title}</h3>
      </div>
      {values.length ? (
        <ul>
          {values.map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p>None</p>
      )}
    </section>
  )
}

function EventTimeline({ events }: { events: TaskEvent[] }) {
  return (
    <section className="task-stream">
      <div className="task-section-title">
        <Inbox size={17} />
        <h2>Event Timeline</h2>
      </div>
      <div className="event-timeline">
        {events.map((event) => (
          <article key={event.id} className="event-row">
            <span>{event.type}</span>
            <strong>{event.summary}</strong>
            <small>
              {formatDate(event.createdAt)}
              {event.sourceRef ? ` · ${event.sourceRef}` : ""}
            </small>
          </article>
        ))}
      </div>
    </section>
  )
}

function CheckpointList({ checkpoints, state }: { checkpoints: TaskCheckpoint[]; state: TaskState }) {
  return (
    <section className="task-stream">
      <div className="task-section-title">
        <Flag size={17} />
        <h2>Checkpoints</h2>
      </div>
      <div className="checkpoint-list">
        {checkpoints.length ? (
          checkpoints.map((checkpoint) => (
            <article key={checkpoint.id} className="checkpoint-row">
              <strong>{checkpoint.title}</strong>
              <p>{checkpoint.summary || "No summary"}</p>
              <small>{formatDate(checkpoint.createdAt)}</small>
            </article>
          ))
        ) : (
          <article className="checkpoint-row">
            <strong>{state.currentGoal || "No checkpoint yet"}</strong>
            <p>None</p>
          </article>
        )}
      </div>
    </section>
  )
}

function formatDate(value?: string | null) {
  if (!value) return "unknown"
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value))
}
