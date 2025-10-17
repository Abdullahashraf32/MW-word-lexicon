import sys
import time
import ctypes
from ctypes import wintypes, create_unicode_buffer

def to_int(arg):
  try:
    return int(arg)
  except Exception:
    return None

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
EM_GETSEL = 0x00B0

CF_UNICODETEXT = 13
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
VK_CONTROL = 0x11
VK_C = 0x43

class RECT(ctypes.Structure):
  _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class GUITHREADINFO(ctypes.Structure):
  _fields_ = [
    ("cbSize", wintypes.DWORD),
    ("flags", wintypes.DWORD),
    ("hwndActive", wintypes.HWND),
    ("hwndFocus", wintypes.HWND),
    ("hwndCapture", wintypes.HWND),
    ("hwndMenuOwner", wintypes.HWND),
    ("hwndMoveSize", wintypes.HWND),
    ("hwndCaret", wintypes.HWND),
    ("rcCaret", RECT)
  ]

def try_get_selection_from_hwnd(focus):
  try:
    bufname = create_unicode_buffer(256)
    user32.GetClassNameW(focus, bufname, ctypes.sizeof(bufname))
    cname = (bufname.value or "").lower()
    if "edit" in cname or "richedit" in cname or "richtextbox" in cname:
      start = wintypes.DWORD()
      end = wintypes.DWORD()
      try:
        user32.SendMessageW(focus, EM_GETSEL, ctypes.byref(start), ctypes.byref(end))
      except Exception:
        try:
          user32.SendMessageW(focus, EM_GETSEL, 0, 0)
        except Exception:
          return None
      s = int(start.value) if hasattr(start, "value") else 0
      e = int(end.value) if hasattr(end, "value") else 0
      if e > s:
        length = user32.SendMessageW(focus, WM_GETTEXTLENGTH, 0, 0)
        if length <= 0:
          return None
        buf = create_unicode_buffer(length + 1)
        user32.SendMessageW(focus, WM_GETTEXT, length + 1, ctypes.byref(buf))
        full = buf.value or ""
        try:
          sel = full[s:e]
        except Exception:
          sel = full
        if sel and sel.strip():
          return sel.strip()
  except Exception:
    return None
  return None

def clipboard_get_text():
  try:
    if not user32.OpenClipboard(None):
      return None
    try:
      h = user32.GetClipboardData(CF_UNICODETEXT)
      if not h:
        return None
      ptr = kernel32.GlobalLock(h)
      if not ptr:
        return None
      try:
        text = ctypes.wstring_at(ptr)
        return text
      finally:
        kernel32.GlobalUnlock(h)
    finally:
      user32.CloseClipboard()
  except Exception:
    try:
      user32.CloseClipboard()
    except Exception:
      pass
  return None

def clipboard_set_text(text):
  try:
    if not user32.OpenClipboard(None):
      return False
    try:
      user32.EmptyClipboard()
      encoded = text.encode("utf-16le")
      hGlobal = kernel32.GlobalAlloc(0x0040, len(encoded) + 2)
      if not hGlobal:
        return False
      lp = kernel32.GlobalLock(hGlobal)
      if not lp:
        kernel32.GlobalFree(hGlobal)
        return False
      try:
        ctypes.memmove(lp, encoded, len(encoded))
        ctypes.memmove(lp + len(encoded), b"\x00\x00", 2)
      finally:
        kernel32.GlobalUnlock(hGlobal)
      user32.SetClipboardData(CF_UNICODETEXT, hGlobal)
      return True
    finally:
      user32.CloseClipboard()
  except Exception:
    try:
      user32.CloseClipboard()
    except Exception:
      pass
  return False

def send_ctrl_c_to_window(hwnd, timeout=0.6):
  try:
    try:
      user32.ShowWindow(hwnd, 5)
      user32.SetForegroundWindow(hwnd)
    except Exception:
      pass
    original = clipboard_get_text()
    class KEYBDINPUT(ctypes.Structure):
      _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.ULONG_PTR)]
    class INPUT(ctypes.Structure):
      _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]
    inputs_struct = (INPUT * 4)()
    inputs_struct[0].type = INPUT_KEYBOARD
    inputs_struct[0].ki = KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0)
    inputs_struct[1].type = INPUT_KEYBOARD
    inputs_struct[1].ki = KEYBDINPUT(VK_C, 0, 0, 0, 0)
    inputs_struct[2].type = INPUT_KEYBOARD
    inputs_struct[2].ki = KEYBDINPUT(VK_C, 0, KEYEVENTF_KEYUP, 0, 0)
    inputs_struct[3].type = INPUT_KEYBOARD
    inputs_struct[3].ki = KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0)
    ctypes.windll.user32.SendInput(4, ctypes.byref(inputs_struct), ctypes.sizeof(inputs_struct[0]))
    deadline = time.time() + timeout
    while time.time() < deadline:
      time.sleep(0.04)
      val = clipboard_get_text()
      if val and val.strip():
        try:
          if original is not None:
            clipboard_set_text(original)
        except Exception:
          pass
        return val.strip()
    try:
      if original is not None:
        clipboard_set_text(original)
    except Exception:
      pass
  except Exception:
    pass
  return None

def try_ui_automation_text(hwnd):
  try:
    from comtypes.client import CreateObject
    uia = CreateObject("UIAutomationClient.CUIAutomation")
    element = uia.ElementFromHandle(hwnd)
    if not element:
      return None
    TextPatternId = 10014
    try:
      pattern = element.GetCurrentPattern(TextPatternId)
    except Exception:
      try:
        pattern = element.GetPattern(TextPatternId)
      except Exception:
        pattern = None
    if not pattern:
      return None
    try:
      ranges = pattern.GetSelection()
      if ranges and ranges.Length > 0:
        rng = ranges.GetElement(0) if hasattr(ranges, "GetElement") else ranges[0]
        try:
          text = rng.GetText(-1)
        except Exception:
          try:
            text = rng.GetText(sys.maxsize)
          except Exception:
            text = None
        if text and text.strip():
          return text.strip()
    except Exception:
      try:
        docRange = pattern.GetDocumentRange()
        if docRange:
          text = docRange.GetText(-1)
          if text and text.strip():
            return text.strip()
      except Exception:
        pass
  except Exception:
    pass
  return None

def get_selection_for_hwnd(hwnd):
  """
  Return selected text for a given hwnd (int). Returns string or None.
  """
  try:
    target = wintypes.HWND(int(hwnd))
  except Exception:
    return None
  try:
    res = try_ui_automation_text(target)
    if res:
      return res
    res = try_get_selection_from_hwnd(target)
    if res:
      return res
    res = send_ctrl_c_to_window(target)
    if res:
      return res
  except Exception:
    return None
  return None

def get_selection_for_foreground():
  try:
    foreground = user32.GetForegroundWindow()
    if not foreground:
      return None
    pid = wintypes.DWORD()
    threadId = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = user32.GetGUIThreadInfo(threadId, ctypes.byref(gui_info))
    focused_handle = gui_info.hwndFocus or gui_info.hwndActive or foreground if ok else foreground
    if focused_handle:
      res = try_ui_automation_text(focused_handle)
      if res:
        return res
      res = try_get_selection_from_hwnd(focused_handle)
      if res:
        return res
      res = send_ctrl_c_to_window(focused_handle)
      if res:
        return res
  except Exception:
    return None
  return None

def main():
  hwnd_arg = None
  if len(sys.argv) > 1:
    hwnd_arg = to_int(sys.argv[1])
  if hwnd_arg:
    res = get_selection_for_hwnd(hwnd_arg)
    if res:
      sys.stdout.write(res)
      return
  res = get_selection_for_foreground()
  if res:
    sys.stdout.write(res)

if __name__ == "__main__":
  main()
