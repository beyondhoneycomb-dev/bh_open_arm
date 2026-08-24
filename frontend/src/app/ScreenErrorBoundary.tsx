// What stays on screen when a screen does not.
//
// Every screen and the viewport arrive as a lazy chunk (routes/screenResolver.ts,
// ViewportRoute.tsx), and a chunk that fails to load rejects into the render pass rather than
// into a promise the caller holds. Without a boundary that throw unwinds the whole tree, so a
// bundle hash that moved under an open tab takes the safety bar off the page along with the
// screen — and CG-G-03b asks for a reachable STOP_HOLD on every route, which an unmounted
// document does not serve on any.
//
// It sits inside the outlet slot, below SafetyBarHost, so the blast radius of a screen fault is
// one panel. There is deliberately no reload control on it: the nav rail is still mounted and is
// the recovery path, and a reload would end the WebSocket session, which drops the control lease
// and latches the dead-man. That latch is the safe direction, but it is a robot state change,
// and this panel is not where an operator should be asked for one.
//
// Resetting on route change is load-bearing, not tidiness. React holds a boundary's error state
// until the component itself is replaced, so a boundary mounted once would keep showing the
// first failed chunk on every route the operator navigated to afterwards — the nav rail would
// stop being a recovery path at the exact moment it became one. The caller supplies a key that
// changes with the path; see Layout.tsx.

import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

interface ScreenErrorBoundaryProps {
  children: ReactNode;
}

interface ScreenErrorBoundaryState {
  // The error, or null while nothing has thrown. Held rather than a bare boolean so the panel
  // can name what failed: a fixed "could not display this screen" line sends the operator to the
  // backend logs for a fault that lives in the bundle.
  error: Error | null;
}

export class ScreenErrorBoundary extends Component<
  ScreenErrorBoundaryProps,
  ScreenErrorBoundaryState
> {
  state: ScreenErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ScreenErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // React logs the error itself; the component stack is what it does not keep anywhere a
    // reader can reach afterwards, and it is what names which screen threw.
    console.error("screen render failed", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) {
      return this.props.children;
    }
    return (
      <section className="oa-scaffold" aria-labelledby="oa-screen-error-title" role="alert">
        <header className="oa-scaffold__head">
          <p className="oa-scaffold__id">화면 오류</p>
          <h1 id="oa-screen-error-title" className="oa-scaffold__title">
            이 화면을 표시하지 못했습니다
          </h1>
        </header>
        <p className="oa-scaffold__pending">
          왼쪽 메뉴에서 다른 화면으로 이동할 수 있습니다. 상단 안전 바와 소프트 스톱은 그대로
          동작합니다.
        </p>
        <pre className="oa-screen-error__detail">{error.message}</pre>
      </section>
    );
  }
}
