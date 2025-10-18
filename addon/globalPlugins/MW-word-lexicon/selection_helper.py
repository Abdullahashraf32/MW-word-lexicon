import sys
import time
import ctypes
from ctypes import wintypes, create_unicode_buffer

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
  Tries to get the selected text from a window handle (hwnd) by using
  Windows messages. This method works well for standard controls like
  'Edit', 'RichEdit', etc.

  Args:
    focus (wintypes.HWND): The handle to the window/control.

  Returns:
    The selected text as a string if successful, otherwise None.
  """
  try:
    # Get the class name of the window to check if it's a known text control.
    bufname = create_unicode_buffer(256)
    user32.GetClassNameW(focus, bufname, ctypes.sizeof(bufname))
    cname = (bufname.value or "").lower()

    # Check if the control is a type that supports EM_GETSEL.
    if "edit" in cname or "richedit" in cname or "richtextbox" in cname:
      start = wintypes.DWORD()
      end = wintypes.DWORD()
      
      # Send the EM_GETSEL message to get the start and end of the selection.
      try:
        user32.SendMessageW(focus, EM_GETSEL, ctypes.byref(start), ctypes.byref(end))
      except Exception:
        # Fallback for some architectures/control versions.
        try:
          user32.SendMessageW(focus, EM_GETSEL, 0, 0)
        except Exception:
          return None

      s = int(start.value) if hasattr(start, "value") else 0
      e = int(end.value) if hasattr(end, "value") else 0

      # If there is a selection (end > start).
      if e > s:
        # Get the total length of the text in the control.
        length = user32.SendMessageW(focus, WM_GETTEXTLENGTH, 0, 0)
        if length <= 0:
          return None
        
        # Get the full text from the control.
        buf = create_unicode_buffer(length + 1)
        user32.SendMessageW(focus, WM_GETTEXT, length + 1, ctypes.byref(buf))
        full = buf.value or ""
        
        # Slice the full text to get the selected part.
        try:
          sel = full[s:e]
        except Exception:
          sel = full # Fallback to full text on slicing error.
        
        if sel and sel.strip():
          return sel.strip()
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
  Tries to get the selected text from a window handle using the
  Microsoft UI Automation (UIA) framework. This is a more modern
  accessibility API that works with a wider range of applications.

  Args:
    hwnd (wintypes.HWND): The handle to the window/control.

  Returns:
    The selected text as a string if successful, otherwise None.
  """
  try:
    from comtypes.client import CreateObject
    
    # Create an instance of the CUIAutomation object.
    uia = CreateObject("UIAutomationClient.CUIAutomation")
    
    # Get the UIA element corresponding to the window handle.
    element = uia.ElementFromHandle(hwnd)
    if not element:
      return None
      
    # The ID for the TextPattern in UIA.
    TextPatternId = 10014
    
    # Get the TextPattern from the element.
    try:
      pattern = element.GetCurrentPattern(TextPatternId)
    except Exception:
      try:
        pattern = element.GetPattern(TextPatternId)
      except Exception:
        pattern = None
        
    if not pattern:
      return None
      
    # Try to get the selected text ranges.
    try:
      ranges = pattern.GetSelection()
      if ranges and ranges.Length > 0:
        rng = ranges.GetElement(0) if hasattr(ranges, "GetElement") else ranges[0]
        # Get the text from the first selection range.
        try:
          text = rng.GetText(-1) # -1 means get the entire text of the range.
        except Exception:
          try:
            text = rng.GetText(sys.maxsize) # Fallback for some implementations.
          except Exception:
            text = None
        if text and text.strip():
          return text.strip()
    except Exception:
      # If getting selection fails, try getting the entire document text as a fallback.
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
  Gets the selected text for a given window handle by trying several methods
  in order of reliability and performance.

  The order of methods is:
  1. UI Automation (most modern and reliable).
  2. Direct Windows messages (fast but limited to standard controls).
  3. Simulating Ctrl+C (broadest compatibility but slower and intrusive).

  Args:
    hwnd (int): The window handle as an integer.

  Returns:
    The selected text as a string, or None if all methods fail.
  """
  try:
    target = wintypes.HWND(int(hwnd))
  except Exception:
    return None
    
  try:
    # 1. Try with UI Automation first.
    res = try_ui_automation_text(target)
    if res:
      return res
      
    # 2. If that fails, try with standard window messages.
    res = try_get_selection_from_hwnd(target)
    if res:
      return res
      
    # 3. As a last resort, try simulating Ctrl+C.
    res = send_ctrl_c_to_window(target)
    if res:
      return res
  except Exception:
    return None
  return None

def get_selection_for_foreground():
  """
  Gets the selected text from the currently active foreground window.
  It intelligently finds the specific control that has focus and then
  attempts to get the selection from it.

  Returns:
    The selected text as a string, or None if it cannot be retrieved.
  """
  try:
    # Get the handle of the window in the foreground.
    foreground = user32.GetForegroundWindow()
    if not foreground:
      return None
      
    # Get the thread and process ID for the foreground window.
    pid = wintypes.DWORD()
    threadId = user32.GetWindowThreadProcessId(foreground, ctypes.byref(pid))
    
    # Get detailed GUI thread info to find the focused control.
    gui_info = GUITHREADINFO()
    gui_info.cbSize = ctypes.sizeof(GUITHREADINFO)
    ok = user32.GetGUIThreadInfo(threadId, ctypes.byref(gui_info))
    
    # The focused handle is the most specific target. Fall back to active or foreground window.
    focused_handle = gui_info.hwndFocus or gui_info.hwndActive or foreground if ok else foreground
    
    if focused_handle:
      # Use the same multi-method approach as get_selection_for_hwnd.
      # 1. Try UI Automation.
      res = try_ui_automation_text(focused_handle)
      if res:
        return res
        
      # 2. Try standard messages.
      res = try_get_selection_from_hwnd(focused_handle)
      if res:
        return res
        
      # 3. Try simulating Ctrl+C.
      res = send_ctrl_c_to_window(focused_handle)
      if res:
        return res
  except Exception:
    return None
  return None

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