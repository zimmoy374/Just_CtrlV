export type TaskSessionStatus =
  | "open"
  | "paused"
  | "handoff_ready"
  | "waiting_user"
  | "closing_review"
  | "closed"
  | "archived"
  | "expired"

export type TaskEventType =
  | "user_goal"
  | "user_constraint"
  | "agent_observation"
  | "agent_action"
  | "decision"
  | "file_change"
  | "test_result"
  | "blocker"
  | "question"
  | "checkpoint_created"
  | "handoff_created"
  | "close_suggested"
  | "task_closed"
  | "memory_candidate"

export type TaskSession = {
  id: string
  title: string
  userGoal: string
  status: TaskSessionStatus
  activeAgent: string
  createdAt: string
  updatedAt: string
  lastEventAt?: string | null
  closedAt?: string | null
  expiresAt?: string | null
}

export type TaskEvent = {
  id: string
  taskSessionId: string
  type: TaskEventType
  summary: string
  payload: Record<string, unknown>
  source: string
  sourceRef: string
  createdAt: string
}

export type TaskState = {
  taskSessionId: string
  currentGoal: string
  done: string[]
  inProgress: string[]
  nextSteps: string[]
  openQuestions: string[]
  constraints: string[]
  risks: string[]
  decisions: string[]
  filesTouched: string[]
  confidence: number
  updatedAt: string
}

export type TaskCheckpoint = {
  id: string
  taskSessionId: string
  title: string
  summary: string
  stateSnapshot: Record<string, unknown>
  eventFromId?: string | null
  eventToId?: string | null
  createdAt: string
}

export type TaskDetail = {
  task: TaskSession
  state: TaskState
  events: TaskEvent[]
  checkpoints: TaskCheckpoint[]
}

export type TaskHandoffFreshness = {
  state: "fresh" | "stale" | "expired"
  isStale: boolean
  warning: string
  checkedAt: string
  referenceAt?: string | null
  expiresAt?: string | null
}

export type TaskHandoffRef = {
  ref: string
  id: string
  title?: string
  eventType?: TaskEventType
  source?: string
  sourceRef?: string
  createdAt?: string | null
}

export type TaskHandoffPack = {
  taskId: string
  status: TaskSessionStatus
  freshness: TaskHandoffFreshness
  userGoal: string
  currentGoal: string
  done: string[]
  inProgress: string[]
  nextSteps: string[]
  openQuestions: string[]
  constraints: string[]
  decisions: string[]
  risks: string[]
  filesTouched: string[]
  checkpointRefs: TaskHandoffRef[]
  sourceRefs: TaskHandoffRef[]
}

export type HandoffPackResponse = {
  id?: string | null
  taskSessionId: string
  format: "markdown" | "json"
  content: string
  pack: TaskHandoffPack
  budget: Record<string, unknown>
  createdAt: string
}
