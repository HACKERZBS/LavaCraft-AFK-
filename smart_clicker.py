"""
Smart Anti-AFK + AutoClicker v5 для Minecraft (LavaCraft)
- Anti-AFK: патруль вперёд-назад ~10 блоков
- AutoClick ПКМ: долгое удержание для лука
- Авто-админ
"""

import ctypes
import ctypes.wintypes
import time
import random
import threading
import sys
import os

# ============ АВТО-ПОВЫШЕНИЕ ДО АДМИНА ==================

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if not is_admin():
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{os.path.abspath(__file__)}"', None, 1
    )
    sys.exit(0)

import tkinter as tk

user32 = ctypes.windll.user32
try: user32.SetProcessDPIAware()
except: pass

# ===================== НАСТРОЙКИ ========================

# AutoClicker ЛКМ
CPS_MIN = 8
CPS_MAX = 10
JITTER_PIXELS = 3
HOLD_MIN_MS = 40
HOLD_MAX_MS = 80

# AutoClicker ПКМ (лук)
BOW_HOLD_MIN = 0.9       # Мин. удержание ПКМ для лука (сек)
BOW_HOLD_MAX = 1.4       # Макс. удержание ПКМ для лука (сек)
BOW_PAUSE_MIN = 0.1      # Пауза между выстрелами (сек)
BOW_PAUSE_MAX = 0.3

# Anti-AFK
# Скорость ходьбы в MC = ~4.317 блоков/сек
# 10 блоков ≈ 2.3 сек ходьбы
PATROL_BLOCKS = 10
WALK_SPEED = 4.317
PATROL_DURATION = PATROL_BLOCKS / WALK_SPEED  # ~2.3 сек
PATROL_PAUSE_MIN = 20.0   # Пауза между патрулями
PATROL_PAUSE_MAX = 25.0

# ================== WINDOWS API =========================

keybd_event = user32.keybd_event
mouse_event = user32.mouse_event
SendInput = user32.SendInput
GetAsyncKeyState = user32.GetAsyncKeyState
GetForegroundWindow = user32.GetForegroundWindow
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
MapVirtualKeyW = user32.MapVirtualKeyW
IsWindowVisible = user32.IsWindowVisible
EnumWindows = user32.EnumWindows

MAPVK_VK_TO_VSC = 0
MOUSEEVENTF_MOVE     = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
MOUSEEVENTF_RIGHTDOWN= 0x0008
MOUSEEVENTF_RIGHTUP  = 0x0010
KEYEVENTF_KEYUP    = 0x0002
KEYEVENTF_SCANCODE = 0x0008
INPUT_MOUSE    = 0
INPUT_KEYBOARD = 1

VK = {
    'W': 0x57, 'A': 0x41, 'S': 0x53, 'D': 0x44,
    'E': 0x45, 'SPACE': 0x20, 'SHIFT': 0x10,
    'CTRL': 0x11, '1': 0x31, '2': 0x32, '3': 0x33,
}
VK_F6 = 0x75; VK_F7 = 0x05; VK_F8 = 0x06

# ============= SendInput Structures ====================

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx",ctypes.c_long),("dy",ctypes.c_long),
        ("mouseData",ctypes.c_ulong),("dwFlags",ctypes.c_ulong),
        ("time",ctypes.c_ulong),("dwExtraInfo",ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk",ctypes.c_ushort),("wScan",ctypes.c_ushort),
        ("dwFlags",ctypes.c_ulong),("time",ctypes.c_ulong),
        ("dwExtraInfo",ctypes.POINTER(ctypes.c_ulong))]

class _INPUTunion(ctypes.Union):
    _fields_ = [("mi",MOUSEINPUT),("ki",KEYBDINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type",ctypes.c_ulong),("union",_INPUTunion)]

def _si(*inputs):
    n=len(inputs); arr=(INPUT*n)(*inputs)
    SendInput(n, ctypes.pointer(arr), ctypes.sizeof(INPUT))

# ============= ФОНОВЫЙ РЕЖИМ (PostMessage в окно MC) ====
# Когда включён — ввод идёт НЕ в активное окно, а напрямую в окно Minecraft
# через PostMessage. Окно MC может быть без фокуса / под другими окнами.

kernel32 = ctypes.windll.kernel32
kernel32.OpenProcess.restype = ctypes.wintypes.HANDLE
kernel32.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD,
                                                ctypes.wintypes.LPWSTR, ctypes.POINTER(ctypes.wintypes.DWORD)]
PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [ctypes.wintypes.HWND, ctypes.c_uint, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
PostMessageW.restype = ctypes.wintypes.BOOL
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

WM_KEYDOWN = 0x0100; WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201; WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204; WM_RBUTTONUP = 0x0205
MK_LBUTTON = 0x0001; MK_RBUTTON = 0x0002
VK_ESCAPE = 0x1B

def _win_title(h):
    try:
        l = GetWindowTextLengthW(h)
        if l == 0: return ""
        b = ctypes.create_unicode_buffer(l+1); GetWindowTextW(h, b, l+1)
        return b.value
    except: return ""

def _win_class(h):
    try:
        b = ctypes.create_unicode_buffer(256); user32.GetClassNameW(h, b, 256)
        return b.value
    except: return ""

def _proc_name(h):
    try:
        pid = ctypes.wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        hp = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
        if not hp: return ""
        try:
            buf = ctypes.create_unicode_buffer(520); n = ctypes.wintypes.DWORD(520)
            if kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)):
                return os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(hp)
    except: pass
    return ""

# Клавиши, которыми можно «кликать» вместо мыши (назначаются в игре на Атаку / Использовать)
KEYMAP = {'Мышь': None, 'F9': 0x78, 'F10': 0x79, 'F12': 0x7B,
          'Num0': 0x60, 'Num1': 0x61, 'Num2': 0x62}

class _BG:
    GLFW_CLASSES = ('GLFW30', 'LWJGL')
    NAME_KEYS = ('minecraft', 'lavacraft', 'lava')
    SKIP_PROCS = ('chrome.exe','msedge.exe','firefox.exe','opera.exe','brave.exe','explorer.exe',
                  'code.exe','notepad.exe','telegram.exe','discord.exe','python.exe','pythonw.exe',
                  'cmd.exe','windowsterminal.exe')
    JAVA_PROCS = ('javaw.exe', 'java.exe')

    def __init__(self):
        self.enabled = False
        self.hwnd = None
        self.info = ''
        self.dump = []
        self.key_lmb = None   # VK клавиши вместо ЛКМ (None = мышь)
        self.key_rmb = None   # VK клавиши вместо ПКМ
        self.guard = True     # возвращать фокус пользователю, если клик отдал его игре
        self._prev_fg = 0; self._click_t = 0.0; self._gt = None
        self._last = 0.0

    def find(self):
        cands = []
        def cb(h, lp):
            try:
                if not IsWindowVisible(h): return True
                t = _win_title(h)
                if not t: return True
                low = t.lower()
                if 'smart afk' in low: return True          # само окно кликера
                cls = _win_class(h)
                has_name = any(k in low for k in self.NAME_KEYS)
                is_glfw = cls in self.GLFW_CLASSES
                pr = _proc_name(h)
                is_java = pr in self.JAVA_PROCS
                if is_glfw and (is_java or has_name): score = 0   # само окно игры (LWJGL/GLFW)
                elif has_name and pr not in self.SKIP_PROCS: score = 1   # окно с LavaCraft/Minecraft в заголовке (любой процесс)
                elif is_java: score = 2                           # любое окно Java-процесса (запасной вариант)
                else: return True
                cands.append((score, h, t, cls, pr))
            except: pass
            return True
        try: EnumWindows(WNDENUMPROC(cb), 0)
        except: pass
        if not cands: return None
        cands.sort(key=lambda c: c[0])
        self.dump = [f'{c[2][:30]} [{c[4] or "?"}, {c[3]}]' for c in cands]
        c = cands[0]
        if c[3] not in self.GLFW_CLASSES:
            ch = self._find_child(c[1])
            if ch: c = (c[0], ch[0], c[2], ch[1], c[4])
        return c

    def _find_child(self, parent):
        res = []
        def cb(h, lp):
            try:
                cl = _win_class(h)
                if cl in self.GLFW_CLASSES: res.append((h, cl))
            except: pass
            return True
        try: user32.EnumChildWindows(parent, WNDENUMPROC(cb), 0)
        except: pass
        return res[0] if res else None

    def refresh(self, force=False):
        now = time.time()
        if not force and now - self._last < 1.0: return
        self._last = now
        c = self.find()
        if c:
            self.hwnd = c[1]
            self.info = f'{c[2][:40]} [{c[4] or "?"}, {c[3]}]'
        else:
            self.hwnd = None; self.info = ''

    def alive(self):
        if self.hwnd and user32.IsWindow(self.hwnd): return True
        self.hwnd = None
        self.refresh()
        return self.hwnd is not None

    def key(self, vk, down):
        if not self.alive(): return
        sc = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        lp = 1 | (sc << 16)
        if not down: lp |= (1 << 30) | (1 << 31)
        PostMessageW(self.hwnd, WM_KEYDOWN if down else WM_KEYUP, vk, lp)

    def click(self, button, down):
        vk = self.key_lmb if button == 'left' else self.key_rmb
        if vk: return self.key(vk, down)      # «клик» клавишей — не трогает фокус
        if not self.alive(): return
        r = ctypes.wintypes.RECT(); user32.GetClientRect(self.hwnd, ctypes.byref(r))
        lp = (((r.bottom // 2) & 0xFFFF) << 16) | ((r.right // 2) & 0xFFFF)
        if button == 'left':
            msg = WM_LBUTTONDOWN if down else WM_LBUTTONUP; wp = MK_LBUTTON if down else 0
        else:
            msg = WM_RBUTTONDOWN if down else WM_RBUTTONUP; wp = MK_RBUTTON if down else 0
        if self.guard:
            try:
                fg = user32.GetForegroundWindow()
                root = user32.GetAncestor(self.hwnd, 2)
                if fg and fg != root: self._prev_fg = fg
                self._click_t = time.time()
            except: pass
        PostMessageW(self.hwnd, msg, wp, lp)

    def dump_all(self):
        rows = []
        def cb(h, lp):
            try:
                if IsWindowVisible(h):
                    t = _win_title(h)
                    if t: rows.append(f'{h}\t{_proc_name(h) or "?"}\t{_win_class(h)}\t{t}')
            except: pass
            return True
        try: EnumWindows(WNDENUMPROC(cb), 0)
        except: pass
        return rows

    def pick_under_cursor(self):
        """Ручной выбор: берём окно, над которым сейчас курсор."""
        user32.WindowFromPoint.argtypes = [ctypes.wintypes.POINT]
        user32.WindowFromPoint.restype = ctypes.wintypes.HWND
        pt = ctypes.wintypes.POINT(); user32.GetCursorPos(ctypes.byref(pt))
        h = user32.WindowFromPoint(pt)
        if not h: return False
        chain = []; x = h
        while x and len(chain) < 20:
            chain.append(x); x = user32.GetParent(x)
        root = chain[-1]
        tgt = None
        for x in chain:
            if _win_class(x) in self.GLFW_CLASSES: tgt = x; break
        if tgt is None:
            ch = self._find_child(root)
            tgt = ch[0] if ch else root
        self.hwnd = tgt
        self.info = f'{_win_title(root)[:40]} [{_proc_name(root) or "?"}, {_win_class(tgt)}] (вручную)'
        return True

    # --- Сторож фокуса: если после нашего клика игра забрала фокус — вернуть прежнее окно ---
    def start_guard(self):
        if self._gt and self._gt.is_alive(): return
        self._gt = threading.Thread(target=self._guard_loop, daemon=True); self._gt.start()

    def _user_switching(self):
        # Alt / Win / кнопки мыши зажаты — значит окно переключает сам пользователь
        for vk in (0x12, 0x5B, 0x5C, 0x01, 0x02, 0x04):
            if GetAsyncKeyState(vk) & 0x8000: return True
        return False

    def _guard_loop(self):
        while self.enabled:
            time.sleep(0.01)
            try:
                if not self.guard or not self.hwnd: continue
                if time.time() - self._click_t > 0.4: continue
                root = user32.GetAncestor(self.hwnd, 2)
                fg = user32.GetForegroundWindow()
                prev = self._prev_fg
                if fg == root and prev and prev != root and user32.IsWindow(prev) and not user32.IsIconic(prev):
                    if self._user_switching(): continue
                    self._restore(prev)
                    self._click_t = 0.0
            except: pass

    def _restore(self, h):
        cur = kernel32.GetCurrentThreadId()
        t_fg = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
        att = bool(t_fg and t_fg != cur)
        if att: user32.AttachThreadInput(cur, t_fg, True)
        try: user32.SetForegroundWindow(h)
        finally:
            if att: user32.AttachThreadInput(cur, t_fg, False)

    def tap(self, vk, hold=0.06):
        self.key(vk, True); time.sleep(hold); self.key(vk, False)

BG = _BG()

# ============= ВВОД ====================================

def press_key(vk):
    if BG.enabled: return BG.key(vk, True)
    sc = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    keybd_event(vk, sc, 0, 0)
    i=INPUT(); i.type=INPUT_KEYBOARD; i.union.ki.wVk=vk; i.union.ki.wScan=sc; i.union.ki.dwFlags=0; _si(i)
    i2=INPUT(); i2.type=INPUT_KEYBOARD; i2.union.ki.wVk=0; i2.union.ki.wScan=sc; i2.union.ki.dwFlags=KEYEVENTF_SCANCODE; _si(i2)

def release_key(vk):
    if BG.enabled: return BG.key(vk, False)
    sc = MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
    keybd_event(vk, sc, KEYEVENTF_KEYUP, 0)
    i=INPUT(); i.type=INPUT_KEYBOARD; i.union.ki.wVk=vk; i.union.ki.wScan=sc; i.union.ki.dwFlags=KEYEVENTF_KEYUP; _si(i)
    i2=INPUT(); i2.type=INPUT_KEYBOARD; i2.union.ki.wVk=0; i2.union.ki.wScan=sc; i2.union.ki.dwFlags=KEYEVENTF_SCANCODE|KEYEVENTF_KEYUP; _si(i2)

def tap_key(vk, hold=None):
    if hold is None: hold=max(0.03,min(0.15,random.gauss(0.07,0.02)))
    press_key(vk); time.sleep(hold); release_key(vk)

def click_down(button='left'):
    if BG.enabled: return BG.click(button, True)
    f=MOUSEEVENTF_LEFTDOWN if button=='left' else MOUSEEVENTF_RIGHTDOWN
    mouse_event(f,0,0,0,0)
    i=INPUT(); i.type=INPUT_MOUSE; i.union.mi.dwFlags=f; _si(i)

def click_up(button='left'):
    if BG.enabled: return BG.click(button, False)
    f=MOUSEEVENTF_LEFTUP if button=='left' else MOUSEEVENTF_RIGHTUP
    mouse_event(f,0,0,0,0)
    i=INPUT(); i.type=INPUT_MOUSE; i.union.mi.dwFlags=f; _si(i)

def move_mouse(dx,dy):
    if BG.enabled: return   # в фоне мышь не двигаем
    mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)

# ============= ДЕТЕКТ ОКНА =============================

def get_active_title():
    try:
        h=GetForegroundWindow(); l=GetWindowTextLengthW(h)
        if l==0: return ""
        b=ctypes.create_unicode_buffer(l+1); GetWindowTextW(h,b,l+1)
        return b.value
    except: return ""

def is_mc_active():
    if BG.enabled: return BG.alive()
    t=get_active_title().lower()
    return any(k in t for k in ['minecraft','lavacraft','craft','java','lwjgl','mojang'])

# ============= РАНДОМИЗАЦИЯ ============================

def human_delay(mn,mx):
    t=random.uniform(mn,mx); d=random.gauss(1/t, 1/t*0.2)
    if random.random()<0.05: d+=random.uniform(0.05,0.2)
    return max(0.02, d)

def do_jitter():
    if random.random()<0.6:
        dx=random.gauss(0,JITTER_PIXELS*0.5); dy=random.gauss(0,JITTER_PIXELS*0.5)
        for _ in range(random.randint(2,3)):
            move_mouse(dx/3,dy/3); time.sleep(random.uniform(0.002,0.008))

def smooth_move(tdx,tdy,dur=0.3):
    steps=max(5,int(dur*60))
    for _ in range(steps):
        move_mouse(tdx/steps+random.gauss(0,0.5), tdy/steps+random.gauss(0,0.5))
        time.sleep(dur/steps)

# ============= АВТОКЛИКЕР ЛКМ ==========================

class ClickerLMB:
    def __init__(self):
        self.active=False; self.no_check=False

    def toggle(self):
        self.active=not self.active
        if self.active: threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        while self.active:
            if not self.no_check and not is_mc_active():
                time.sleep(0.3); continue
            do_jitter()
            h=max(0.02, random.gauss(random.uniform(HOLD_MIN_MS,HOLD_MAX_MS)/1000, 0.01))
            click_down('left'); time.sleep(h); click_up('left')
            time.sleep(human_delay(CPS_MIN, CPS_MAX))

    def stop(self): self.active=False

# ============= АВТОКЛИКЕР ПКМ (ЛУК) ====================

class ClickerRMB:
    """ПКМ с долгим удержанием для натяжки лука."""
    def __init__(self):
        self.active=False; self.no_check=False

    def toggle(self):
        self.active=not self.active
        if self.active: threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        while self.active:
            if not self.no_check and not is_mc_active():
                time.sleep(0.3); continue

            # Зажимаем ПКМ (натягиваем лук)
            hold = random.uniform(BOW_HOLD_MIN, BOW_HOLD_MAX)
            # Гауссовый шум для естественности
            hold = max(0.7, random.gauss(hold, 0.1))

            click_down('right')
            # Ждём с мелкими шагами чтобы можно было остановить
            end = time.time() + hold
            while self.active and time.time() < end:
                time.sleep(0.05)
            click_up('right')

            # Пауза между выстрелами
            pause = random.uniform(BOW_PAUSE_MIN, BOW_PAUSE_MAX)
            pause = max(0.2, random.gauss(pause, 0.1))
            time.sleep(pause)

    def stop(self):
        self.active=False
        # На всякий случай отпустить ПКМ
        try: click_up('right')
        except: pass

# ============= ANTI-AFK (ПАТРУЛЬ) ======================

class AntiAFK:
    """
    Патруль: вперёд N блоков → сразу назад N блоков → пауза 20-25 сек → повтор.
    Только ходьба (W/S), без прыжков и поворотов головы.
    N меняется ползунком в GUI (PATROL_BLOCKS).
    """
    def __init__(self):
        self.active=False; self.no_check=False

    def toggle(self):
        self.active=not self.active
        if self.active: threading.Thread(target=self._run,daemon=True).start()

    def _run(self):
        while self.active:
            if not self.no_check and not is_mc_active():
                time.sleep(0); continue

            # Вперёд ~N блоков и СРАЗУ назад ~N блоков (без паузы между ними)
            for key in (VK['W'], VK['S']):
                if not self.active:
                    break

                duration = PATROL_BLOCKS / WALK_SPEED

                press_key(key)
                try:
                    walk_end = time.time() + duration
                    while self.active and time.time() < walk_end:
                        time.sleep(0.05)
                finally:
                    release_key(key)

            # Пауза 20-25 сек
            pause = random.uniform(PATROL_PAUSE_MIN, PATROL_PAUSE_MAX)
            end = time.time() + pause
            while self.active and time.time() < end:
                time.sleep(0.15)

    def stop(self):
        self.active=False
        # На всякий случай отпустить W и S
        try: release_key(VK['W']); release_key(VK['S'])
        except: pass

# ============= GUI =====================================

class App:
    BG='#1a1a2e'; BG2='#16213e'; FG='#e0e0e0'
    GREEN='#00c853'; RED='#ff1744'; ACCENT='#0f3460'
    OFF='#2c2c54'; ON='#00c853'; YEL='#ffd600'

    def __init__(self):
        self.afk=AntiAFK(); self.cl=ClickerLMB(); self.cr=ClickerRMB()
        self.root=tk.Tk()
        self.root.title('MC Smart AFK+Clicker v5 [ADMIN]')
        self.root.geometry('460x790')
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        self.root.attributes('-topmost', True)
        self._build(); self._poll_hk(); self._upd_mc()

    def _build(self):
        tf=tk.Frame(self.root,bg=self.BG2,pady=10); tf.pack(fill='x')
        tk.Label(tf,text='\u26cf Smart AFK + AutoClicker v5',
                 font=('Segoe UI',15,'bold'),fg=self.YEL,bg=self.BG2).pack()
        tk.Label(tf,text='\u2705 \u0410\u0434\u043c\u0438\u043d\u0438\u0441\u0442\u0440\u0430\u0442\u043e\u0440',
                 font=('Segoe UI',9,'bold'),fg=self.GREEN,bg=self.BG2).pack()

        sf=tk.Frame(self.root,bg=self.BG,pady=6); sf.pack(fill='x',padx=20)
        self.mc_lbl=tk.Label(sf,text='...',font=('Segoe UI',9),
                             fg='#888',bg=self.BG,wraplength=400,justify='left')
        self.mc_lbl.pack(anchor='w')

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=4)

        cf=tk.Frame(self.root,bg=self.BG); cf.pack(fill='x',padx=25)
        self.skip_var=tk.BooleanVar(value=False)
        tk.Checkbutton(cf,text='\u041d\u0435 \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0442\u044c \u043e\u043a\u043d\u043e (\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u0432\u0441\u0435\u0433\u0434\u0430)',
                       variable=self.skip_var,font=('Segoe UI',9),
                       fg='#aaa',bg=self.BG,selectcolor=self.BG2,
                       activebackground=self.BG,activeforeground=self.FG,
                       command=self._on_skip).pack(anchor='w')

        # --- Фоновый режим ---
        bgf=tk.Frame(cf,bg=self.BG); bgf.pack(fill='x',pady=(4,0))
        self.bg_var=tk.BooleanVar(value=False)
        tk.Checkbutton(bgf,text='🕶 Фоновый режим',
                       variable=self.bg_var,font=('Segoe UI',9,'bold'),
                       fg=self.YEL,bg=self.BG,selectcolor=self.BG2,
                       activebackground=self.BG,activeforeground=self.FG,
                       command=self._on_bg).pack(side='left')
        for _t,_c in (('\u238b Esc',self._bg_esc),('\U0001f50d Окна',self._bg_list),('\U0001f3af Выбрать',self._bg_pick)):
            tk.Button(bgf,text=_t,font=('Segoe UI',8),
                      bg=self.ACCENT,fg='white',activebackground='#1a4a8a',
                      relief='flat',cursor='hand2',
                      command=_c).pack(side='right',padx=(4,0))

        mf=tk.Frame(cf,bg=self.BG); mf.pack(fill='x',pady=(2,0))
        tk.Label(mf,text='Клик клавишей (бинд в игре):',font=('Segoe UI',8),
                 fg='#aaa',bg=self.BG).pack(side='left')
        self.map_l=tk.StringVar(value='Мышь'); self.map_r=tk.StringVar(value='Мышь')
        self._mp=('Мышь','Мышь')
        for _lbl,_var in (('ПКМ',self.map_r),('ЛКМ',self.map_l)):
            om=tk.OptionMenu(mf,_var,*KEYMAP.keys(),command=self._on_map)
            om.configure(font=('Segoe UI',8),bg=self.OFF,fg=self.FG,activebackground=self.ACCENT,
                         activeforeground='white',relief='flat',highlightthickness=0,bd=0,width=5)
            om.pack(side='right',padx=(4,0))
            tk.Label(mf,text=_lbl,font=('Segoe UI',8),fg='#aaa',bg=self.BG).pack(side='right')
        self.guard_var=tk.BooleanVar(value=True)
        tk.Checkbutton(cf,text='Возвращать фокус после клика (игра не мешает)',
                       variable=self.guard_var,font=('Segoe UI',8),fg='#aaa',bg=self.BG,
                       selectcolor=self.BG2,activebackground=self.BG,activeforeground=self.FG,
                       command=lambda:setattr(BG,'guard',self.guard_var.get())).pack(anchor='w')

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=6)

        bf=tk.Frame(self.root,bg=self.BG); bf.pack(fill='x',padx=25)
        bf.columnconfigure(0,weight=1)

        self.ab,self.as_=self._btn(bf,'\U0001f6e1 Anti-AFK (\u043f\u0430\u0442\u0440\u0443\u043b\u044c \u0432\u043f\u0435\u0440\u0451\u0434-\u043d\u0430\u0437\u0430\u0434)','F6',self._t_afk,0)
        self.lb,self.ls=self._btn(bf,'\U0001f5b1 AutoClick \u041b\u041a\u041c (\u0431\u044b\u0441\u0442\u0440\u044b\u0439)','F7',self._t_lmb,1)
        self.rb,self.rs=self._btn(bf,'\U0001f3f9 AutoClick \u041f\u041a\u041c (\u043b\u0443\u043a)','F8',self._t_rmb,2)

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=6)

        # Ползунки
        sl=tk.Frame(self.root,bg=self.BG); sl.pack(fill='x',padx=25)
        self.sc_dist=self._slider(sl,'Дистанция патруля (блоков)',2,50,1,
                                  PATROL_BLOCKS,self._on_dist)
        self.sc_bow=self._slider(sl,'Зажатие лука (сек)',0.95,3.0,0.05,
                                 round((BOW_HOLD_MIN+BOW_HOLD_MAX)/2,2),self._on_bow)

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=6)

        # Инфо
        inf=tk.Frame(self.root,bg=self.BG); inf.pack(fill='x',padx=25)
        self.inf1=tk.Label(inf,font=('Consolas',9),fg='#888',bg=self.BG)
        self.inf1.pack(anchor='w')
        self.inf2=tk.Label(inf,font=('Consolas',9),fg='#888',bg=self.BG)
        self.inf2.pack(anchor='w')
        self._upd_info()

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=6)

        # Test
        ttf=tk.Frame(self.root,bg=self.BG); ttf.pack(fill='x',padx=25)
        tk.Button(ttf,text='\U0001f9ea \u0422\u0415\u0421\u0422 (3 \u0441\u0435\u043a)',
                  font=('Segoe UI',10),bg='#1b5e20',fg='white',
                  activebackground='#2e7d32',relief='flat',cursor='hand2',
                  command=self._test).pack(fill='x')

        tk.Frame(self.root,bg=self.ACCENT,height=2).pack(fill='x',padx=20,pady=6)

        tk.Label(self.root,text='\u041b\u043e\u0433:',font=('Segoe UI',9,'bold'),
                 fg='#666',bg=self.BG).pack(fill='x',padx=25,anchor='w')
        lf=tk.Frame(self.root,bg='#111')
        lf.pack(fill='both',expand=True,padx=25,pady=(2,12))
        self.logw=tk.Text(lf,height=5,bg='#111',fg='#4caf50',
                          font=('Consolas',9),relief='flat',state='disabled',
                          wrap='word',bd=0,padx=8,pady=4)
        self.logw.pack(fill='both',expand=True)
        self._log('\u0413\u043e\u0442\u043e\u0432\u043e! Anti-AFK = \u043f\u0430\u0442\u0440\u0443\u043b\u044c \u0432\u043f\u0435\u0440\u0451\u0434/\u043d\u0430\u0437\u0430\u0434. \u041f\u041a\u041c = \u0434\u043b\u044f \u043b\u0443\u043a\u0430.')

    def _slider(self,p,text,lo,hi,step,val,cmd):
        s=tk.Scale(p,label=text,from_=lo,to=hi,resolution=step,orient='horizontal',
                   length=400,font=('Segoe UI',9),fg=self.FG,bg=self.BG,
                   troughcolor=self.OFF,activebackground=self.ACCENT,
                   highlightthickness=0,bd=0)
        s.set(val)              # сначала значение, потом command (чтобы не вызвался при сборке)
        s.configure(command=cmd)
        s.pack(fill='x',pady=2)
        s.bind('<ButtonRelease-1>',lambda e:self._log(f'{text}: {s.get()}'))
        return s

    def _on_dist(self,v):
        global PATROL_BLOCKS
        PATROL_BLOCKS=int(float(v)); self._upd_info()

    def _on_bow(self,v):
        # ползунок = середина диапазона удержания, разброс ±0.25 с как в оригинале
        global BOW_HOLD_MIN, BOW_HOLD_MAX
        c=float(v)
        BOW_HOLD_MIN=round(c-0.25,2); BOW_HOLD_MAX=round(c+0.25,2)
        self._upd_info()

    def _upd_info(self):
        self.inf1.configure(text=f'Anti-AFK: {PATROL_BLOCKS} блоков вперёд-назад (~{PATROL_BLOCKS/WALK_SPEED:.1f}с)')
        self.inf2.configure(text=f'ЛКМ: {CPS_MIN}-{CPS_MAX} CPS  |  ПКМ (лук): удержание {BOW_HOLD_MIN}-{BOW_HOLD_MAX}с')

    def _btn(self,p,t,hk,cmd,row):
        f=tk.Frame(p,bg=self.BG,pady=5); f.grid(row=row,column=0,sticky='ew',padx=(0,8))
        b=tk.Button(f,text=f'{t}  [{hk}]',font=('Segoe UI',11,'bold'),
                    bg=self.OFF,fg=self.FG,activebackground='#3d3d6b',
                    activeforeground='white',relief='flat',cursor='hand2',
                    width=28,command=cmd); b.pack(fill='x')
        s=tk.Label(p,text='  \u25cf OFF',font=('Segoe UI',10,'bold'),
                   fg=self.RED,bg=self.BG,width=8); s.grid(row=row,column=1,sticky='e')
        return b,s

    def _ub(self,b,s,on):
        if on: b.configure(bg=self.ON,fg='#000'); s.configure(text='  \u25cf ON',fg=self.GREEN)
        else: b.configure(bg=self.OFF,fg=self.FG); s.configure(text='  \u25cf OFF',fg=self.RED)

    def _on_skip(self):
        v=self.skip_var.get()
        self.afk.no_check=v; self.cl.no_check=v; self.cr.no_check=v
        self._log(f'\u041f\u0440\u043e\u0432\u0435\u0440\u043a\u0430 \u043e\u043a\u043d\u0430: {"OFF" if v else "ON"}')

    def _on_bg(self):
        v=self.bg_var.get()
        if any(m.active for m in (self.afk,self.cl,self.cr)):
            self.bg_var.set(not v)   # откатить галочку
            self._log('Сначала выключи F6/F7/F8, потом меняй режим')
            return
        BG.enabled=v
        if v:
            BG.refresh(force=True)
            BG.start_guard()
            if BG.hwnd: self._log(f'Фон ON: подключился к {BG.info}')
            for d in BG.dump[:4]: self._log('  найдено: '+d)
            else: self._log('Фон ON: окно Minecraft пока не найдено, буду искать')
        else:
            BG.hwnd=None; BG.info=''
            self._log('Фон OFF: обычный режим (нужен фокус на MC)')

    def _bg_esc(self):
        if not BG.enabled:
            self._log('Esc: сначала включи фоновый режим'); return
        if not BG.alive():
            self._log('Esc: окно Minecraft не найдено'); return
        threading.Thread(target=lambda:BG.tap(VK_ESCAPE),daemon=True).start()
        self._log('Esc отправлен в MC')

    def _on_map(self,_=None):
        if self.cl.active or self.cr.active:
            self.map_l.set(self._mp[0]); self.map_r.set(self._mp[1])   # откатить
            self._log('Сначала выключи F7/F8, потом меняй клавиши клика')
            return
        self._mp=(self.map_l.get(),self.map_r.get())
        BG.key_lmb=KEYMAP[self._mp[0]]; BG.key_rmb=KEYMAP[self._mp[1]]
        self._log(f'Клик в фоне: ЛКМ→{self._mp[0]}, ПКМ→{self._mp[1]}')

    def _bg_list(self):
        rows=BG.dump_all()
        try:
            path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'windows_dump.txt')
            io_=open(path,'w',encoding='utf-8'); io_.write('hwnd\tprocess\tclass\ttitle\n'+'\n'.join(rows)); io_.close()
            self._log(f'Окон: {len(rows)}, полный список в windows_dump.txt')
        except Exception as e:
            self._log(f'Окон: {len(rows)} (файл не записан: {e})')
        keys=('java','lava','minecraft','craft')
        shown=0
        for r in rows:
            if any(k in r.lower() for k in keys) and shown<6:
                self._log('  '+r.replace('\t',' | ')); shown+=1

    def _bg_pick(self):
        if not BG.enabled:
            self._log('Выбор окна: сначала включи фоновый режим'); return
        self._log('Выбор: за 4 сек наведи курсор на окно Minecraft (не кликай)...')
        def _do():
            time.sleep(4)
            ok=BG.pick_under_cursor()
            self.root.after(0,lambda:self._log(f'Выбрано: {BG.info}' if ok else 'Под курсором нет окна'))
        threading.Thread(target=_do,daemon=True).start()

    def _t_afk(self):
        self.afk.toggle(); self._ub(self.ab,self.as_,self.afk.active)
        self._log(f'Anti-AFK {"ON \u2705" if self.afk.active else "OFF \u26d4"}')

    def _t_lmb(self):
        self.cl.toggle(); self._ub(self.lb,self.ls,self.cl.active)
        self._log(f'AutoClick \u041b\u041a\u041c {"ON" if self.cl.active else "OFF"}')

    def _t_rmb(self):
        self.cr.toggle(); self._ub(self.rb,self.rs,self.cr.active)
        self._log(f'AutoClick \u041f\u041a\u041c (\u043b\u0443\u043a) {"ON" if self.cr.active else "OFF"}')

    def _test(self):
        self._log('\u0422\u0415\u0421\u0422: 3 \u0441\u0435\u043a...')
        def _do():
            time.sleep(3)
            self.root.after(0,lambda:self._log('\u041d\u0430\u0436\u0438\u043c\u0430\u044e W...'))
            press_key(VK['W']); time.sleep(1.5); release_key(VK['W'])
            time.sleep(0.3)
            self.root.after(0,lambda:self._log('\u041d\u0430\u0437\u0430\u0434 S...'))
            press_key(VK['S']); time.sleep(1.5); release_key(VK['S'])
            time.sleep(0.3)
            self.root.after(0,lambda:self._log('\u0422\u0415\u0421\u0422 \u0433\u043e\u0442\u043e\u0432.'))
        threading.Thread(target=_do,daemon=True).start()

    def _log(self,msg):
        self.logw.configure(state='normal')
        self.logw.insert('end',f'[{time.strftime("%H:%M:%S")}] {msg}\n')
        self.logw.see('end')
        n=int(self.logw.index('end-1c').split('.')[0])
        if n>100: self.logw.delete('1.0','2.0')
        self.logw.configure(state='disabled')

    def _upd_mc(self):
        if BG.enabled:
            BG.alive()
            if BG.hwnd:
                self.mc_lbl.configure(text=f'🔗 Фон: {BG.info}',fg=self.GREEN)
            else:
                self.mc_lbl.configure(text='⏳ Фон: ищу окно Minecraft...',fg=self.YEL)
            self.root.after(800,self._upd_mc); return
        t=get_active_title()
        if is_mc_active():
            self.mc_lbl.configure(text=f'\u2705 MC: "{t}"',fg=self.GREEN)
        else:
            self.mc_lbl.configure(text=f'\u23f3 \u041e\u043a\u043d\u043e: "{t[:50]}"',fg='#888')
        self.root.after(800,self._upd_mc)

    def _poll_hk(self):
        if not hasattr(self,'_hk'): self._hk={VK_F6:0,VK_F7:0,VK_F8:0}
        for vk,cb in [(VK_F6,self._t_afk),(VK_F7,self._t_lmb),(VK_F8,self._t_rmb)]:
            d=bool(GetAsyncKeyState(vk)&0x8000)
            if d and not self._hk[vk]: cb()
            self._hk[vk]=d
        self.root.after(80,self._poll_hk)

    def run(self):
        try: self.root.mainloop()
        finally: self.afk.stop(); self.cl.stop(); self.cr.stop()

if __name__=='__main__':
    App().run()