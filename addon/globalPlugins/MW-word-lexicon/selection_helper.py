# This file is part of the MW-word-lexicon project.
# Copyright (C) 2025 Abdullah Ashraf
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.

import sys
import time
import ctypes
from ctypes import wintypes, create_unicode_buffer
import re

def _find_edit_like_child(root_hwnd):
  """
  Find a descendant of 'root_hwnd' whose class name looks like an Edit/RichEdit control.
  Returns HWND (int) or None.
  """
  try:
    FindWindowExW = user32.FindWindowExW
  except Exception:
    return None

  EDIT_KEYS = ("edit", "richedit", "richtextbox")
  child = wintypes.HWND(0)
  last = 0
  while True:
    child = FindWindowExW(root_hwnd, last, None, None)
    if not child:
      break
    # class name
    buf = create_unicode_buffer(256)
    try:
      user32.GetClassNameW(child, buf, ctypes.sizeof(buf))
      cname = (buf.value or "").lower()
    except Exception:
      cname = ""
    if any(k in cname for k in EDIT_KEYS):
      return child
    last = child

  # Try deeper: enumerate grandchildren of the first-level children
  last = 0
  while True:
    first_level = FindWindowExW(root_hwnd, last, None, None)
    if not first_level:
      break
    sublast = 0
    while True:
      sub = FindWindowExW(first_level, sublast, None, None)
      if not sub:
        break
      buf = create_unicode_buffer(256)
      try:
        user32.GetClassNameW(sub, buf, ctypes.sizeof(buf))
        cname = (buf.value or "").lower()
      except Exception:
        cname = ""
      if any(k in cname for k in EDIT_KEYS):
        return sub
      sublast = sub
    last = first_level
  return None

def _pick_numbered_line_word(full_text, start, end):
  """
  Robustly extract the word from numbered/bulleted lines,
      Returns the word if the current line matches, else None.
  """
  if not isinstance(full_text, str):
    return None
  n = len(full_text)
  L = max(0, int(start)); R = max(L, int(end))

  # Compute current line bounds around (start, end)
  line_start = full_text.rfind("\n", 0, L) + 1
  if line_start < 0:
    line_start = 0
  line_end = full_text.find("\n", R)
  if line_end == -1:
    line_end = n
  line = full_text[line_start:line_end]

  # Pattern: optional spaces, digits, optional spaces, one of - . ) : ],
  # optional spaces, WORD, then optional trailing punctuation/spaces
  m = re.match(r"^\s*\d+\s*[-\.\)\]:]\s*([A-Za-z][A-Za-z'\-]*)[^\w]*\s*$", line)
  if not m:
    return None
  return m.group(1)

def _expand_to_longest_word_on_line(full_text, start, end):
  """
  Last-resort: given full text and a (start, end) range, compute the current line,
  then return the longest [A-Za-z'-]+ token on that line (prefer one intersecting the range).
  """
  if not isinstance(full_text, str):
    return None
  n = len(full_text)
  L = max(0, int(start)); R = max(L, int(end))
  # line bounds
  line_start = full_text.rfind("\n", 0, L) + 1
  if line_start < 0: line_start = 0
  line_end = full_text.find("\n", R)
  if line_end == -1: line_end = n
  line = full_text[line_start:line_end]

  best = None
  for m in re.finditer(r"[A-Za-z][A-Za-z'\-]*", line):
    s0, e0 = m.span()
    abs_s, abs_e = line_start + s0, line_start + e0
    # Prefer a token intersecting the (start,end) range around the caret/selection.
    if not (abs_e <= L or abs_s >= R):
      return m.group(0)
    if not best or len(m.group(0)) > len(best):
      best = m.group(0)
  return best

def _word_at_index(full_text, index):
  """
  Return the full English-like word (letters, apostrophe, hyphen) surrounding 'index'.
  If no word surrounds the index, return None.
  """
  if not isinstance(full_text, str):
    return None
  n = len(full_text)
  if n == 0:
    return None
  i = max(0, min(int(index), n - 1))

  # If current char is not wordy, try the previous char once (for right-edge selections)
  def _isw(ch): return bool(re.match(r"[A-Za-z'\-]", ch))
  if not _isw(full_text[i]):
    if i > 0 and _isw(full_text[i - 1]):
      i -= 1
    else:
      return None

  L = i
  while L > 0 and _isw(full_text[L - 1]):
    L -= 1
  R = i + 1
  while R < n and _isw(full_text[R]):
    R += 1
  word = full_text[L:R].strip()
  return re.sub(r"[^\w'\-]+$", "", word) if word else None

def get_strict_word_from_foreground():
  """
  Return the *actual* word under selection/caret from a text edit control,
  even if the UI focus is not directly on that control (e.g., Notepad parent window).
  Strategy:
    - Get foreground and GUI thread info.
    - Prefer hwndFocus if it's Edit/RichEdit; otherwise, find an Edit/RichEdit descendant.
    - Use EM_GETSEL + WM_GETTEXT on that handle.
    - Remove CR characters, then:
        * numbered/bulleted regex
        * word-at-index (center for real selection, caret for e==s)
        * expand to word bounds
        * longest token on line as a last resort
  """
  try:
    foreground = user32.GetForegroundWindow()
    if not foreground:
      return None

    pid = wintypes.DWORD()
    threadId = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))

    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = user32.GetGUIThreadInfo(threadId, ctypes.byref(gui_info))

    focus = gui_info.hwndFocus or gui_info.hwndActive or foreground if ok else foreground
    target = focus

    # Ensure target is an Edit-like control; otherwise find a descendant.
    bufname = create_unicode_buffer(256)
    user32.GetClassNameW(target, bufname, ctypes.sizeof(bufname))
    cname = (bufname.value or "").lower()
    if not ("edit" in cname or "richedit" in cname or "richtextbox" in cname):
      found = _find_edit_like_child(foreground)
      if found:
        target = found
      else:
        # As a fallback, try a child under the focused window (if different)
        if focus and focus != foreground:
          found2 = _find_edit_like_child(focus)
          if found2:
            target = found2
          else:
            return None

    # Get selection range and entire text from the *text control* target
    start = wintypes.DWORD()
    end = wintypes.DWORD()
    try:
      user32.SendMessageW(target, EM_GETSEL, ctypes.byref(start), ctypes.byref(end))
    except Exception:
      try:
        user32.SendMessageW(target, EM_GETSEL, 0, 0)
      except Exception:
        return None
    s = int(getattr(start, "value", 0))
    e = int(getattr(end, "value", 0))

    length = user32.SendMessageW(target, WM_GETTEXTLENGTH, 0, 0)
    if length <= 0:
      return None

    buf = create_unicode_buffer(length + 1)
    user32.SendMessageW(target, WM_GETTEXT, length + 1, ctypes.byref(buf))
    full = buf.value or ""

    # Normalize CRLF → strip CR to make line math robust near EOL
    if "\r" in full:
      full = full.replace("\r", "")

    # Numbered/bulleted override
    numbered_word = _pick_numbered_line_word(full, s, e)
    if numbered_word:
      return numbered_word

    # Choose index: center of selection or caret
    idx = s if e == s else (s + e) // 2

    # Primary: word-at-index
    picked = _word_at_index(full, idx)
    if picked:
      return picked

    # Expand to word bounds from range/index
    L = s if e > s else idx
    R = e if e > s else idx
    while L > 0 and re.match(r"[A-Za-z'\-]", full[L - 1]): L -= 1
    while R < len(full) and re.match(r"[A-Za-z'\-]", full[R]): R += 1
    cand = (full[L:R] or "").strip()
    if cand:
      cand = re.sub(r"[^\w'\-]+$", "", cand)
    if cand:
      return cand

    # Last resort: dominant token on the current line
    fallback = _expand_to_longest_word_on_line(full, s, e)
    if fallback:
      return fallback

  except Exception:
    return None
  return None

def to_int(arg):
  """
  Safely converts an argument to an integer.

  Args:
    arg: The value to convert.

  Returns:
    An integer if the conversion is successful, otherwise None.
  """
  try:
    return int(arg)
  except Exception:
    return None

# Load necessary Windows libraries.
# user32.dll contains functions for user interface tasks like window management.
# kernel32.dll provides access to core OS functions like memory management.
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Define Windows message constants used to interact with window controls.
WM_GETTEXT = 0x000D  # Message to get the text of a window/control.
WM_GETTEXTLENGTH = 0x000E  # Message to get the length of the text.
EM_GETSEL = 0x00B0  # Message specific to Edit controls to get the selection range.

# Define Windows constants for clipboard and keyboard input operations.
CF_UNICODETEXT = 13  # Clipboard format for Unicode text.
INPUT_KEYBOARD = 1  # Indicates a keyboard event for the SendInput function.
KEYEVENTF_KEYUP = 0x0002  # Indicates a key-up event.
VK_CONTROL = 0x11  # Virtual-Key code for the Control key.
VK_C = 0x43  # Virtual-Key code for the 'C' key.

class RECT(ctypes.Structure):
  """
  A ctypes structure that maps to the Windows RECT structure.
  It defines the coordinates of the upper-left and lower-right corners of a rectangle.
  """
  _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

class GUITHREADINFO(ctypes.Structure):
  """
  A ctypes structure that maps to the Windows GUITHREADINFO structure.
  It contains information about a GUI thread, including various window handles
  associated with the thread such as the active window and the focused window.
  """
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
  """
  Get selected text from a window handle using EM_GETSEL/WM_GETTEXT.
  Handles both real selections and caret-only cases by expanding to word bounds.
  """
  try:
    # Identify class name
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

      s = int(getattr(start, "value", 0))
      e = int(getattr(end, "value", 0))

      length = user32.SendMessageW(focus, WM_GETTEXTLENGTH, 0, 0)
      if length <= 0:
        return None

      buf = create_unicode_buffer(length + 1)
      user32.SendMessageW(focus, WM_GETTEXT, length + 1, ctypes.byref(buf))
      full = buf.value or ""
      # Hard override for numbered-list lines like "3-water.":
      # If the current line matches, ignore the raw selection range and return the word.
      numbered_word = _pick_numbered_line_word(full, s, e)
      if numbered_word:
        return numbered_word
      # Numbered-line hard match (covers 1-, 1 -, 1., 1), 1:, etc.)
      numbered_word = _pick_numbered_line_word(full, s, e)
      if numbered_word:
        return numbered_word

      # Case 1: real selection (e > s) → slice then normalize/expand.
      if e > s:
        try:
          sel = full[s:e]
        except Exception:
          sel = full
        sel = (sel or "").strip()

        # Very short alpha? fix with word-at-index first
        if sel and len(sel) <= 4 and re.match(r"^[A-Za-z]+$", sel):
          center = (s + e) // 2
          picked = _word_at_index(full, center)
          if picked:
            sel = picked
          else:
            # Expand left/right on raw text as fallback
            L, R = s, e
            while L > 0 and re.match(r"[A-Za-z'\-]", full[L - 1]): L -= 1
            while R < len(full) and re.match(r"[A-Za-z'\-]", full[R]): R += 1
            sel = (full[L:R] or sel).strip()

        # Trim trailing punctuation
        if sel:
          sel = re.sub(r"[^\w'\-]+$", "", sel)

        if sel:
          # Still too short? choose the dominant token on this line
          if len(sel) <= 4 and re.match(r"^[A-Za-z]+$", sel):
            fallback = _expand_to_longest_word_on_line(full, s, e)
            if fallback:
              sel = fallback
          return sel.strip() or None

      # Case 2: caret only (e == s) → expand around caret to word bounds.
      if e == s:
        picked = _word_at_index(full, s)
        if picked:
          return picked

        L = R = s
        while L > 0 and re.match(r"[A-Za-z'\-]", full[L - 1]): L -= 1
        while R < len(full) and re.match(r"[A-Za-z'\-]", full[R]): R += 1
        cand = (full[L:R] or "").strip()
        if cand:
          cand = re.sub(r"[^\w'\-]+$", "", cand)
        if cand:
          return cand

        fallback = _expand_to_longest_word_on_line(full, s, e)
        if fallback:
          return fallback

  except Exception:
    return None
  return None

def clipboard_get_text():
  """
  Retrieves Unicode text from the system clipboard.

  Returns:
    The text from the clipboard as a string, or None if it fails
    or if the clipboard does not contain Unicode text.
  """
  try:
    if not user32.OpenClipboard(None):
      return None
    try:
      # Get handle to clipboard data in Unicode text format.
      h = user32.GetClipboardData(CF_UNICODETEXT)
      if not h:
        return None
      
      # Lock the memory handle to get a pointer to the text.
      ptr = kernel32.GlobalLock(h)
      if not ptr:
        return None
      try:
        # Read the null-terminated Unicode string from the pointer.
        text = ctypes.wstring_at(ptr)
        return text
      finally:
        # Unlock the memory.
        kernel32.GlobalUnlock(h)
    finally:
      # Close the clipboard.
      user32.CloseClipboard()
  except Exception:
    # Ensure the clipboard is closed even if an error occurs.
    try:
      user32.CloseClipboard()
    except Exception:
      pass
  return None

def clipboard_set_text(text):
  """
  Places the given Unicode text onto the system clipboard.

  Args:
    text (str): The text to be placed on the clipboard.

  Returns:
    True if successful, False otherwise.
  """
  try:
    if not user32.OpenClipboard(None):
      return False
    try:
      # Clear the current clipboard content.
      user32.EmptyClipboard()
      
      # Encode the text as UTF-16 Little Endian for Windows.
      encoded = text.encode("utf-16le")
      
      # Allocate a movable block of memory from the global heap.
      hGlobal = kernel32.GlobalAlloc(0x0040, len(encoded) + 2) # GHND, add 2 for null terminator.
      if not hGlobal:
        return False
        
      # Lock the memory to get a pointer.
      lp = kernel32.GlobalLock(hGlobal)
      if not lp:
        kernel32.GlobalFree(hGlobal)
        return False
      try:
        # Copy the encoded text and a null terminator into the allocated memory.
        ctypes.memmove(lp, encoded, len(encoded))
        ctypes.memmove(lp + len(encoded), b"\x00\x00", 2)
      finally:
        kernel32.GlobalUnlock(hGlobal)
        
      # Set the clipboard data with the handle to the memory block.
      user32.SetClipboardData(CF_UNICODETEXT, hGlobal)
      return True
    finally:
      user32.CloseClipboard()
  except Exception:
    # Ensure the clipboard is closed even if an error occurs.
    try:
      user32.CloseClipboard()
    except Exception:
      pass
  return False

def send_ctrl_c_to_window(hwnd, timeout=0.6):
  """
  A fallback method to get selected text by simulating a Ctrl+C keypress
  in the target window and then reading the text from the clipboard.

  Args:
    hwnd (wintypes.HWND): The handle to the target window.
    timeout (float): The time in seconds to wait for the clipboard to update.

  Returns:
    The copied text as a string if successful, otherwise None.
  """
  try:
    # Bring the window to the foreground to receive key presses.
    try:
      user32.ShowWindow(hwnd, 5) # SW_SHOW
      user32.SetForegroundWindow(hwnd)
    except Exception:
      pass
      
    # Save the original clipboard content to restore it later.
    original = clipboard_get_text()

    # Define ctypes structures for keyboard input simulation.
    class KEYBDINPUT(ctypes.Structure):
      _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", wintypes.ULONG_PTR)]
    
    class INPUT(ctypes.Structure):
      _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT)]

    # Create an array of INPUT structures for the key presses:
    # 1. Press Control
    # 2. Press 'C'
    # 3. Release 'C'
    # 4. Release Control
    inputs_struct = (INPUT * 4)()
    inputs_struct[0].type = INPUT_KEYBOARD
    inputs_struct[0].ki = KEYBDINPUT(VK_CONTROL, 0, 0, 0, 0)
    inputs_struct[1].type = INPUT_KEYBOARD
    inputs_struct[1].ki = KEYBDINPUT(VK_C, 0, 0, 0, 0)
    inputs_struct[2].type = INPUT_KEYBOARD
    inputs_struct[2].ki = KEYBDINPUT(VK_C, 0, KEYEVENTF_KEYUP, 0, 0)
    inputs_struct[3].type = INPUT_KEYBOARD
    inputs_struct[3].ki = KEYBDINPUT(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0, 0)

    # Send the keypress events.
    ctypes.windll.user32.SendInput(4, ctypes.byref(inputs_struct), ctypes.sizeof(inputs_struct[0]))

    # Poll the clipboard for a short period to see if new text appears.
    deadline = time.time() + timeout
    while time.time() < deadline:
      time.sleep(0.04)
      val = clipboard_get_text()
      if val and val.strip():
        # If new text is found, restore the original clipboard content and return the new text.
        try:
          if original is not None:
            clipboard_set_text(original)
        except Exception:
          pass
        return val.strip()
        
    # If the timeout is reached, restore the original clipboard content.
    try:
      if original is not None:
        clipboard_set_text(original)
    except Exception:
      pass
  except Exception:
    pass
  return None

def try_ui_automation_text(hwnd):
  """
  Try to read the exact selection via Microsoft UI Automation (UIA).
  If the selection is a too-short alpha prefix (e.g., 'wat' from 'water'),
  first normalize to the enclosing word, then (if needed) walk left/right
  character-by-character until true word boundaries are reached.
  Docs: IUIAutomationTextRange::ExpandToEnclosingUnit / MoveEndpointByUnit.
  """
  try:
    from comtypes.client import CreateObject
    import re as _re

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

    EP_START, EP_END = 0, 1       # TextPatternRangeEndpoint
    TU_CHAR, TU_WORD = 0, 2       # TextUnit Character/Word

    def _strip_trailing_punct(s):
      return _re.sub(r"[^\w'\-]+$", "", s or "").strip()

    def _txt(r, n=-1):
      try:
        return (r.GetText(n) or "").strip()
      except Exception:
        return ""

    # Selection first
    try:
      ranges = pattern.GetSelection()
      if not ranges:
        return None
      rng = ranges.GetElement(0) if hasattr(ranges, "GetElement") else ranges[0]
      txt = _txt(rng, -1)

      # If it's already a decent length, just clean punctuation.
      if txt and len(txt) > 4:
        return _strip_trailing_punct(txt)

      # Normalize to Word if provider supports it.
      if txt and _re.match(r"^[A-Za-z]+$", txt):
        try:
          w = rng.Clone()
          w.ExpandToEnclosingUnit(TU_WORD)
          t2 = _strip_trailing_punct(_txt(w, -1))
          if t2 and len(t2) >= len(txt):
            return t2
        except Exception:
          pass

      # Manual left walk to word boundary.
      try:
        left = rng.Clone()
        while True:
          probe = left.Clone()
          moved = probe.MoveEndpointByUnit(EP_START, TU_CHAR, -1)
          if not moved:
            break
          check = probe.Clone()
          check.MoveEndpointByRange(EP_END, probe, EP_START)
          c = _txt(check, 1)
          if not c or not _re.match(r"[A-Za-z'\-]", c):
            break
          left = probe
      except Exception:
        left = rng

      # Manual right walk to word boundary.
      try:
        right = left.Clone()
        while True:
          probe = right.Clone()
          moved = probe.MoveEndpointByUnit(EP_END, TU_CHAR, +1)
          if not moved:
            break
          check = probe.Clone()
          check.MoveEndpointByRange(EP_START, probe, EP_END)
          c = _txt(check, 1)
          if not c or not _re.match(r"[A-Za-z'\-]", c):
            break
          right = probe
      except Exception:
        right = left

      expanded = _strip_trailing_punct(_txt(right, -1))
      if expanded:
        return expanded

      if txt:
        return _strip_trailing_punct(txt)
    except Exception:
      pass

    # Weak fallback: whole document (rarely used for exact selection)
    try:
      doc = pattern.GetDocumentRange()
      if doc:
        t = _strip_trailing_punct(_txt(doc, -1))
        if t:
          return t
    except Exception:
      pass

  except Exception:
    pass
  return None

def get_selection_for_hwnd(hwnd):
  """
  Try in order:
    1) UIA (with word expansion)
    2) EM_GETSEL/WM_GETTEXT (with word-boundary expansion)
    3) Simulated Ctrl+C
  """
  try:
    target = wintypes.HWND(int(hwnd))
  except Exception:
    return None

  try:
    # 1) UIA
    res = try_ui_automation_text(target)
    if res:
      # If UIA returned a too-short alpha prefix, do not return yet.
      if len(res) <= 4 and re.match(r"^[A-Za-z]+$", res or ""):
        pass  # fall through to EM_GETSEL path
      else:
        return res

    # 2) EM_GETSEL path
    res = try_get_selection_from_hwnd(target)
    if res:
      return res

    # 3) Simulate Ctrl+C
    res = send_ctrl_c_to_window(target)
    if res:
      return res
  except Exception:
    return None
  return None

def get_selection_for_foreground():
  """
  Get the selected text from the current foreground control.
  Order:
    1) UIA (expand to word) — but DO NOT return if it looks like a short alpha prefix (e.g., "wat")
    2) EM_GETSEL/WM_GETTEXT (handles real selection and caret-only; expands to word bounds)
    3) Simulated Ctrl+C as a last resort
  """
  try:
    foreground = user32.GetForegroundWindow()
    if not foreground:
      return None

    # Find the focused child control for the foreground thread
    pid = wintypes.DWORD()
    threadId = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))

    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = user32.GetGUIThreadInfo(threadId, ctypes.byref(gui_info))

    focused_handle = gui_info.hwndFocus or gui_info.hwndActive or foreground if ok else foreground
    if not focused_handle:
      return None

    # 1) UIA — if it returns a short alpha prefix, do not return yet; fall through to EM_GETSEL
    res = try_ui_automation_text(focused_handle)
    if res:
      if len(res) <= 4 and re.match(r"^[A-Za-z]+$", res or ""):
        # Too-short alpha prefix like "wat" → let EM_GETSEL handle it with word-boundary expansion
        pass
      else:
        return res

    # 2) EM_GETSEL/WM_GETTEXT — this path expands to full word bounds and handles caret-only cases
    res = try_get_selection_from_hwnd(focused_handle)
    if res:
      return res

    # 3) Simulate Ctrl+C — broad compatibility fallback
    res = send_ctrl_c_to_window(focused_handle)
    if res:
      return res

  except Exception:
    return None
  return None

def _expand_word_bounds(full_text, start, end):
  """
  Given the full control text and a (start, end) selection range,
  expand the range to cover the entire English-like word (letters, apostrophe, hyphen).
  Returns (expanded_text, new_start, new_end).
  """
  if not isinstance(full_text, str):
    return None, start, end
  n = len(full_text)
  L = max(0, int(start))
  R = max(L, int(end))

  # Move left while previous char is part of a word.
  while L > 0 and re.match(r"[A-Za-z'\-]", full_text[L - 1]):
    L -= 1
  # Move right while next char is part of a word.
  while R < n and re.match(r"[A-Za-z'\-]", full_text[R]):
    R += 1

  expanded = full_text[L:R].strip()
  return (expanded if expanded else None), L, R

def main():
  """
  The main entry point for the script.
  It checks for a command-line argument which is expected to be a window
  handle (hwnd). If provided, it gets the selection for that handle.
  If not, it gets the selection for the current foreground window.
  The result is printed to standard output.
  """
  hwnd_arg = None
  if len(sys.argv) > 1:
    hwnd_arg = to_int(sys.argv[1])
  
  if hwnd_arg:
    # If an hwnd is provided as an argument, use it.
    res = get_selection_for_hwnd(hwnd_arg)
    if res:
      sys.stdout.write(res)
      return
      
  # Otherwise, get the selection from the foreground window.
  res = get_selection_for_foreground()
  if res:
    sys.stdout.write(res)

# This standard Python construct ensures that the main() function is called
# only when the script is executed directly (not when imported as a module).
if __name__ == "__main__":
  main()