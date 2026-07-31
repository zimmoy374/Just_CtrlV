import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 whitespace-nowrap rounded-lg border text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "border-emerald-900 bg-emerald-900 text-white shadow-sm hover:bg-emerald-800",
        secondary: "border-stone-300 bg-white text-stone-800 hover:bg-stone-100",
        ghost: "border-transparent bg-transparent text-stone-700 hover:bg-stone-200/70",
        danger: "border-red-200 bg-red-50 text-red-700 hover:bg-red-100",
      },
      size: {
        icon: "h-8 w-8 p-0",
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
