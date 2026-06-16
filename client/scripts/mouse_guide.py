import sys
import time
import math
import argparse
import threading
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt5.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPen, QFont, QFontMetrics
import pyautogui
from pynput import mouse, keyboard

pyautogui.PAUSE = 0.0

class MouseGuide(QWidget):
    def __init__(self, target_x, target_y, timeout=20.0, type_hint=""):
        super().__init__()
        self.target_x = target_x
        self.target_y = target_y
        # Text the user should type AFTER clicking. When non-empty we
        # render a rounded bubble near the spotlight showing it.
        self.type_hint = (type_hint or "").strip()
        self.user_took_control = False
        self.running = True

        # Use the full virtual desktop (spans all monitors) and pick the
        # primary screen's geometry for sizing the overlay.
        screen = QApplication.primaryScreen()
        geom = screen.geometry() if screen is not None else None
        self.w = geom.width()  if geom is not None else QApplication.desktop().width()
        self.h = geom.height() if geom is not None else QApplication.desktop().height()
        # Two coord systems live in this script:
        #   * Qt painter: logical pixels  (geometry is in Qt's scaled space)
        #   * pyautogui : physical pixels (DPI-aware level 2, matches the
        #                                  executor & mss)
        # On a 4K display with 200% scaling, devicePixelRatio = 2 and physical
        # coords are double the Qt logical coords. The agent gives us physical
        # coords. Keep them as physical for pyautogui; compute the Qt-logical
        # versions on demand for drawing.
        try:
            self.dpr = float(screen.devicePixelRatio()) if screen else 1.0
        except Exception:
            self.dpr = 1.0

        # Adapt spotlight size + trail width to screen so the overlay reads the
        # same on a 1080p laptop and a 4K monitor. Floor/ceiling so it never
        # disappears on tiny displays or eats half the screen on huge ones.
        short_edge = min(self.w, self.h)
        self.min_radius = max(60, min(180, int(short_edge * 0.08)))
        self.trail_width = max(10.0, min(36.0, short_edge * 0.012))

        self.max_radius = math.hypot(self.w, self.h)
        self.circle_radius = self.max_radius
        self.state = "entering"

        self.trail = []
        
        self.setup_window()
        
        self.mouse_listener = mouse.Listener(on_click=self.on_click, on_move=self.on_move)
        self.keyboard_listener = keyboard.Listener(on_release=self.on_key_release)
        self.mouse_listener.start()
        self.keyboard_listener.start()
        
        self.move_thread = threading.Thread(target=self.move_mouse_smoothly, daemon=True)
        self.move_thread.start()
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate_frame)
        self.timer.start(16)

        # Hard cap: even if the user doesn't move/click, we exit after
        # `timeout` seconds so the agent isn't stuck waiting on a stale
        # overlay.
        if timeout and timeout > 0:
            QTimer.singleShot(int(timeout * 1000), self.close_app)

    def _qt(self, v):
        """Convert a physical-pixel coord to Qt-logical (for painter ops)."""
        return v / self.dpr if self.dpr > 1.0001 else v

    def setup_window(self):
        self.setGeometry(0, 0, self.w, self.h)
        # WindowDoesNotAcceptFocus + WindowTransparentForInput → we never
        # steal focus from the shell, so Start menu / volume flyout don't
        # close just because the overlay appeared.
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.show()
        # Win11 Start menu / system-tray flyouts (Volume, Wi-Fi, Calendar,
        # Action Center) get z-ordered above plain WindowStaysOnTopHint so
        # the overlay vanishes behind them. Combat that with three things:
        #   1. Re-pop HWND_TOPMOST on a ~33 ms timer (cheap fallback).
        #   2. SetWinEventHook on EVENT_SYSTEM_FOREGROUND / EVENT_OBJECT_SHOW
        #      so the re-pop happens *the moment* another window appears,
        #      not on the next poll tick.
        #   3. SWP_NOACTIVATE everywhere so the re-pop doesn't steal focus
        #      and close the flyout the user is interacting with.
        # Caveat: the Win11 Start menu (StartMenuExperienceHost) is rendered
        # in DWM's "AppWindow" z-band that sits above HWND_TOPMOST. Beating
        # it would require a uiAccess=true manifest + a signed installer
        # (out of scope). Volume / Wi-Fi / Calendar / notifications are
        # plain topmost and these tricks DO beat them.
        self._reassert_topmost()
        self._install_winevent_hooks()
        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(33)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start()

    def _reassert_topmost(self):
        """Force HWND_TOPMOST + BringWindowToTop. Cheap (no move/resize/
        activate) so it's safe to run at 30 Hz."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            user32.SetWindowPos(
                hwnd, HWND_TOPMOST,
                0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            # BringWindowToTop raises the HWND in z-order without focus
            # change — catches the case where another topmost window
            # was just put above us.
            user32.BringWindowToTop(hwnd)
            # Long-shot: try the undocumented user32!SetWindowBand to put
            # our HWND in the UIACCESS z-band (above HWND_TOPMOST). Most
            # builds require uiAccess privilege and silently refuse, but
            # the call itself is harmless when it fails. If a future
            # Windows build relaxes this, the Start menu becomes
            # catchable for free.
            try:
                SetWindowBand = user32.SetWindowBand
                SetWindowBand.argtypes = [
                    ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
                ]
                SetWindowBand.restype = ctypes.c_bool
                ZBID_UIACCESS = 2
                SetWindowBand(hwnd, None, ZBID_UIACCESS)
            except Exception:  # noqa: BLE001
                pass
        except Exception:  # noqa: BLE001
            pass

    def _shell_flyout_rect(self):
        """If a Win11 shell flyout (Start menu, Volume, Wi-Fi, Calendar,
        notifications) is the current foreground window, return its
        physical-pixel screen rect as (l, t, r, b). Otherwise None.

        Used to move the type-hint bubble OUTSIDE the unbeatable Start-
        menu z-band so the user can still see what to type.
        """
        if sys.platform != "win32":
            return None
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            if not fg:
                return None
            buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(fg, buf, 64)
            # Win11 shell uses CoreWindow for Start + all tray flyouts.
            # Win10 uses ApplicationFrameWindow for some. Catch both.
            if buf.value not in (
                "Windows.UI.Core.CoreWindow",
                "ApplicationFrameWindow",
            ):
                return None
            rect = wintypes.RECT()
            user32.GetWindowRect(fg, ctypes.byref(rect))
            return rect.left, rect.top, rect.right, rect.bottom
        except Exception:  # noqa: BLE001
            return None

    def _install_winevent_hooks(self):
        """Subscribe to the shell's foreground-change events so we can
        re-pop above any window the instant it appears, rather than waiting
        for the 33 ms polling tick.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            EVENT_SYSTEM_FOREGROUND = 0x0003
            EVENT_OBJECT_SHOW = 0x8002
            WINEVENT_OUTOFCONTEXT = 0x0000
            WINEVENT_SKIPOWNPROCESS = 0x0002

            user32 = ctypes.windll.user32

            WinEventProcType = ctypes.WINFUNCTYPE(
                None,
                wintypes.HANDLE,  # hWinEventHook
                wintypes.DWORD,   # event
                wintypes.HWND,    # hwnd
                wintypes.LONG,    # idObject
                wintypes.LONG,    # idChild
                wintypes.DWORD,   # idEventThread
                wintypes.DWORD,   # dwmsEventTime
            )

            our_hwnd = int(self.winId())

            def _on_winevent(hook, event, hwnd, idObject, idChild,
                             idEventThread, dwmsEventTime):
                if hwnd == our_hwnd:
                    return
                # We're called from the system's event thread; SetWindowPos
                # is thread-safe so we can re-pop directly.
                try:
                    self._reassert_topmost()
                except Exception:  # noqa: BLE001
                    pass

            # Keep refs so the GC doesn't reap the callback / hooks.
            self._winevent_proc = WinEventProcType(_on_winevent)
            flags = WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS
            self._hook_fg = user32.SetWinEventHook(
                EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
                0, self._winevent_proc, 0, 0, flags,
            )
            self._hook_show = user32.SetWinEventHook(
                EVENT_OBJECT_SHOW, EVENT_OBJECT_SHOW,
                0, self._winevent_proc, 0, 0, flags,
            )
        except Exception:  # noqa: BLE001
            self._hook_fg = None
            self._hook_show = None

    def _uninstall_winevent_hooks(self):
        if sys.platform != "win32":
            return
        try:
            import ctypes
            user32 = ctypes.windll.user32
            for h in (getattr(self, "_hook_fg", None),
                      getattr(self, "_hook_show", None)):
                if h:
                    user32.UnhookWinEvent(h)
        except Exception:  # noqa: BLE001
            pass

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Spotlight center is in Qt-logical pixels (painter's coord system),
        # so divide the physical-pixel target by devicePixelRatio.
        grad = QRadialGradient(
            QPointF(self._qt(self.target_x), self._qt(self.target_y)),
            self.circle_radius,
        )
        # Inside the hole is 100% transparent
        grad.setColorAt(0, QColor(0, 0, 0, 0))
        grad.setColorAt(0.3, QColor(0, 0, 0, 0))
        # Smoothly transitions to the dark screen overlay
        grad.setColorAt(1, QColor(0, 0, 0, 180)) # 180 is a nice dark gray
        
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        # This single rect draw covers the whole screen. Anything outside circle_radius is clamped to the color at 1.0!
        painter.drawRect(self.rect())

        # Draw the continuous mouse trail (Comet tail)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        if len(self.trail) > 1:
            for i in range(len(self.trail) - 1):
                tx1, ty1, age1 = self.trail[i]
                tx2, ty2, age2 = self.trail[i+1]
                
                avg_age = (age1 + age2) / 2.0
                alpha = int(255 * avg_age)
                
                # Bright Cyan trail
                pen = QPen(QColor(0, 255, 255, alpha))
                # Taper the line width based on age (thicker at the head).
                # Width scales with screen so the trail reads the same at any res.
                pen.setWidthF(self.trail_width * avg_age)
                pen.setCapStyle(Qt.RoundCap)
                painter.setPen(pen)
                # Trail points are recorded in pyautogui's physical-pixel space;
                # convert to Qt-logical for the painter.
                painter.drawLine(
                    QPointF(self._qt(tx1), self._qt(ty1)),
                    QPointF(self._qt(tx2), self._qt(ty2)),
                )

        # ── Type-hint bubble ────────────────────────────────────────────
        # Renders only when the agent passed a non-empty hint (i.e. the
        # user needs to TYPE something after clicking the spot). Tries to
        # sit below the spotlight; if that runs off-screen flips to above.
        if self.type_hint:
            self._draw_type_hint_bubble(painter)

    def _draw_type_hint_bubble(self, painter: QPainter) -> None:
        # All coords in Qt-logical px (painter space).
        tx = self._qt(self.target_x)
        ty = self._qt(self.target_y)
        spot_radius = self.circle_radius
        msg = f"⌨  Type: {self.type_hint}"
        font = QFont("Segoe UI", 12, QFont.DemiBold)
        painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(msg)
        text_h = fm.height()
        pad_x = 14
        pad_y = 8
        bubble_w = text_w + pad_x * 2
        bubble_h = text_h + pad_y * 2
        # Default position: bubble centered horizontally below the spot,
        # 14 px gap from the spotlight edge. Clamp horizontally so it
        # never bleeds off the left/right.
        gap = 14
        bx = tx - bubble_w / 2
        by = ty + spot_radius + gap
        # If the bubble would fall off the bottom, flip above the spot.
        scr_w = self._qt(self.w)
        scr_h = self._qt(self.h)
        if by + bubble_h > scr_h - 8:
            by = ty - spot_radius - gap - bubble_h
        bx = max(8.0, min(scr_w - bubble_w - 8.0, bx))

        # If a Win11 shell flyout (Start menu, tray flyout) is foreground
        # AND would visually cover the default bubble position, relocate
        # the bubble to a clear strip OUTSIDE the flyout rect. Our overlay
        # widget is z-ordered below the flyout, but only the pixels that
        # overlap the flyout's window rect are obscured — anywhere else
        # on the overlay paints normally and IS visible.
        excl = self._shell_flyout_rect()
        if excl:
            el = self._qt(excl[0])
            et = self._qt(excl[1])
            er = self._qt(excl[2])
            eb = self._qt(excl[3])
            bubble_overlaps = (
                bx < er and bx + bubble_w > el
                and by < eb and by + bubble_h > et
            )
            if bubble_overlaps:
                # Prefer above the flyout (Start menu is bottom-anchored
                # in Win11), fall back to below if there's no room.
                candidate_by = et - gap - bubble_h
                if candidate_by < 8:
                    candidate_by = eb + gap
                # If even that doesn't fit, clamp to the top of screen.
                if candidate_by < 8:
                    candidate_by = 8
                if candidate_by + bubble_h > scr_h - 8:
                    candidate_by = scr_h - 8 - bubble_h
                by = candidate_by
                # Re-center horizontally over the flyout so the bubble
                # visually relates to the active flyout.
                flyout_cx = (el + er) / 2
                bx = max(8.0, min(scr_w - bubble_w - 8.0,
                                  flyout_cx - bubble_w / 2))

        # White rounded-rect with a soft cyan border to match the trail.
        painter.setPen(QPen(QColor(0, 220, 255, 220), 2))
        painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
        painter.drawRoundedRect(QRectF(bx, by, bubble_w, bubble_h), 14, 14)
        # Subtle drop-shadow-ish stroke under the bubble for depth.
        painter.setPen(QPen(QColor(0, 0, 0, 35), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(bx + 1, by + 2, bubble_w, bubble_h), 14, 14)
        # Bubble text
        painter.setPen(QColor(20, 30, 45))
        painter.drawText(
            QRectF(bx, by, bubble_w, bubble_h),
            Qt.AlignCenter, msg,
        )

    def animate_frame(self):
        if not self.running:
            return
            
        # Update trail ages
        new_trail = []
        for tx, ty, age in self.trail:
            age -= 0.05 # Slightly faster fade for the trail
            if age > 0:
                new_trail.append((tx, ty, age))
        self.trail = new_trail
            
        # Update spotlight animation
        if self.state == "entering":
            # Much faster entrance
            speed = (self.circle_radius - self.min_radius) * 0.20
            if speed < 3: speed = 3
            self.circle_radius -= speed
            
            if self.circle_radius <= self.min_radius:
                self.circle_radius = self.min_radius
                self.state = "idle"
                
        elif self.state == "exiting":
            # Fast exit
            speed = (self.circle_radius + 10) * 0.25
            self.circle_radius += speed
            
            if self.circle_radius >= self.max_radius:
                self.close_app()
                return
                
        self.update()

    def on_click(self, x, y, button, pressed):
        if pressed and self.state != "exiting":
            self.start_exit()
            
    def on_move(self, x, y):
        # Intentionally a no-op: the trail records ONLY where the agent
        # moves the cursor (from move_mouse_smoothly). User-driven motion
        # shouldn't paint a cyan comet — that's voodo's signature, reserved
        # for "this is voodo guiding you to the spot".
        return

    def on_key_release(self, key):
        if key == keyboard.Key.pause or key == keyboard.Key.esc:
            if self.state != "exiting":
                self.start_exit()

    def start_exit(self):
        self.state = "exiting"

    def move_mouse_smoothly(self):
        current_x, current_y = pyautogui.position()
        float_x, float_y = float(current_x), float(current_y)
        speed = 25.0 # Much faster mouse movement
        
        while self.running and not self.user_took_control and self.state != "exiting":
            dx = self.target_x - float_x
            dy = self.target_y - float_y
            distance = math.hypot(dx, dy)
            
            if distance < speed:
                pyautogui.moveTo(self.target_x, self.target_y)
                self.trail.append((self.target_x, self.target_y, 1.0))
                break
                
            move_x = (dx / distance) * speed
            move_y = (dy / distance) * speed
            
            float_x += move_x
            float_y += move_y
            
            target_int_x = int(float_x)
            target_int_y = int(float_y)
            
            pyautogui.moveTo(target_int_x, target_int_y)
            self.trail.append((target_int_x, target_int_y, 1.0))
            
            time.sleep(0.01) # Faster loop for smoother high-speed movement
            
            actual_x, actual_y = pyautogui.position()
            if math.hypot(actual_x - target_int_x, actual_y - target_int_y) > 15:
                self.user_took_control = True
                break

    def close_app(self):
        self.running = False
        self._uninstall_winevent_hooks()
        self.mouse_listener.stop()
        self.keyboard_listener.stop()
        QApplication.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spotlight Mouse Guide Tool (PyQt5)")
    parser.add_argument("x", type=int, help="Target X coordinate")
    parser.add_argument("y", type=int, help="Target Y coordinate")
    parser.add_argument("--timeout", type=float, default=20.0,
                        help="Max seconds to wait before auto-closing (default 20).")
    parser.add_argument("--type-hint", default="",
                        help="If set, shows a bubble near the spotlight saying "
                             "'Type: <text>' — used in guide mode when the user "
                             "needs to type after clicking.")
    parser.add_argument("--label", default="",
                        help="Optional caption. Currently consumed only as a "
                             "fallback source for the type-hint bubble: when "
                             "--type-hint is empty and --label starts with "
                             "'Type: ', the rest is shown in the bubble.")
    args = parser.parse_args()

    # Fallback for older callers that stuff the hint into `label`
    # (graceful-degrade path on the agent side).
    if not args.type_hint and args.label:
        lbl = args.label.strip()
        for prefix in ("Type: ", "type: ", "TYPE: "):
            if lbl.startswith(prefix):
                args.type_hint = lbl[len(prefix):]
                break
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    # Per-monitor DPI awareness (level 2) — matches the executor's setting
    # so the coords passed in are interpreted as physical pixels on whatever
    # monitor the target lives on, not the legacy logical-pixel space.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        
    app = QApplication(sys.argv)
    guide = MouseGuide(args.x, args.y, timeout=args.timeout,
                       type_hint=args.type_hint)
    sys.exit(app.exec_())
