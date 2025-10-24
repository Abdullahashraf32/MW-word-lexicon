# -*- coding: UTF-8 -*-
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

import os
import sys
import subprocess
import globalPluginHandler
import ui
import time
import api
import requests
import re
import wx
from scriptHandler import script
import config
import gui
from gui.settingsDialogs import SettingsPanel
from . import thesaurus
import json
import threading

# Get the directory of the current addon.
addon_dir = os.path.dirname(__file__)
# Add the addon directory to the system path to ensure local modules can be imported.
if addon_dir not in sys.path:
  sys.path.insert(0, addon_dir)

# Try to import the selection_helper module, which contains platform-specific
# code to get selected text from other applications.
try:
  from . import selection_helper
except Exception:
  try:
    import selection_helper
  except Exception:
    selection_helper = None

# A global variable to track any currently open dialog from this addon.
# This is used to prevent opening multiple dialogs at once.
OPEN_DIALOG = None

def _clear_open_dialog(evt, frame):
  """
  Event handler to reset the OPEN_DIALOG global variable when a dialog is closed.
  This ensures that a new dialog can be opened later.

  Args:
    evt: The wx event object.
    frame: The frame object being closed.
  """
  global OPEN_DIALOG
  try:
    OPEN_DIALOG = None
  except Exception:
    pass
  # Allow the event to propagate.
  try:
    evt.Skip()
  except Exception:
    pass

def _call_selection_helper_for_hwnd(hwnd, out_container):
  """
  A thread-safe function to call the selection helper for a specific window handle (hwnd).
  The result is placed into the 'out_container' list.

  Args:
    hwnd (int): The window handle to get the selection from.
    out_container (list): A list to which the result will be appended.
  """
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_hwnd(hwnd)
      out_container.append(res)
  except Exception:
    out_container.append(None)

def _call_selection_helper_foreground(out_container):
  """
  A thread-safe function to call the selection helper for the current foreground window.
  The result is placed into the 'out_container' list.

  Args:
    out_container (list): A list to which the result will be appended.
  """
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_foreground()
      out_container.append(res)
  except Exception:
    out_container.append(None)

# The URL for the dictionary API proxy.
DICTIONARY_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}"

def strip_html_tags(text):
  """
  Removes HTML tags from a given string using a regular expression.

  Args:
    text (str): The string containing HTML tags.

  Returns:
    str: The string with HTML tags removed.
  """
  return re.sub(r'<[^>]+>', '', text)

def play_with_ffplay(audio_url, speed=100, volume=100):
  """
  Plays an audio stream from a URL using the bundled ffplay.exe.

  Args:
    audio_url (str): The URL of the audio to play.
    speed (int): The playback speed percentage (50-200).
    volume (int): The playback volume percentage (0-100).
  """
  try:
    ffplay_path = os.path.join(os.path.dirname(__file__), "bin", "ffplay.exe")
    # Clamp speed and volume to valid ranges and convert to ffplay format.
    rate = max(50, min(speed, 200)) / 100
    vol = max(0, min(volume, 100))
    # Launch ffplay in a separate process to play the audio without blocking.
    subprocess.Popen([
      ffplay_path,
      "-nodisp",  # No video window.
      "-autoexit",  # Exit when playback finishes.
      "-af", f"atempo={rate:.2f},volume={vol / 100:.2f}",  # Audio filters for speed and volume.
      audio_url
    ])
  except Exception as e:
    ui.message(f"Audio playback failed: {e}")

def get_word_of_the_day():
  """
  Fetches and parses the "Word of the Day" from the API endpoint.

  Returns:
    str: A formatted string "Word - Definition", or just "Word" if parsing fails,
         or None if the request fails.
  """
  url = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/wotd"
  response = requests.get(url)
  if response.status_code == 200:
    html = response.text
    # Use regex to find the word and its definition in the HTML response.
    word_match = re.search(r'<h2[^>]*class="word-header-txt"[^>]*>(.*?)</h2>', html, re.DOTALL)
    word = strip_html_tags(word_match.group(1).strip()) if word_match else None
    def_match = re.search(r'<div[^>]*class="wod-definition-container"[^>]*>.*?<p>(.*?)</p>', html, re.DOTALL)
    raw_definition = def_match.group(1).strip() if def_match else None
    definition = strip_html_tags(raw_definition) if raw_definition else None
    if word:
      return f"{word} - {definition}" if definition else word
  return None

def clean_example_text(text, keyword):
  """
  Cleans up example text from the API and highlights the keyword.
  Removes special formatting like '{it}' and wraps the keyword in parentheses.

  Args:
    text (str): The raw example text.
    keyword (str): The word to highlight.

  Returns:
    str: The cleaned and highlighted example text.
  """
  # Remove tags like {bc}, {it}, etc.
  text = re.sub(r"{[^{}]+}", "", text)
  # Create a regex to find the keyword (case-insensitive) and wrap it.
  pattern = re.compile(r"{[^{}]*}?" + re.escape(keyword) + r"{[^{}]*}?|(?<!\w)" + re.escape(keyword) + r"(?!\w)", re.IGNORECASE)
  return pattern.sub(lambda m: f"({keyword})", text).strip()

def extract_all_examples(entry, keyword):
  """
  Recursively extracts all example sentences from a Merriam-Webster API JSON entry.

  Args:
    entry (dict): A dictionary representing a single word entry from the API.
    keyword (str): The word being looked up, used for highlighting.

  Returns:
    list: A list of cleaned example sentences.
  """
  examples = []

  def extract_from_dt(dt):
    """Inner recursive function to traverse the 'dt' (defining text) structure."""
    for part in dt:
      if part[0] == "vis":  # 'vis' contains verbal illustrations (examples).
        for vis_item in part[1]:
          if isinstance(vis_item, dict):
            text = vis_item.get("t", "")
            if text:
              examples.append(clean_example_text(text, keyword))
      elif isinstance(part[1], list):
        # Recursively process nested structures.
        for subpart in part[1]:
          if isinstance(subpart, list):
            extract_from_dt(subpart)

  try:
    # The main loop to start the extraction process.
    for d in entry.get("def", []):
      for sseq in d.get("sseq", []):
        for item in sseq:
          if len(item) >= 2 and isinstance(item[1], dict):
            extract_from_dt(item[1].get("dt", []))
  except Exception as e:
    print(f"Error extracting examples: {e}")
  return examples

def get_word_definition_from_proxy(word):
  """
  Fetches the definition and examples for a word from the dictionary API proxy.

  Args:
    word (str): The word to look up.

  Returns:
    str: A formatted string containing the word, its definitions, and examples,
         or an error message if the lookup fails.
  """
  try:
    response = requests.get(DICTIONARY_API_URL.format(word))
    if response.status_code == 200:
      try:
        data = response.json()
        if data and isinstance(data, list):
          all_definitions = []
          all_examples = []
          for entry in data:
            if not isinstance(entry, dict): continue
            # Extract short definitions and examples from each entry.
            all_definitions.extend(entry.get("shortdef", []))
            all_examples.extend(extract_all_examples(entry, word))

          if not all_definitions and not all_examples:
            return "No definitions found."

          # Format the final output string.
          result = f"{word}:\n"
          if all_definitions:
            result += "Definitions:\n" + "\n".join(f"{i+1}. {d}" for i, d in enumerate(all_definitions))
          if all_examples:
            result += "\n\nExamples:\n" + "\n".join(f"{i+1}. {ex}" for i, ex in enumerate(all_examples))
          return result.strip()
      except Exception as e:
        print(f"Error parsing definition: {e}")
  except requests.RequestException:
    return "Failed to connect to the dictionary service."
  return None

def get_selected_text_via_helper_with_hwnd(hwnd, timeout_seconds=0.5):
  """
  Gets selected text by running selection_helper.py in a subprocess for a specific hwnd.
  This is a fallback method.

  Args:
    hwnd (int): The window handle.
    timeout_seconds (float): Timeout for the subprocess.

  Returns:
    str or None: The selected text or None on failure/timeout.
  """
  try:
    helper = os.path.join(os.path.dirname(__file__), "selection_helper.py")
    cmd = [sys.executable, helper, str(int(hwnd))]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    out = proc.stdout.strip()
    if out:
      return out
  except subprocess.TimeoutExpired:
    return None
  except Exception:
    return None
  return None

def get_selected_text_via_helper(timeout_seconds=0.5):
  """
  Gets selected text by running selection_helper.py in a subprocess for the foreground window.
  This is a fallback method.

  Args:
    timeout_seconds (float): Timeout for the subprocess.

  Returns:
    str or None: The selected text or None on failure/timeout.
  """
  try:
    helper = os.path.join(os.path.dirname(__file__), "selection_helper.py")
    cmd = [sys.executable, helper]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
    out = proc.stdout.strip()
    if out:
      return out
  except subprocess.TimeoutExpired:
    return None
  except Exception:
    return None
  return None

def get_selected_text():
  """
  Attempts to retrieve the currently selected text using multiple methods.

  The methods are tried in the following order:
  1. NVDA's review cursor and its properties (`value`, `text`, `displayText`).
  2. The window handle (`hwnd`) associated with the review cursor object,
     passed to a threaded call of `selection_helper`.
  3. A threaded call of `selection_helper` for the current foreground window as a final fallback.

  Returns:
    str or None: The selected text, or None if it cannot be retrieved.
  """
  try:
    reviewPos = api.getReviewPosition()
  except Exception:
    reviewPos = None

  # Method 1: Try getting text directly from the review position object.
  if reviewPos:
    try:
      for attr in ("value", "text", "displayText"):
        try:
          v = getattr(reviewPos, attr, None)
        except Exception:
          v = None
        if isinstance(v, str) and v.strip():
          return v.strip()
      try:
        if hasattr(reviewPos, "getText"):
          t = reviewPos.getText(0)
          if isinstance(t, str) and t.strip():
            return t.strip()
      except Exception:
        pass
    except Exception:
      pass

    # Method 2: Collect potential window handles from the review position object.
    hwnd_candidates = []
    # Collect all possible hwnd attributes safely.
    for attr_name in ("windowHandle", "hwnd"):
        try:
            wh = getattr(reviewPos, attr_name, None)
            if wh is not None:
                try:
                    hwnd_candidates.append(int(wh))
                except Exception:
                    try:
                        hwnd_candidates.append(int(getattr(wh, "value", wh)))
                    except Exception:
                        pass
        except Exception:
            pass
    try:
      appmod = getattr(reviewPos, "appModule", None)
      if appmod:
        wh = getattr(appmod, "helperLocalBindingHandle", None)
        if wh is not None:
          try:
            hwnd_candidates.append(int(wh))
          except Exception:
            try:
              hwnd_candidates.append(int(getattr(wh, "value", wh)))
            except Exception:
              pass
    except Exception:
      pass

    # Try to get selection for each candidate hwnd using a thread.
    for h in hwnd_candidates:
      try:
        out = []
        th = threading.Thread(target=_call_selection_helper_for_hwnd, args=(h, out))
        th.daemon = True
        th.start()
        th.join(0.9) # Wait for a short time.
        if out and out[0]:
          return out[0]
      except Exception:
        pass

  # Method 3: Fallback to getting selection from the foreground window.
  try:
    out = []
    th = threading.Thread(target=_call_selection_helper_foreground, args=(out,))
    th.daemon = True
    th.start()
    th.join(0.9)
    if out and out[0]:
      return out[0]
  except Exception:
    pass

  return None

def get_valid_selected_word():
  """
  A wrapper for get_selected_text() that handles the case where no text is selected.

  Returns:
    str or None: The selected text if found, otherwise None after showing a message.
  """
  selected = get_selected_text()
  if not selected:
    ui.message("No text selected.")
    return None
  return selected

def handle_double_press(last_time, current_time, cached_text, label="Text"):
  """
  Checks if a key press is a "double press" (within 1.5 seconds of the last one).
  If it is, it copies the cached text to the clipboard.

  Args:
    last_time (float): The timestamp of the last press.
    current_time (float): The timestamp of the current press.
    cached_text (str): The text to copy on a double press.
    label (str): The label for the message (e.g., "Definition").

  Returns:
    str: "copied" if text was copied, "empty" if there was nothing to copy, "no" otherwise.
  """
  if last_time and (current_time - last_time) < 1.5:
    if cached_text:
      api.copyToClip(cached_text)
      ui.message(f"{label} copied to clipboard.")
      return "copied"
    else:
      ui.message(f"No recent {label.lower()} to copy.")
      return "empty"
  return "no"

def _get_history_retention_seconds():
  """
  Reads history retention settings from the config and converts them to seconds.

  Returns:
    int: The total retention time in seconds. Returns 0 to disable retention.
  """
  try:
    unit = str(config.conf["mwWordLexicon"].get("history_retention_unit", "days")).lower()
    value = int(config.conf["mwWordLexicon"].get("history_retention_value", 0))
    if value <= 0:
      return 0
    if unit in ("minute", "minutes", "min", "m"):
      return value * 60
    if unit in ("hour", "hours", "h"):
      return value * 3600
    # Default to days.
    return value * 24 * 3600
  except Exception:
    return 0

def _prune_history_by_retention(history_list):
  """
  Filters a history list, removing items older than the configured retention period.

  Args:
    history_list (list): The list of history items (dicts with a 'ts' timestamp key).

  Returns:
    list: The pruned history list.
  """
  seconds = _get_history_retention_seconds()
  if not seconds: # A value of 0 means keep forever.
    return history_list
  cutoff = time.time() - seconds
  return [item for item in history_list if item.get("ts", 0) >= cutoff]

class SearchDialog(wx.Frame):
  """
  A custom wx.Frame dialog for manually searching for definitions, synonyms, or antonyms.
  """
  def __init__(self, parent, pre_filled_text=""):
    """
    Initializes the search dialog UI components.

    Args:
      parent: The parent window.
      pre_filled_text (str): Text to pre-populate the search box with.
    """
    global OPEN_DIALOG
    if OPEN_DIALOG:
      ui.message("Please close the open dialog before opening another.")
      raise RuntimeError("Dialog already open")
    super(SearchDialog, self).__init__(parent, title="Search Dictionary", size=(600, 450))
    OPEN_DIALOG = self
    panel = wx.Panel(self)
    
    main_sizer = wx.BoxSizer(wx.VERTICAL)
    search_sizer = wx.BoxSizer(wx.HORIZONTAL)
    
    self.search_box = wx.TextCtrl(panel, value=pre_filled_text)
    search_sizer.Add(self.search_box, 1, wx.EXPAND | wx.ALL, 5)
    
    self.search_type = wx.ComboBox(panel, choices=["definition", "synonyms", "antonyms"], style=wx.CB_READONLY)
    self.search_type.SetValue("definition")
    search_sizer.Add(self.search_type, 0, wx.ALL, 5)
    
    search_button = wx.Button(panel, label="Search")
    search_sizer.Add(search_button, 0, wx.ALL, 5)
    
    main_sizer.Add(search_sizer, 0, wx.EXPAND)
    
    self.results_area = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
    main_sizer.Add(self.results_area, 1, wx.EXPAND | wx.ALL, 5)
    
    close_button = wx.Button(panel, label="Close")
    main_sizer.Add(close_button, 0, wx.ALIGN_CENTER | wx.ALL, 5)
    
    panel.SetSizer(main_sizer)
    
    # Bind events
    search_button.Bind(wx.EVT_BUTTON, self.on_search)
    close_button.Bind(wx.EVT_BUTTON, lambda evt: self._do_close())
    self.search_box.Bind(wx.EVT_KEY_UP, self.on_key_up)
    self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)
    self.Bind(wx.EVT_CLOSE, self._on_close)

    self._auto_focus_results_after_search = bool(pre_filled_text)

    # If text is pre-filled, automatically start the search.
    if pre_filled_text:
      wx.CallAfter(self.search_box.SetFocus)
      wx.CallLater(80, self.on_search, None)

  def _on_char_hook(self, evt):
    """Handles key events for the whole frame, like the Escape key."""
    if evt.GetKeyCode() == wx.WXK_ESCAPE:
      self._do_close()
    else:
      evt.Skip()

  def _do_close(self):
    """Safely closes the dialog and resets the global flag."""
    global OPEN_DIALOG
    try:
      self.Destroy()
    except Exception:
      pass
    OPEN_DIALOG = None

  def _on_close(self, evt):
    """Ensures the global flag is reset when the dialog is closed via the window manager."""
    global OPEN_DIALOG
    OPEN_DIALOG = None
    try:
      evt.Skip()
    except Exception:
      pass

  def on_key_up(self, event):
    """Handles the Enter key in the search box to trigger a search."""
    if event.GetKeyCode() == wx.WXK_RETURN:
      self.on_search(None)
    event.Skip()

  def on_search(self, event):
    """
    Initiates the search process in a background thread to keep the GUI responsive.
    """
    query = self.search_box.GetValue().strip()
    if not query:
      return
    
    search_type = self.search_type.GetValue()
    
    self.results_area.SetValue(f"Searching for {search_type} of '{query}'...")
    
    def worker():
      """The function that runs in the background thread to perform the API call."""
      result = ""
      try:
        if search_type == "definition":
          result = get_word_definition_from_proxy(query)
        elif search_type == "synonyms":
          result = thesaurus.get_word_thesaurus(query)
        elif search_type == "antonyms":
          result = thesaurus.get_word_antonyms(query)
      except Exception as e:
        result = f"An error occurred: {e}"
      
      final_result = result or "Not found."

      def on_complete():
        """This function is called on the main thread after the worker is done."""
        self.results_area.SetValue(final_result)
        if search_type == "definition":
          # For definitions, also copy to clipboard and add to history.
          wx.CallAfter(api.copyToClip, final_result)
          for plugin in globalPluginHandler.runningPlugins:
            if isinstance(plugin, GlobalPlugin):
              wx.CallAfter(plugin._addToHistory, final_result)
              break
        if self._auto_focus_results_after_search:
          try:
            self.results_area.SetFocus()
            self._auto_focus_results_after_search = False
          except Exception:
            pass
      # Schedule the UI update to run on the main GUI thread.
      wx.CallAfter(on_complete)
      
    # Start the background thread.
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
  """
  The main NVDA addon class that handles scripts, state management, and history.
  """
  # Class-level variables to store history and current index.
  history = []
  historyIndex = -1
  restoring = False

  def __init__(self):
    """
    Initializes the plugin, loads settings, and sets up state variables.
    """
    super().__init__()
    # Register the settings panel with NVDA's settings dialog.
    gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(MwWordLexiconSettingsPanel)
    # Initialize state variables for double-press detection.
    self.last_definition_press_time = None
    self.last_wotd_press_time = None
    self.last_definition_text = None
    self.word_of_the_day_text = None
    # Ensure the configuration section exists.
    if "mwWordLexicon" not in config.conf:
      config.conf.createSection("mwWordLexicon")
    # Load settings from config, with defaults.
    try:
      self.history_size = int(config.conf["mwWordLexicon"].get("history_size", 3))
    except:
      self.history_size = 3
    # Load and parse history from JSON string in config.
    hist_json = config.conf["mwWordLexicon"].get("history_json", "[]")
    try:
      parsed = json.loads(hist_json)
      if isinstance(parsed, list):
        # Normalize history items to be dicts with text and timestamp.
        normalized = []
        for item in parsed:
          if isinstance(item, dict) and "text" in item:
            normalized.append({"text": item.get("text") or "", "ts": float(item.get("ts", 0))})
          elif isinstance(item, str): # Handle legacy string-only history.
            normalized.append({"text": item, "ts": 0.0})
        GlobalPlugin.history = normalized
      else:
        GlobalPlugin.history = []
    except Exception:
      GlobalPlugin.history = []
    GlobalPlugin.historyIndex = -1
    GlobalPlugin.restoring = False
    self.copy_mode = int(config.conf["mwWordLexicon"].get("copy_mode", 1))
    self.cycle_history = str(config.conf["mwWordLexicon"].get("cycle_history", False)).lower() == 'true'
    self.last_copy_mode2_press_time = None
    self.last_thesaurus_press_time = None
    self.last_thesaurus_text = None
    self.last_antonyms_press_time = None
    self.last_antonyms_text = None
    # Start a background thread to periodically prune old history items.
    self._retention_stop_event = threading.Event()
    self._retention_thread = threading.Thread(target=self._retention_worker)
    self._retention_thread.daemon = True
    self._retention_thread.start()
    try:
      self._periodic_prune_check() # Run one check on startup.
    except Exception:
      pass

  def _updateAndSaveHistory(self, new_history, prune=True):
    """
    Updates the history list, prunes it, enforces size limits, and saves to config.

    Args:
      new_history (list): The new list of history items.
      prune (bool): Whether to apply the retention period pruning.
    """
    # Normalize all items to the dict format with timestamps.
    normalized = []
    now = time.time()
    for item in new_history:
      if isinstance(item, dict) and "text" in item:
        normalized.append({"text": item.get("text") or "", "ts": float(item.get("ts", now))})
      elif isinstance(item, str):
        normalized.append({"text": item, "ts": now})
    # Prune based on retention settings.
    if prune:
      normalized = _prune_history_by_retention(normalized)
    # Enforce the maximum history size.
    try:
      max_size = int(config.conf["mwWordLexicon"].get("history_size", getattr(self, "history_size", 3)))
    except Exception:
      max_size = getattr(self, "history_size", 3)
    normalized.sort(key=lambda x: x.get("ts", 0)) # Sort by time to remove oldest first.
    while len(normalized) > max_size:
      normalized.pop(0)
    GlobalPlugin.history = normalized
    # Save the updated history back to the config file as a JSON string.
    try:
      config.conf["mwWordLexicon"]["history_json"] = json.dumps(GlobalPlugin.history, ensure_ascii=False)
      # Attempt to trigger a config save.
      try:
        save_func = getattr(config, "save", None)
        if callable(save_func):
          save_func()
        else:
          conf_obj = getattr(config, "conf", None)
          if conf_obj and hasattr(conf_obj, "write"):
            conf_obj.write()
      except Exception:
        pass
    except Exception as e:
      print(f"Failed to save history: {e}")

  def _addToHistory(self, text):
    """
    Adds a new item to the history, ensuring no duplicates.

    Args:
      text (str): The text of the new history item.
    """
    if not text:
      return

    now = time.time()
    current_history = list(GlobalPlugin.history)
    # Remove any existing entry with the same text to avoid duplicates.
    current_history = [h for h in current_history if (h.get("text") if isinstance(h, dict) else h) != text]
    current_history.append({"text": text, "ts": now})

    self._updateAndSaveHistory(current_history)
    GlobalPlugin.historyIndex = -1 # Reset cycle index.

  def _periodic_prune_check(self):
    """Checks if the history needs pruning and does so if necessary."""
    try:
      pruned = _prune_history_by_retention(GlobalPlugin.history)
      if pruned != GlobalPlugin.history:
        self._updateAndSaveHistory(pruned)
    except Exception:
      pass

  def _retention_worker(self):
    """Background thread worker that periodically calls the prune check."""
    try:
      # Wait for 30 seconds, or until the stop event is set.
      while not self._retention_stop_event.wait(30):
        self._periodic_prune_check()
    except Exception:
      pass

  def _stop_retention_thread(self):
    """Signals the retention worker thread to stop."""
    try:
      self._retention_stop_event.set()
      try:
        self._retention_thread.join(1.0)
      except Exception:
        pass
    except Exception:
      pass

  def get_word_definition(self, word):
    """Wrapper function for getting a word definition."""
    return get_word_definition_from_proxy(word)

  def handle_output(self, text):
    """
    Handles the result of a lookup based on the current `copy_mode`.

    - Mode 0: Copies to clipboard, adds to history, and speaks the result.
    - Mode 1: Just speaks the result.
    - Mode 2: Copies, adds to history, and shows a custom dialog with audio playback.

    Args:
      text (str): The text result to handle.
    """
    if self.copy_mode == 0:
      api.copyToClip(text)
      self._addToHistory(text)
      ui.message(text)
    elif self.copy_mode == 1:
      ui.message(text)
    elif self.copy_mode == 2:
      def fetch_audio_and_show_dialog(text, word):
        """Fetches audio URL in a thread and then creates the dialog."""
        try:
          response = requests.get(DICTIONARY_API_URL.format(word))
          if response.status_code != 200:
            wx.CallAfter(ui.message, "Failed to retrieve audio data.")
            return

          data = response.json()
          audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
          if not audio_id:
            wx.CallAfter(ui.message, "No pronunciation audio available.")
            audio_url = None
          else:
            subfolder = audio_id[0]
            audio_url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subfolder}/{audio_id}.mp3"
          # Create the dialog on the main thread.
          wx.CallAfter(create_and_show_dialog, text, audio_url, word)

        except Exception as e:
          wx.CallAfter(ui.message, f"Error: {str(e)}")

      def create_and_show_dialog(text, audio_url, original_word):
        """Creates and shows the custom result dialog."""
        global OPEN_DIALOG
        if OPEN_DIALOG:
          ui.message("Please close the open dialog before opening another.")
          return
        frame = wx.Frame(None, title="Definition", size=(600, 400))
        OPEN_DIALOG = frame
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.VERTICAL)

        text_ctrl = wx.TextCtrl(panel, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
        sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)

        speed_slider = None
        volume_slider = None
        if audio_url:
          play_button = wx.Button(panel, label="Play")
          sizer.Add(play_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

          # Add speed and volume controls.
          speed_label = wx.StaticText(panel, label="Speed:")
          sizer.Add(speed_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          speed_slider = wx.Slider(panel, value=100, minValue=50, maxValue=200, style=wx.SL_HORIZONTAL)
          sizer.Add(speed_slider, 0, wx.EXPAND | wx.ALL, 10)
          volume_label = wx.StaticText(panel, label="Volume:")
          sizer.Add(volume_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          volume_slider = wx.Slider(panel, value=100, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
          sizer.Add(volume_slider, 0, wx.EXPAND | wx.ALL, 10)

          def do_play_for_url(url):
            """Helper to play audio with current slider values."""
            sp = speed_slider.GetValue() if speed_slider else 100
            vol = volume_slider.GetValue() if volume_slider else 100
            play_with_ffplay(url, sp, vol)
          
          play_button.Bind(wx.EVT_BUTTON, lambda evt: threading.Thread(target=do_play_for_url, args=(audio_url,), daemon=True).start())

        # Add standard dialog buttons.
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        ok_button = wx.Button(panel, label="OK")
        btn_row.Add(ok_button, 0, wx.ALL, 5)
        cancel_button = wx.Button(panel, label="Cancel")
        btn_row.Add(cancel_button, 0, wx.ALL, 5)
        sizer.Add(btn_row, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

        ok_button.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
        cancel_button.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
        
        def _play_word_lookup(word_to_lookup):
          """Looks up and plays the pronunciation for a given word."""
          # This function is used for playing pronunciation of selected text inside the dialog.
          try:
            resp = requests.get(DICTIONARY_API_URL.format(word_to_lookup))
            if resp.status_code != 200: return
            data = resp.json()
            audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
            if not audio_id: return
            subfolder = audio_id[0]
            url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subfolder}/{audio_id}.mp3"
            do_play_for_url(url)
          except Exception:
            wx.CallAfter(ui.message, "Failed to fetch pronunciation.")

        def on_char_hook(evt):
          """Custom key bindings for the dialog."""
          kc = evt.GetKeyCode()
          if kc == wx.WXK_ESCAPE:
            frame.Close()
            return
          # Ctrl+P: Play pronunciation of selected text or the original word.
          if evt.ControlDown() and (kc == ord('P') or kc == ord('p')):
            sel = text_ctrl.GetStringSelection().strip()
            if sel:
              words = [w for w in re.split(r'\s+', sel) if w]
              if len(words) > 1: ui.message("Cannot play pronunciation: select a single word.")
              else: threading.Thread(target=_play_word_lookup, args=(words[0],), daemon=True).start()
            else:
              if audio_url: threading.Thread(target=do_play_for_url, args=(audio_url,), daemon=True).start()
              else: threading.Thread(target=_play_word_lookup, args=(original_word,), daemon=True).start()
            return
          # Shift+Up/Down: Adjust playback speed.
          if evt.ShiftDown() and kc in (wx.WXK_UP, wx.WXK_DOWN):
            if speed_slider:
              cur = speed_slider.GetValue(); step = 5; newv = cur + (step if kc == wx.WXK_UP else -step)
              newv = max(speed_slider.GetMin(), min(speed_slider.GetMax(), newv)); speed_slider.SetValue(newv)
              ui.message(f"Speed {newv}%")
            return
          # Ctrl+Up/Down: Adjust playback volume.
          if evt.ControlDown() and kc in (wx.WXK_UP, wx.WXK_DOWN):
            if volume_slider:
              cur = volume_slider.GetValue(); step = 5; newv = cur + (step if kc == wx.WXK_UP else -step)
              newv = max(volume_slider.GetMin(), min(volume_slider.GetMax(), newv)); volume_slider.SetValue(newv)
              ui.message(f"Volume {newv}%")
            return
          evt.Skip()

        frame.Bind(wx.EVT_CHAR_HOOK, on_char_hook)
        frame.Bind(wx.EVT_CLOSE, lambda evt: _clear_open_dialog(evt, frame))
        panel.SetSizer(sizer)
        frame.Show()
        frame.Raise()

      # Start the process by fetching the audio in a background thread.
      audio_thread = threading.Thread(target=fetch_audio_and_show_dialog, args=(text, self.last_selected_word))
      audio_thread.daemon = True
      audio_thread.start()

      # Immediately copy and add to history.
      api.copyToClip(text)
      self._addToHistory(text)
      self.last_definition_text = text

  def terminate(self):
    """
    Called when the plugin is being unloaded. Performs cleanup.
    """
    try:
      self._stop_retention_thread()
    except Exception:
      pass
    try:
      # Unregister the settings panel.
      NVDASettingsDialog.categoryClasses.remove(MwWordLexiconSettingsPanel)
    except (ValueError, AttributeError):
      pass

  def threaded_request(self, target_func, *args):
    """
    A generic helper to run a function in a background thread and handle its output.

    Args:
      target_func: The function to run in the thread.
      *args: Arguments to pass to the target function.
    """
    def worker():
      result = target_func(*args)
      def on_complete():
        if result:
          self.handle_output(result)
        else:
          ui.message("Not found.")
      wx.CallAfter(on_complete)

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()

  @script(description="Cycle copy/display modes", gesture="kb:control+shift+a")
  def script_cycle_copy_mode(self, gesture):
    """
    Cycles through the three copy modes and saves the new setting.
    """
    self.copy_mode = (self.copy_mode + 1) % 3
    try:
      config.conf["mwWordLexicon"]["copy_mode"] = self.copy_mode
      # Save config
      try:
        save_func = getattr(config, "save", None)
        if callable(save_func):
          save_func()
        else:
          conf_obj = getattr(config, "conf", None)
          if conf_obj and hasattr(conf_obj, "write"):
            conf_obj.write()
      except Exception:
        pass
    except Exception:
      pass
    ui.message(["Auto copy", "Double press to copy", "Copy and show dialog"][self.copy_mode])

  @script(
      description="Open Search Dialog", 
      gesture="kb:nvda+alt+a"
      )
  def script_showSearchDialog(self, gesture):
    """
    Opens the manual search dialog, pre-filling it with the currently selected text.
    """
    global OPEN_DIALOG
    if OPEN_DIALOG:
      ui.message("Please close the open dialog before opening another.")
      return
    selected_text = get_selected_text() or ""
    try:
      dialog = SearchDialog(None, pre_filled_text=selected_text)
      dialog.Show()
      dialog.Raise()
      # If there was selected text, trigger an automatic search.
      if selected_text:
        wx.CallAfter(dialog.on_search, None)
    except Exception as e:
      ui.message(f"Error opening search dialog: {e}")

  @script(
      description="Get word definition or copy last one if pressed quickly twice.",
      gesture="kb:control+shift+d"
      )
  def script_get_definition_with_smart_copy(self, gesture):
    """
    Gets the definition for the selected word. If pressed twice quickly,
    it copies the previous definition to the clipboard instead.
    """
    now = time.time()
    # Handle the double-press-to-copy logic if in mode 1 or 2.
    if self.copy_mode in (1, 2):
      label = "Definition"
      status = handle_double_press(
        self.last_copy_mode2_press_time if self.copy_mode == 2 else self.last_definition_press_time,
        now,
        self.last_definition_text,
        label
      )
      if status in ("copied", "empty"):
        if status == "copied":
          self._addToHistory(self.last_definition_text)
          self.last_definition_text = None
        return

    # Update the timestamp for the next double-press check.
    if self.copy_mode == 2:
      self.last_copy_mode2_press_time = now
    else:
      self.last_definition_press_time = now

    word = get_valid_selected_word()
    if not word:
      return
    self.last_selected_word = word
    self.threaded_request(self.get_word_definition, word)

  @script(
      description="Get Word of the Day with examples or copy them on quick second press.",
      gesture="kb:control+shift+w"
      )
  def script_word_of_the_day(self, gesture):
    """
    Gets the Word of the Day. If pressed twice quickly (in mode 1),
    it copies the previous WOTD to the clipboard.
    """
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_wotd_press_time, now, self.word_of_the_day_text, "Word of the Day")
      if status in ("copied", "empty"):
        if status == "copied":
          self._addToHistory(self.word_of_the_day_text)
          self.word_of_the_day_text = None
        return
    self.last_wotd_press_time = now

    def get_full_wotd():
      """Fetches WOTD and also tries to fetch its examples."""
      raw = get_word_of_the_day()
      if not raw:
        return "Failed to retrieve Word of the Day."

      word = raw.split(" - ")[0].strip()
      message = f"Word of the Day: {raw}"

      # Also fetch examples for the word.
      try:
        response = requests.get(DICTIONARY_API_URL.format(word))
        if response.status_code == 200:
          data = response.json()
          examples = []
          for entry in data:
            examples += extract_all_examples(entry, word)
          if examples:
            message += "\n\nExamples:\n" + "\n".join(f"{i+1}. {ex}" for i, ex in enumerate(examples))
      except Exception as e:
        print(f"Error extracting examples: {e}")

      self.word_of_the_day_text = message.strip()
      self.last_selected_word = word
      return self.word_of_the_day_text

    self.threaded_request(get_full_wotd)

  @script(
    description="Show or cycle through history",
    gesture="kb:control+shift+h"
    )
  def script_show_history_list(self, gesture):
    """
    Shows the lookup history. Behavior depends on the 'cycle_history' setting.
    - If True: Cycles through history items, copying each one.
    - If False: Shows a dialog with the history list and management options.
    """
    if not GlobalPlugin.history:
      ui.message("No history available.")
      return

    if self.cycle_history:
      # Cycle mode: move to the next item and copy it.
      GlobalPlugin.historyIndex = (GlobalPlugin.historyIndex + 1) % len(GlobalPlugin.history)
      reversed_history = list(reversed([h.get("text") for h in GlobalPlugin.history]))
      item_to_copy = reversed_history[GlobalPlugin.historyIndex]
      try:
        api.copyToClip(item_to_copy)
        ui.message(item_to_copy)
      except Exception as e:
        ui.message(f"Failed to copy history item: {e}")
    else:
      # Dialog mode: show a list with options.
      try:
        global OPEN_DIALOG
        if OPEN_DIALOG:
          ui.message("Please close the open dialog before opening another.")
          return
        frame = wx.Frame(None, title="mwWordLexicon — History", size=(700, 400))
        OPEN_DIALOG = frame
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.VERTICAL)
        lbl = wx.StaticText(panel, label="Right-click for options or use keyboard shortcuts:")
        sizer.Add(lbl, 0, wx.EXPAND | wx.ALL, 8)
        
        items = [entry.get("text") if isinstance(entry, dict) else str(entry) for entry in reversed(GlobalPlugin.history)]
        lb = wx.ListBox(panel, choices=items, style=wx.LB_SINGLE)
        sizer.Add(lb, 1, wx.EXPAND | wx.ALL, 8)
        
        close_btn = wx.Button(panel, label="Close")
        sizer.Add(close_btn, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        # Define actions for the dialog.
        def do_copy_selected(event=None):
          sel = lb.GetSelection(); text = lb.GetString(sel)
          api.copyToClip(text); ui.message("History item copied.")
        def do_copy_all(event=None):
          all_items = "\n\n".join(lb.GetItems())
          api.copyToClip(all_items); ui.message("All history items copied.")
        def do_remove_selected(event=None):
          sel = lb.GetSelection(); original_index = len(GlobalPlugin.history) - 1 - sel
          GlobalPlugin.history.pop(original_index); self._updateAndSaveHistory(GlobalPlugin.history)
          lb.Delete(sel); ui.message("Item removed.")
          if lb.GetCount() > 0: lb.SetSelection(min(sel, lb.GetCount() - 1))
        def do_clear_history(event=None):
          dialog = wx.MessageDialog(frame, "Are you sure?", "Confirm Clear", wx.YES_NO | wx.ICON_WARNING)
          if dialog.ShowModal() == wx.ID_YES:
            self._updateAndSaveHistory([]); lb.Clear(); ui.message("History cleared."); frame.Close()
          dialog.Destroy()
        
        # Create context menu and keyboard accelerators.
        ID_COPY, ID_COPY_ALL, ID_REMOVE, ID_CLEAR = wx.NewIdRef(), wx.NewIdRef(), wx.NewIdRef(), wx.NewIdRef()
        def on_context_menu(event):
          menu = wx.Menu(); menu.Append(ID_COPY, "Copy\tCtrl+C"); menu.Append(ID_COPY_ALL, "Copy All\tCtrl+Shift+C")
          menu.AppendSeparator(); menu.Append(ID_REMOVE, "Remove\tDelete"); menu.Append(ID_CLEAR, "Clear\tShift+Delete")
          frame.PopupMenu(menu); menu.Destroy()

        lb.Bind(wx.EVT_CONTEXT_MENU, on_context_menu)
        frame.Bind(wx.EVT_MENU, do_copy_selected, id=ID_COPY); frame.Bind(wx.EVT_MENU, do_copy_all, id=ID_COPY_ALL)
        frame.Bind(wx.EVT_MENU, do_remove_selected, id=ID_REMOVE); frame.Bind(wx.EVT_MENU, do_clear_history, id=ID_CLEAR)
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
        accel_tbl = wx.AcceleratorTable([(wx.ACCEL_CTRL, ord('C'), ID_COPY), (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('C'), ID_COPY_ALL), (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_REMOVE), (wx.ACCEL_SHIFT, wx.WXK_DELETE, ID_CLEAR)])
        frame.SetAcceleratorTable(accel_tbl)
        frame.Bind(wx.EVT_CHAR_HOOK, lambda evt: frame.Close() if evt.GetKeyCode() == wx.WXK_ESCAPE else evt.Skip())
        frame.Bind(wx.EVT_CLOSE, lambda evt: _clear_open_dialog(evt, frame))
        
        panel.SetSizer(sizer); frame.Show(); frame.Raise(); wx.CallAfter(lb.SetFocus)
      except Exception as e:
        ui.message(f"History UI error: {e}")

  @script(
      description="Get thesaurus (synonyms) for the selected word.",
      gesture="kb:control+shift+t"
      )
  def script_get_thesaurus(self, gesture):
    """
    Gets synonyms for the selected word. If pressed twice quickly (in mode 1),
    it copies the previous thesaurus result.
    """
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_thesaurus_press_time, now, self.last_thesaurus_text, "Thesaurus")
      if status in ("copied", "empty"):
        if status == "copied":
          self._addToHistory(self.last_thesaurus_text)
          self.last_thesaurus_text = None
        return
    self.last_thesaurus_press_time = now

    word = get_valid_selected_word()
    if not word:
      return
    self.last_selected_word = word
    self.threaded_request(thesaurus.get_word_thesaurus, word)

  @script(
      description="Get antonyms for the selected word.",
      gesture="kb:control+shift+u"
      )
  def script_get_antonyms(self, gesture):
    """
    Gets antonyms for the selected word. If pressed twice quickly (in mode 1),
    it copies the previous antonyms result.
    """
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_antonyms_press_time, now, self.last_antonyms_text, "Antonyms")
      if status in ("copied", "empty"):
        if status == "copied":
          self._addToHistory(self.last_antonyms_text)
          self.last_antonyms_text = None
        return
    self.last_antonyms_press_time = now

    word = get_valid_selected_word()
    if not word:
      return
    self.last_selected_word = word
    self.threaded_request(thesaurus.get_word_antonyms, word)

# The name of the configuration section.
SECTION = "mwWordLexicon"

class MwWordLexiconSettingsPanel(SettingsPanel):
  """
  The GUI panel for this addon's settings, which appears in NVDA's settings dialog.
  """
  # The title of the settings category.
  title = "MW Word Lexicon"

  def makeSettings(self, sizer):
    """
    Creates the UI controls for the settings panel.
    """
    if SECTION not in config.conf:
      config.conf.createSection(SECTION)

    # Load current settings to display in the controls.
    current_size = int(config.conf[SECTION].get("history_size", "3"))
    cycle_history = str(config.conf[SECTION].get("cycle_history", False)).lower() == 'true'
    current_retention_value = int(config.conf[SECTION].get("history_retention_value", "0"))
    current_retention_unit = str(config.conf[SECTION].get("history_retention_unit", "days"))

    settings_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="Settings")

    # History size setting
    history_label = wx.StaticText(self, label="History size (number of items to keep):")
    settings_sizer.Add(history_label, 0, wx.ALL, 5)
    self.history_spin = wx.SpinCtrl(self, value=str(current_size), min=1, max=100)
    settings_sizer.Add(self.history_spin, 0, wx.EXPAND | wx.ALL, 5)

    # Cycle history setting
    self.cycle_history_cb = wx.CheckBox(self, label="Cycle through history directly (copies each item)")
    self.cycle_history_cb.SetValue(cycle_history)
    settings_sizer.Add(self.cycle_history_cb, 0, wx.ALL, 5)

    # History retention setting
    retention_label = wx.StaticText(self, label="History retention (value + unit, 0 = keep forever):")
    settings_sizer.Add(retention_label, 0, wx.ALL, 5)
    retention_row = wx.BoxSizer(wx.HORIZONTAL)
    self.retention_spin = wx.SpinCtrl(self, value=str(current_retention_value), min=0, max=365000)
    retention_row.Add(self.retention_spin, 0, wx.RIGHT | wx.ALL, 5)
    choices = ["minutes", "hours", "days"]
    self.retention_unit = wx.ComboBox(self, choices=choices, style=wx.CB_READONLY)
    # Set the combobox to the currently saved unit.
    cu = str(current_retention_unit).lower()
    if cu.startswith("min"): self.retention_unit.SetValue("minutes")
    elif cu.startswith("hour"): self.retention_unit.SetValue("hours")
    else: self.retention_unit.SetValue("days")
    retention_row.Add(self.retention_unit, 0, wx.ALL, 5)
    settings_sizer.Add(retention_row, 0, wx.EXPAND | wx.ALL, 5)

    sizer.Add(settings_sizer, 0, wx.EXPAND | wx.ALL, 5)

  def onSave(self):
    """
    Called when the user clicks OK or Apply. Saves the settings to the config file.
    """
    # Get values from controls and save them to the config section.
    new_size = self.history_spin.GetValue()
    config.conf[SECTION]["history_size"] = new_size
    config.conf[SECTION]["cycle_history"] = self.cycle_history_cb.GetValue()
    config.conf[SECTION]["history_retention_value"] = int(self.retention_spin.GetValue())
    config.conf[SECTION]["history_retention_unit"] = str(self.retention_unit.GetValue() or "days")

    # Trigger config save.
    try:
      save_func = getattr(config, "save", None)
      if callable(save_func): save_func()
      else:
        conf_obj = getattr(config, "conf", None)
        if conf_obj and hasattr(conf_obj, "write"): conf_obj.write()
    except Exception:
      pass

    now = time.time()
    # Update the running plugin instance with the new settings immediately.
    for plugin in globalPluginHandler.runningPlugins:
      if hasattr(plugin, "script_get_definition_with_smart_copy"):
        plugin.history_size = new_size
        plugin.cycle_history = self.cycle_history_cb.GetValue()
        # Trim history if the new size is smaller.
        while len(plugin.history) > new_size:
          plugin.history.pop(0)
        # Resave history to apply new size limit.
        try:
          normalized = []
          for item in plugin.history:
            if isinstance(item, dict) and "text" in item:
              ts = float(item.get("ts", 0)) or now
              normalized.append({"text": item.get("text") or "", "ts": ts})
            elif isinstance(item, str):
              normalized.append({"text": item, "ts": now})
          plugin._updateAndSaveHistory(normalized, prune=False)
        except Exception:
          pass
        break