import * as React from "react"

import { cn } from "../../lib/utils"

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "min-h-24 w-full resize-none rounded-md border border-stone-300 bg-white px-3 py-3 text-sm text-stone-800 outline-none transition placeholder:text-stone-400 focus:border-emerald-700 focus:ring-4 focus:ring-emerald-100",
        className,
      )}
      {...props}
    />
  ),
)
Textarea.displayName = "Textarea"

export { Textarea }
