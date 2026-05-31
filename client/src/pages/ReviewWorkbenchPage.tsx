import type { FormEvent, ReactNode } from "react"
import {
  Check,
  Database,
  Download,
  FileClock,
  FileText,
  GitBranch,
  ListChecks,
  Lock,
  Pencil,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react"

import { Button } from "../components/ui/button"
import type { MemoryProposal, MemoryProposalType, MemoryTargetStore } from "../types/memory"
import type {
  ReviewConflict,
  ReviewMemoryRecord,
  ReviewProfileFact,
  ReviewProposalPatch,
  ReviewSource,
  ReviewWorkbench,
} from "../types/review"

type ReviewWorkbenchView = Pick<ReviewWorkbench, "proposals" | "profileFacts" | "conflicts" | "rules" | "procedures" | "pages" | "sources" | "counts">

const PROPOSAL_TYPES: MemoryProposalType[] = [
  "lesson",
  "pitfall",
  "user_preference",
  "project_rule",
  "workflow_pattern",
  "technical_decision",
  "environment_fact",
  "profile_fact",
  "entity_relation",
  "fact_supersession",
  "page_update",
]

const TARGET_STORES: MemoryTargetStore[] = ["semantic_knowledge", "profile_temporal_graph", "rule_preference", "procedure_lesson"]
const SOURCE_VISIBILITIES = ["workspace", "task", "profile", "private"]

const PROPOSAL_TYPE_LABEL: Record<MemoryProposalType, string> = {
  lesson: "经验教训",
  pitfall: "踩坑记录",
  user_preference: "用户偏好",
  project_rule: "项目规则",
  workflow_pattern: "流程模式",
  technical_decision: "技术决策",
  environment_fact: "环境事实",
  profile_fact: "个人事实",
  entity_relation: "实体关系",
  fact_supersession: "事实替代",
  page_update: "知识页更新",
}

const TARGET_STORE_LABEL: Record<MemoryTargetStore, string> = {
  semantic_knowledge: "正式知识",
  profile_temporal_graph: "动态事实",
  rule_preference: "规则偏好",
  procedure_lesson: "流程经验",
}

const VISIBILITY_LABEL: Record<string, string> = {
  workspace: "工作区可见",
  task: "任务内可见",
  profile: "个人资料可见",
  private: "私密",
}

const SCOPE_LABEL: Record<string, string> = {
  workspace: "工作区",
  task: "任务",
  profile: "个人资料",
  private: "私密",
}

const STATUS_LABEL: Record<string, string> = {
  pending: "待审",
  accepted: "已接受",
  dismissed: "已拒绝",
  active: "有效",
  open: "未解决",
  resolved: "已解决",
  invalidated: "已失效",
  superseded: "已被替代",
  conflicted: "有冲突",
  purged: "已清除",
  read: "读取",
  write: "写入",
}

const SOURCE_KIND_LABEL: Record<string, string> = {
  card_text: "文本卡片",
  card_link: "链接卡片",
  card_image: "图片卡片",
  external_ai_note: "外部整理笔记",
  agent_selection: "外部选择材料",
  task_event: "任务事件",
}

const PROVENANCE_TYPE_LABEL: Record<string, string> = {
  proposal_created: "待审记忆已创建",
  proposal_for_task: "已关联到任务",
  proposal_dismissed: "待审记忆已拒绝",
  proposal_routed: "待审记忆已分流",
  proposal_created_source: "已生成证据来源",
  accepted_proposal_created_relation: "已创建关系",
  accepted_proposal_created_fact: "已创建事实",
  fact_superseded: "事实已被替代",
  fact_supersession_proposed: "已提出事实替代",
  fact_invalidated: "事实已失效",
  conflict_opened: "冲突已打开",
  conflict_resolved: "冲突已解决",
  conflict_resolution_invalidated_fact: "冲突处理中失效事实",
  proposal_accepted: "待审记忆已接受",
  proposal_review_updated: "待审记忆审查已更新",
  source_policy_updated: "证据权限已更新",
  source_purged: "证据已清除",
  agent_tool_read: "外部工具读取",
  agent_tool_write: "外部工具写入",
  checkpoint_created: "阶段记录已创建",
  handoff_created: "工作摘要已创建",
}

type ReviewWorkbenchPageProps = {
  workbench: ReviewWorkbenchView | null
  isLoading: boolean
  exportPath: string
  onRefresh: () => void
  onExport: () => void
  onSaveProposal: (id: string, payload: ReviewProposalPatch) => void
  onAcceptProposal: (id: string) => void
  onDismissProposal: (id: string) => void
  onSupersedeFact: (id: string, objectValue: string, evidenceRefs: string[], reviewNote: string) => void
  onInvalidateFact: (id: string, reason: string) => void
  onResolveConflict: (id: string, resolution: string, winningFactId?: string) => void
  onSaveSourcePolicy: (id: string, visibility: string, privacyLabels: string[]) => void
  onPurgeSource: (id: string, reason: string) => void
}

export function ReviewWorkbenchPage({
  workbench,
  isLoading,
  exportPath,
  onRefresh,
  onExport,
  onSaveProposal,
  onAcceptProposal,
  onDismissProposal,
  onSupersedeFact,
  onInvalidateFact,
  onResolveConflict,
  onSaveSourcePolicy,
  onPurgeSource,
}: ReviewWorkbenchPageProps) {
  const counts = workbench?.counts ?? {}

  return (
    <section className="review-workbench">
      <div className="review-head">
        <div>
          <span className="view-kicker">记忆审查</span>
          <h1>记忆审查台</h1>
        </div>
        <div className="review-actions">
          <Button type="button" variant="secondary" onClick={onRefresh} disabled={isLoading}>
            <RefreshCw size={16} className={isLoading ? "spin" : ""} />
            刷新
          </Button>
          <Button type="button" variant="primary" onClick={onExport}>
            <Download size={16} />
            导出
          </Button>
        </div>
      </div>

      <div className="review-stat-strip" aria-label="记忆审查统计">
        <Stat icon={<ListChecks size={16} />} label="待审记忆" value={counts.pendingProposals ?? 0} />
        <Stat icon={<ShieldCheck size={16} />} label="个人事实" value={counts.profileFacts ?? 0} />
        <Stat icon={<GitBranch size={16} />} label="未解决冲突" value={counts.openConflicts ?? 0} />
      </div>

      {exportPath ? <div className="review-export-path">{exportPath}</div> : null}
      {isLoading && !workbench ? <div className="soft-empty review-loading">正在加载记忆审查台</div> : null}

      {workbench ? (
        <div className="review-grid">
          <section className="review-section review-section-wide">
            <SectionTitle icon={<ListChecks size={17} />} title="待审记忆收件箱" count={workbench.proposals.length} />
            <div className="review-card-list">
              {workbench.proposals.map((proposal) => (
                <ProposalCard
                  key={proposal.id}
                  proposal={proposal}
                  onSave={onSaveProposal}
                  onAccept={onAcceptProposal}
                  onDismiss={onDismissProposal}
                />
              ))}
            </div>
          </section>

          <section className="review-section">
            <SectionTitle icon={<ShieldCheck size={17} />} title="个人事实" count={workbench.profileFacts.length} />
            <div className="review-card-list">
              {workbench.profileFacts.map((fact) => (
                <ProfileFactCard key={fact.id} fact={fact} onSupersede={onSupersedeFact} onInvalidate={onInvalidateFact} />
              ))}
            </div>
          </section>

          <section className="review-section">
            <SectionTitle icon={<GitBranch size={17} />} title="冲突" count={workbench.conflicts.length} />
            <div className="review-card-list">
              {workbench.conflicts.map((conflict) => (
                <ConflictCard key={conflict.id} conflict={conflict} onResolve={onResolveConflict} />
              ))}
            </div>
          </section>

          <MemoryRecordSection title="规则" icon={<Database size={17} />} records={workbench.rules} />
          <MemoryRecordSection title="流程经验" icon={<FileClock size={17} />} records={workbench.procedures} />
          <MemoryRecordSection title="知识页" icon={<FileText size={17} />} records={workbench.pages} />

          <section className="review-section review-section-wide">
            <SectionTitle icon={<Lock size={17} />} title="原始证据" count={workbench.sources.length} />
            <div className="review-card-list review-source-grid">
              {workbench.sources.map((source) => (
                <SourceCard key={source.id} source={source} onSavePolicy={onSaveSourcePolicy} onPurge={onPurgeSource} />
              ))}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  )
}

function ProposalCard({
  proposal,
  onSave,
  onAccept,
  onDismiss,
}: {
  proposal: MemoryProposal
  onSave: (id: string, payload: ReviewProposalPatch) => void
  onAccept: (id: string) => void
  onDismiss: (id: string) => void
}) {
  const disabled = proposal.status !== "pending"

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    onSave(proposal.id, {
      title: String(data.get("title") ?? ""),
      body: String(data.get("body") ?? ""),
      type: String(data.get("type") ?? proposal.type) as MemoryProposalType,
      targetStore: String(data.get("targetStore") ?? proposal.targetStore) as MemoryTargetStore,
      scope: String(data.get("scope") ?? "workspace"),
      evidenceRefs: splitRefs(String(data.get("evidenceRefs") ?? "")),
      reviewNote: String(data.get("reviewNote") ?? ""),
    })
  }

  return (
    <article className={`review-card proposal-status-${proposal.status}`}>
      <form className="review-proposal-form" onSubmit={handleSubmit}>
        <div className="review-card-head">
          <StatusPill value={proposal.status} />
          <span>{proposal.decisionRef ?? proposal.id}</span>
        </div>
        <input name="title" defaultValue={proposal.title} disabled={disabled} aria-label="待审记忆标题" />
        <div className="review-form-row">
          <select name="type" defaultValue={proposal.type} disabled={disabled} aria-label="待审记忆类型">
            {PROPOSAL_TYPES.map((type) => (
              <option key={type} value={type}>
                {PROPOSAL_TYPE_LABEL[type]}
              </option>
            ))}
          </select>
          <select name="targetStore" defaultValue={proposal.targetStore} disabled={disabled} aria-label="待审记忆目标层">
            {TARGET_STORES.map((store) => (
              <option key={store} value={store}>
                {TARGET_STORE_LABEL[store]}
              </option>
            ))}
          </select>
        </div>
        <textarea name="body" defaultValue={proposal.body} disabled={disabled} aria-label="待审记忆正文" />
        <div className="review-form-row">
          <input type="hidden" name="scope" value={proposal.scope} />
          <span className="review-static-field">{formatScope(proposal.scope)}</span>
          <input name="evidenceRefs" defaultValue={proposal.evidenceRefs.join(", ")} disabled={disabled} aria-label="证据引用" />
        </div>
        <input name="reviewNote" defaultValue={proposal.reviewNote} disabled={disabled} aria-label="审查备注" />
        <div className="review-card-actions">
          <Button type="button" size="sm" variant="danger" onClick={() => onDismiss(proposal.id)} disabled={disabled}>
            <X size={14} />
            拒绝
          </Button>
          <Button type="submit" size="sm" variant="secondary" disabled={disabled}>
            <Pencil size={14} />
            保存
          </Button>
          <Button type="button" size="sm" variant="primary" onClick={() => onAccept(proposal.id)} disabled={disabled}>
            <Check size={14} />
            接受
          </Button>
        </div>
      </form>
    </article>
  )
}

function ProfileFactCard({
  fact,
  onSupersede,
  onInvalidate,
}: {
  fact: ReviewProfileFact
  onSupersede: (id: string, objectValue: string, evidenceRefs: string[], reviewNote: string) => void
  onInvalidate: (id: string, reason: string) => void
}) {
  function handleSupersede(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    onSupersede(
      fact.id,
      String(data.get("objectValue") ?? ""),
      splitRefs(String(data.get("evidenceRefs") ?? "")),
      String(data.get("reviewNote") ?? ""),
    )
  }

  return (
    <article className={`review-card fact-status-${fact.status}`}>
      <div className="review-card-head">
        <StatusPill value={fact.status} />
        <span>{fact.ref}</span>
      </div>
      <strong>{fact.title}</strong>
      <p>{fact.subject} / {fact.predicate}</p>
      <RefList refs={[...fact.evidenceRefs, ...fact.conflictRefs]} />
      <DecisionTrail decisions={fact.decisionHistory} provenance={fact.provenanceHistory} />
      <form className="review-mini-form" onSubmit={handleSupersede}>
        <input name="objectValue" defaultValue={fact.objectValue} aria-label="新的事实值" />
        <input name="evidenceRefs" defaultValue={fact.evidenceRefs.join(", ")} aria-label="替代事实证据引用" />
        <input name="reviewNote" defaultValue={`替代 ${fact.ref}`} aria-label="替代事实审查备注" />
        <div className="review-card-actions">
          <Button type="button" size="sm" variant="danger" onClick={() => onInvalidate(fact.id, `在记忆审查台失效 ${fact.ref}`)}>
            <Trash2 size={14} />
            失效
          </Button>
          <Button type="submit" size="sm" variant="secondary">
            <GitBranch size={14} />
            替代
          </Button>
        </div>
      </form>
    </article>
  )
}

function ConflictCard({ conflict, onResolve }: { conflict: ReviewConflict; onResolve: (id: string, resolution: string, winningFactId?: string) => void }) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    onResolve(conflict.id, String(data.get("resolution") ?? ""), String(data.get("winningFactId") ?? "") || undefined)
  }

  return (
    <article className={`review-card conflict-status-${conflict.status}`}>
      <div className="review-card-head">
        <StatusPill value={conflict.status} />
        <span>{conflict.ref}</span>
      </div>
      <strong>{conflict.reason}</strong>
      <RefList refs={[...conflict.factRefs, ...conflict.relationRefs]} />
      <DecisionTrail decisions={conflict.decisionHistory} provenance={conflict.provenanceHistory} />
      <form className="review-mini-form" onSubmit={handleSubmit}>
        <select name="winningFactId" defaultValue="" aria-label="保留的事实">
          <option value="">不选择保留事实</option>
          {conflict.factRefs.map((ref) => (
            <option key={ref} value={ref.replace("fact:", "")}>
              {ref}
            </option>
          ))}
        </select>
        <textarea name="resolution" defaultValue={conflict.resolution || "在记忆审查台处理冲突"} aria-label="冲突处理说明" />
        <div className="review-card-actions">
          <Button type="submit" size="sm" variant="primary" disabled={conflict.status === "resolved"}>
            <Check size={14} />
            解决
          </Button>
        </div>
      </form>
    </article>
  )
}

function SourceCard({
  source,
  onSavePolicy,
  onPurge,
}: {
  source: ReviewSource
  onSavePolicy: (id: string, visibility: string, privacyLabels: string[]) => void
  onPurge: (id: string, reason: string) => void
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    onSavePolicy(source.id, String(data.get("visibility") ?? "workspace"), splitRefs(String(data.get("privacyLabels") ?? "")))
  }

  return (
    <article className={`review-card source-status-${source.status}`}>
      <form className="review-mini-form" onSubmit={handleSubmit}>
        <div className="review-card-head">
          <StatusPill value={source.status} />
          <span>{source.ref}</span>
        </div>
        <strong>{source.title || formatSourceKind(source.kind)}</strong>
        <p>{source.excerpt || "没有原始正文"}</p>
        <div className="review-form-row">
          <select name="visibility" defaultValue={source.visibility} aria-label="证据可见性">
            {SOURCE_VISIBILITIES.map((visibility) => (
              <option key={visibility} value={visibility}>
                {VISIBILITY_LABEL[visibility] ?? visibility}
              </option>
            ))}
          </select>
          <input name="privacyLabels" defaultValue={source.privacyLabels.join(", ")} aria-label="隐私标签" />
        </div>
        <span className="review-muted">{source.contentChars} 字符 · {formatSourceKind(source.kind)}</span>
        <DecisionTrail decisions={source.decisionHistory} provenance={source.provenanceHistory} />
        <div className="review-card-actions">
          <Button type="button" size="sm" variant="danger" onClick={() => onPurge(source.id, `在记忆审查台清除 ${source.ref}`)}>
            <Trash2 size={14} />
            清除
          </Button>
          <Button type="submit" size="sm" variant="secondary">
            <Lock size={14} />
            保存权限
          </Button>
        </div>
      </form>
    </article>
  )
}

function MemoryRecordSection({ title, icon, records }: { title: string; icon: ReactNode; records: ReviewMemoryRecord[] }) {
  return (
    <section className="review-section">
      <SectionTitle icon={icon} title={title} count={records.length} />
      <div className="review-card-list">
        {records.map((record) => (
          <article key={record.ref} className={`review-card record-status-${record.status}`}>
            <div className="review-card-head">
              <StatusPill value={record.status} />
              <span>{record.ref}</span>
            </div>
            <strong>{record.title}</strong>
            <p>{record.summary || record.scope}</p>
            <div className="review-route">
              <span>{TARGET_STORE_LABEL[record.targetStore as MemoryTargetStore] ?? record.targetStore}</span>
              <span>{formatScope(record.scope)}</span>
              <span>{VISIBILITY_LABEL[record.visibility] ?? record.visibility}</span>
            </div>
            <RefList refs={[...record.evidenceRefs, record.decisionRef ?? "", record.sourceRef ?? ""].filter(Boolean)} />
            <DecisionTrail decisions={record.decisionHistory} provenance={record.provenanceHistory} />
          </article>
        ))}
      </div>
    </section>
  )
}

function SectionTitle({ icon, title, count }: { icon: ReactNode; title: string; count: number }) {
  return (
    <div className="review-section-title">
      {icon}
      <h2>{title}</h2>
      <span>{count}</span>
    </div>
  )
}

function Stat({ icon, label, value }: { icon: ReactNode; label: string; value: number }) {
  return (
    <div className="review-stat">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function StatusPill({ value }: { value: string }) {
  return <em className={`review-status review-status-${value}`}>{STATUS_LABEL[value] ?? value}</em>
}

function RefList({ refs }: { refs: string[] }) {
  const clean = refs.filter(Boolean).slice(0, 5)
  if (!clean.length) return null
  return (
    <div className="review-ref-list">
      {clean.map((ref) => (
        <span key={ref}>{ref}</span>
      ))}
    </div>
  )
}

function DecisionTrail({ decisions, provenance }: { decisions: { ref: string; reason: string }[]; provenance: { ref: string; type: string }[] }) {
  const firstDecision = decisions[0]
  const firstProvenance = provenance[0]
  if (!firstDecision && !firstProvenance) return null
  return (
    <div className="review-trail">
      {firstDecision ? <span>{firstDecision.ref}: {formatReason(firstDecision.reason)}</span> : null}
      {firstProvenance ? <span>{formatProvenanceType(firstProvenance.type)}</span> : null}
    </div>
  )
}

function splitRefs(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
}

function formatScope(value?: string | null) {
  if (!value) return "工作区"
  if (SCOPE_LABEL[value]) return SCOPE_LABEL[value]
  if (value.startsWith("task:")) return `任务 ${value.slice(5)}`
  return value
}

function formatSourceKind(value: string) {
  return SOURCE_KIND_LABEL[value] ?? value
}

function formatProvenanceType(value: string) {
  return PROVENANCE_TYPE_LABEL[value] ?? value
}

function formatReason(value?: string | null) {
  if (!value) return "已记录决策"
  if (value.includes("Review Workbench")) return value.replace("Review Workbench", "记忆审查台")
  if (value === "Accepted proposal materialized source evidence") return "接受候选记忆后生成原始证据"
  if (value.startsWith("Routed accepted proposal into")) return "待审记忆已进入目标记忆层"
  if (value.startsWith("Updated source visibility/privacy labels")) return "已更新证据可见性和隐私标签"
  return value
}
