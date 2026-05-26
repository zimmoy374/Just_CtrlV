import type { Reflection } from "../types/organization"
import { ReflectionPanel } from "./reflection-panel"

type SuggestionsPanelProps = {
  suggestions: Reflection[]
  onAccept: (id: string) => void
  onDismiss: (id: string) => void
}

export function SuggestionsPanel({ suggestions, onAccept, onDismiss }: SuggestionsPanelProps) {
  return <ReflectionPanel reflections={suggestions} onAccept={onAccept} onDismiss={onDismiss} />
}


