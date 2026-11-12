import { useRef } from "react";

/**
 * Long press (touch or mouse), plus right-click on desktop.
 * Swallows the click that follows a long press, so holding "Worked out"
 * opens its details without also toggling it.
 */
export function useLongPress(onLong, ms = 450) {
  const timer = useRef(null);
  const fired = useRef(false);
  const origin = useRef(null);
  const clear = () => { clearTimeout(timer.current); timer.current = null; };
  const fire = () => {
    clear();
    fired.current = true;
    if (navigator.vibrate) navigator.vibrate(10);
    onLong();
  };

  return {
    onPointerDown: (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      fired.current = false;
      origin.current = { x: e.clientX, y: e.clientY };
      clear();
      timer.current = setTimeout(fire, ms);
    },
    onPointerMove: (e) => {
      const o = origin.current;
      if (o && timer.current && (Math.abs(e.clientX - o.x) > 8 || Math.abs(e.clientY - o.y) > 8)) clear(); // scrolling
    },
    onPointerUp: clear,
    onPointerLeave: clear,
    onPointerCancel: clear,
    onContextMenu: (e) => {
      e.preventDefault();               // no text-selection callout on phones
      if (!fired.current) fire();       // right-click on desktop
    },
    onClickCapture: (e) => {
      if (fired.current) { e.stopPropagation(); e.preventDefault(); fired.current = false; }
    },
  };
}
