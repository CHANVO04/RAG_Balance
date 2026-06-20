import React from 'react'
import { cn } from '../../lib/utils'

export function Skeleton({
  className = '',
  style,
  variant = 'pulse',
}: {
  className?: string
  style?: React.CSSProperties
  variant?: 'pulse' | 'shimmer'
}) {
  return (
    <div
      className={cn(
        'rounded bg-accent/70',
        variant === 'pulse' && 'animate-pulse',
        variant === 'shimmer' && 'animate-shimmer',
        className,
      )}
      style={style}
    />
  )
}

export function KGSkeleton() {
  return (
    <div className="p-4 space-y-3 h-full">
      <Skeleton variant="shimmer" className="h-4 w-32" />
      <div className="flex gap-4 mt-6">
        {[80, 60, 90, 50].map((w, i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <Skeleton variant="shimmer" className="h-8 rounded-full" style={{ width: w }} />
            <Skeleton className="h-2 w-12" />
          </div>
        ))}
      </div>
      <Skeleton variant="shimmer" className="h-0.5 w-full mt-4" />
      <div className="flex gap-3 mt-4">
        <Skeleton className="h-6 w-20 rounded-full" />
        <Skeleton className="h-6 w-28 rounded-full" />
        <Skeleton className="h-6 w-16 rounded-full" />
      </div>
    </div>
  )
}

export function UMAPSkeleton() {
  return (
    <div className="p-4 h-full flex flex-col gap-3">
      <Skeleton variant="shimmer" className="h-4 w-24" />
      <Skeleton variant="shimmer" className="flex-1 rounded-lg" />
      <div className="flex gap-4">
        {[40, 56, 48].map((w, i) => (
          <div key={i} className="flex items-center gap-1">
            <Skeleton className="h-2 w-2 rounded-full" />
            <Skeleton className="h-2" style={{ width: w }} />
          </div>
        ))}
      </div>
    </div>
  )
}
