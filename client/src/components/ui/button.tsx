import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 whitespace-nowrap rounded-lg border text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "border-amber-900 bg-amber-900 text-amber-50 shadow-sm hover:bg-amber-800",
        secondary: "border-amber-200 bg-white/80 text-stone-800 hover:bg-amber-50",
        ghost: "border-transparent bg-transparent text-stone-700 hover:bg-amber-100/70",
        danger: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
      },
      size: {
        icon: "h-9 w-9 p-0",
        sm: "h-8 px-3",
        default: "h-10 px-4",
      },
    },
    defaultVariants: {
      variant: "secondary",
      size: "default",
    },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />
  },
)
Button.displayName = "Button"

export { Button }
