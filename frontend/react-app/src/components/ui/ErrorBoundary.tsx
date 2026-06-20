import React from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props { children: React.ReactNode; fallbackLabel?: string }
interface State { error: Error | null }

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-full flex flex-col items-center justify-center p-4 text-center gap-2">
          <AlertTriangle size={24} className="text-red-400" />
          <div className="text-sm font-medium text-red-600">
            {this.props.fallbackLabel ?? 'Something went wrong'}
          </div>
          <div className="text-xs text-gray-400 font-mono max-w-xs truncate">
            {this.state.error.message}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="text-xs text-blue-600 underline"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
