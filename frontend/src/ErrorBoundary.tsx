import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "./ui/Button";
import { BrandMark } from "./ui/feedback";

interface State {
  failed: boolean;
}

/**
 * Last line of defence for rendering bugs: a calm full-page message with a
 * reload, instead of a blank screen. Error details go to the console only.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;

    return (
      <div className="flex min-h-full items-center justify-center bg-canvas px-6">
        <div className="max-w-[26rem]">
          <BrandMark size={28} />
          <h1 className="mt-5 text-heading font-semibold text-ink">Something went wrong on this page</h1>
          <p className="mt-2 text-control text-muted">
            Your conversations are saved on the server. Reload to continue where you left off.
          </p>
          <Button variant="primary" className="mt-5" onClick={() => window.location.reload()}>
            Reload Policy Copilot
          </Button>
        </div>
      </div>
    );
  }
}
