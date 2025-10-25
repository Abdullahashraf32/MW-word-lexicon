# -*- coding: UTF-8 -*-
# This file is part of the MW-word-lexicon project.
# Copyright (C) 2025 Abdullah Ashraf
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
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

# Global variable to track any currently open dialog created by this addon.
OPEN_DIALOG = None

def _clear_open_dialog(evt, frame):
  """
  Reset the OPEN_DIALOG global flag when a dialog is closed.
  Allows new dialogs to be opened later.
  """
  global OPEN_DIALOG
  try:
    OPEN_DIALOG = None
  except Exception:
    pass
  try:
    evt.Skip()
  except Exception:
    pass

def _call_selection_helper_for_hwnd(hwnd, out_container):
  """
  Thread-safe call to selection_helper.get_selection_for_hwnd(hwnd).
  The result (or None) is appended to out_container.
  """
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_hwnd(hwnd)
      out_container.append(res)
  except Exception:
    out_container.append(None)

def _call_selection_helper_foreground(out_container):
  """
  Thread-safe call to selection_helper.get_selection_for_foreground().
  The result (or None) is appended to out_container.
  """
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_foreground()
      out_container.append(res)
  except Exception:
    out_container.append(None)

DICTIONARY_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}"

def strip_html_tags(text):
  """
  Remove HTML tags using a regex.
  """
  return re.sub(r'<[^>]+>', '', text)

def play_with_ffplay(audio_url, speed=100, volume=100):
  """
  Play an audio stream from a URL using bundled ffplay.exe.
  """
  try:
    ffplay_path = os.path.join(os.path.dirname(__file__), "bin", "ffplay.exe")
    rate = max(50, min(speed, 200)) / 100
    vol = max(0, min(volume, 100))
    subprocess.Popen([
      ffplay_path,
      "-nodisp",
      "-autoexit",
      "-af", f"atempo={rate:.2f},volume={vol / 100:.2f}",
      audio_url
    ])
  except Exception as e:
    ui.message(f"Audio playback failed: {e}")

def get_word_of_the_day():
  """
  Fetch Word of the Day (simple parsing). Returns None on failure.
  """
  url = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/wotd"
  try:
    response = requests.get(url)
  except Exception:
    return None
  if response.status_code == 200:
    html = response.text
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
  Clean example text and highlight the keyword by wrapping it in parentheses.
  """
  text = re.sub(r"{[^{}]+}", "", text)
  pattern = re.compile(r"{[^{}]*}?" + re.escape(keyword) + r"{[^{}]*}?|(?<!\w)" + re.escape(keyword) + r"(?!\w)", re.IGNORECASE)
  return pattern.sub(lambda m: f"({keyword})", text).strip()

def extract_all_examples(entry, keyword):
  """
  Extract example sentences from Merriam-Webster API JSON structure.
  """
  examples = []
  def extract_from_dt(dt):
    for part in dt:
      if part[0] == "vis":
        for vis_item in part[1]:
          if isinstance(vis_item, dict):
            text = vis_item.get("t", "")
            if text:
              examples.append(clean_example_text(text, keyword))
      elif isinstance(part[1], list):
        for subpart in part[1]:
          if isinstance(subpart, list):
            extract_from_dt(subpart)
  try:
    for d in entry.get("def", []):
      for sseq in d.get("sseq", []):
        for item in sseq:
          if len(item) >= 2 and isinstance(item[1], dict):
            extract_from_dt(item[1].get("dt", []))
  except Exception:
    pass
  return examples

def get_word_definition_from_proxy(word):
  """
  Query dictionary proxy and return formatted definitions+examples or an error string.
  """
  try:
    response = requests.get(DICTIONARY_API_URL.format(word))
  except Exception:
    return "Failed to connect to the dictionary service."
  if response.status_code == 200:
    try:
      data = response.json()
      if data and isinstance(data, list):
        all_definitions = []
        all_examples = []
        for entry in data:
          if not isinstance(entry, dict):
            continue
          all_definitions.extend(entry.get("shortdef", []))
          all_examples.extend(extract_all_examples(entry, word))
        if not all_definitions and not all_examples:
          return "No definitions found."
        result = f"{word}:\n"
        if all_definitions:
          result += "Definitions:\n" + "\n".join(f"{i+1}. {d}" for i, d in enumerate(all_definitions))
        if all_examples:
          result += "\n\nExamples:\n" + "\n".join(f"{i+1}. {ex}" for i, ex in enumerate(all_examples))
        return result.strip()
    except Exception:
      return "Error parsing definition."
  return None

def get_selected_text():
  """
  Try several methods to get the currently selected text:
  1) From NVDA's review cursor properties.
  2) From candidate hwnds via selection_helper (threaded).
  3) From foreground window via selection_helper.
  """
  try:
    reviewPos = api.getReviewPosition()
  except Exception:
    reviewPos = None

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

    hwnd_candidates = []
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

    for h in hwnd_candidates:
      try:
        out = []
        th = threading.Thread(target=_call_selection_helper_for_hwnd, args=(h, out))
        th.daemon = True
        th.start()
        th.join(0.9)
        if out and out[0]:
          return out[0]
      except Exception:
        pass

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
  Wrapper around get_selected_text() that notifies the user if nothing is selected.
  """
  selected = get_selected_text()
  if not selected:
    ui.message("No text selected.")
    return None
  return selected

def handle_double_press(last_time, current_time, cached_text, label="Text"):
  """
  If key press is within 1.5 seconds of last_time, copy cached_text to clipboard.
  Returns "copied", "empty", or "no".
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
  Read retention settings and return seconds. 0 means keep forever.
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
    return value * 24 * 3600
  except Exception:
    return 0

def _prune_history_by_retention(history_list):
  """
  Remove items older than retention cutoff; 0 means keep forever.
  """
  seconds = _get_history_retention_seconds()
  if not seconds:
    return history_list
  cutoff = time.time() - seconds
  return [item for item in history_list if item.get("ts", 0) >= cutoff]

class SearchDialog(wx.Frame):
  """
  Lightweight search frame for manual lookup (definitions, synonyms, antonyms).
  Uses background threads for network operations and updates UI via wx.CallAfter.
  """
  def __init__(self, parent, plugin, pre_filled_text=""):
    global OPEN_DIALOG
    if OPEN_DIALOG:
      ui.message("Please close the open dialog before opening another.")
      raise RuntimeError("Dialog already open")
    super(SearchDialog, self).__init__(parent, title="Search Dictionary", size=(600, 450))
    OPEN_DIALOG = self
    self.plugin = plugin
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

    if pre_filled_text:
      wx.CallAfter(self.search_box.SetFocus)
      wx.CallLater(80, self.on_search, None)

  def _on_char_hook(self, evt):
    if evt.GetKeyCode() == wx.WXK_ESCAPE:
      self._do_close()
    else:
      evt.Skip()

  def _do_close(self):
    global OPEN_DIALOG
    try:
      self.Destroy()
    except Exception:
      pass
    OPEN_DIALOG = None

  def _on_close(self, evt):
    global OPEN_DIALOG
    OPEN_DIALOG = None
    try:
      evt.Skip()
    except Exception:
      pass

  def on_key_up(self, event):
    if event.GetKeyCode() == wx.WXK_RETURN:
      self.on_search(None)
    event.Skip()

  def on_search(self, event):
    query = self.search_box.GetValue().strip()
    if not query:
      return

    search_type = self.search_type.GetValue()
    self.results_area.SetValue(f"Searching for {search_type} of '{query}'...")

    def worker():
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
        self.results_area.SetValue(final_result)
        if search_type == "definition":
          wx.CallAfter(api.copyToClip, final_result)
          wx.CallAfter(self.plugin._addToHistory, final_result)
        if self._auto_focus_results_after_search:
          try:
            self.results_area.SetFocus()
            self._auto_focus_results_after_search = False
          except Exception:
            pass
      wx.CallAfter(on_complete)

    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
  """
  Main addon class. This class is defensive: background work is threaded,
  and settings panel registration/unregistration is defensive.
  """
  history = []
  historyIndex = -1
  restoring = False

  def __init__(self):
    super().__init__()
    # Double-press tracking and internal state.
    self.last_definition_press_time = None
    self.last_wotd_press_time = None
    self.last_definition_text = None
    self.word_of_the_day_text = None
    ensure_config_section(SECTION)
    try:
      self.history_size = int(config.conf["mwWordLexicon"].get("history_size", 3))
    except Exception:
      self.history_size = 3

    # Load history stored as JSON string.
    hist_json = config.conf["mwWordLexicon"].get("history_json", "[]")
    try:
      parsed = json.loads(hist_json)
      if isinstance(parsed, list):
        normalized = []
        for item in parsed:
          if isinstance(item, dict) and "text" in item:
            normalized.append({"text": item.get("text") or "", "ts": float(item.get("ts", 0))})
          elif isinstance(item, str):
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

    # Start background retention thread.
    self._retention_stop_event = threading.Event()
    self._retention_thread = threading.Thread(target=self._retention_worker)
    self._retention_thread.daemon = True
    self._retention_thread.start()
    try:
      self._periodic_prune_check()
    except Exception:
      pass

    # Defensive registration of the settings panel. Append only if not present.
    try:
      cls_list = getattr(gui.settingsDialogs.NVDASettingsDialog, "categoryClasses", None)
      if cls_list is None:
        # Defensive: create the list if it does not exist.
        gui.settingsDialogs.NVDASettingsDialog.categoryClasses = [MwWordLexiconSettingsPanel]
      else:
        if MwWordLexiconSettingsPanel not in cls_list:
          cls_list.append(MwWordLexiconSettingsPanel)
    except Exception:
      # Never let registration errors crash NVDA startup.
      pass

  def _updateAndSaveHistory(self, new_history, prune=True):
    """
    Normalize, prune, cap and save history into config as JSON string.
    """
    normalized = []
    now = time.time()
    for item in new_history:
      if isinstance(item, dict) and "text" in item:
        normalized.append({"text": item.get("text") or "", "ts": float(item.get("ts", now))})
      elif isinstance(item, str):
        normalized.append({"text": item, "ts": now})
    if prune:
      normalized = _prune_history_by_retention(normalized)
    try:
      max_size = int(config.conf["mwWordLexicon"].get("history_size", getattr(self, "history_size", 3)))
    except Exception:
      max_size = getattr(self, "history_size", 3)
    normalized.sort(key=lambda x: x.get("ts", 0))
    while len(normalized) > max_size:
      normalized.pop(0)
    GlobalPlugin.history = normalized
    try:
      config.conf["mwWordLexicon"]["history_json"] = json.dumps(GlobalPlugin.history, ensure_ascii=False)
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

  def _addToHistory(self, text):
    """
    Add a text item to history; normalize and persist.
    """
    if not text:
      return
    now = time.time()
    current_history = list(GlobalPlugin.history)
    current_history = [h for h in current_history if (h.get("text") if isinstance(h, dict) else h) != text]
    current_history.append({"text": text, "ts": now})
    self._updateAndSaveHistory(current_history)
    GlobalPlugin.historyIndex = -1

  def _periodic_prune_check(self):
    try:
      pruned = _prune_history_by_retention(GlobalPlugin.history)
      if pruned != GlobalPlugin.history:
        self._updateAndSaveHistory(pruned)
    except Exception:
      pass

  def _retention_worker(self):
    try:
      while not self._retention_stop_event.wait(30):
        self._periodic_prune_check()
    except Exception:
      pass

  def _stop_retention_thread(self):
    try:
      self._retention_stop_event.set()
      try:
        self._retention_thread.join(1.0)
      except Exception:
        pass
    except Exception:
      pass

  def get_word_definition(self, word):
    return get_word_definition_from_proxy(word)

  def _fetch_audio_and_show_dialog(self, text, word):
    """Helper for handle_output (mode 2) to fetch audio URL."""
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
      wx.CallAfter(self._create_and_show_dialog, text, audio_url, word)
    except Exception as e:
      wx.CallAfter(ui.message, f"Error: {str(e)}")

  def _create_and_show_dialog(self, text, audio_url, original_word):
    """Helper for handle_output (mode 2) to create the dialog."""
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

      speed_label = wx.StaticText(panel, label="Speed:")
      sizer.Add(speed_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
      speed_slider = wx.Slider(panel, value=100, minValue=50, maxValue=200, style=wx.SL_HORIZONTAL)
      sizer.Add(speed_slider, 0, wx.EXPAND | wx.ALL, 10)

      volume_label = wx.StaticText(panel, label="Volume:")
      sizer.Add(volume_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
      volume_slider = wx.Slider(panel, value=100, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
      sizer.Add(volume_slider, 0, wx.EXPAND | wx.ALL, 10)

      def do_play_for_url(url):
        sp = speed_slider.GetValue() if speed_slider else 100
        vol = volume_slider.GetValue() if volume_slider else 100
        play_with_ffplay(url, sp, vol)

      play_button.Bind(wx.EVT_BUTTON, lambda evt: threading.Thread(target=do_play_for_url, args=(audio_url,), daemon=True).start())

    btn_row = wx.BoxSizer(wx.HORIZONTAL)
    ok_button = wx.Button(panel, label="OK")
    btn_row.Add(ok_button, 0, wx.ALL, 5)
    cancel_button = wx.Button(panel, label="Cancel")
    btn_row.Add(cancel_button, 0, wx.ALL, 5)
    sizer.Add(btn_row, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

    ok_button.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
    cancel_button.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())

    def _play_word_lookup(word_to_lookup):
      try:
        resp = requests.get(DICTIONARY_API_URL.format(word_to_lookup))
        if resp.status_code != 200:
          return
        data = resp.json()
        audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
        if not audio_id:
          return
        subfolder = audio_id[0]
        url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subfolder}/{audio_id}.mp3"
        do_play_for_url(url)
      except Exception:
        wx.CallAfter(ui.message, "Failed to fetch pronunciation.")

    def on_char_hook(evt):
      kc = evt.GetKeyCode()
      if kc == wx.WXK_ESCAPE:
        frame.Close()
        return
      if evt.ControlDown() and (kc == ord('P') or kc == ord('p')):
        sel = text_ctrl.GetStringSelection().strip()
        if sel:
          words = [w for w in re.split(r'\s+', sel) if w]
          if len(words) > 1:
            ui.message("Cannot play pronunciation: select a single word.")
          else:
            threading.Thread(target=_play_word_lookup, args=(words[0],), daemon=True).start()
        else:
          if audio_url:
            threading.Thread(target=do_play_for_url, args=(audio_url,), daemon=True).start()
          else:
            threading.Thread(target=_play_word_lookup, args=(original_word,), daemon=True).start()
        return
      if evt.ShiftDown() and kc in (wx.WXK_UP, wx.WXK_DOWN):
        if speed_slider:
          cur = speed_slider.GetValue(); step = 5; newv = cur + (step if kc == wx.WXK_UP else -step)
          newv = max(speed_slider.GetMin(), min(speed_slider.GetMax(), newv)); speed_slider.SetValue(newv)
          ui.message(f"Speed {newv}%")
        return
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

  def handle_output(self, text):
    """
    Handle result according to copy_mode.
    Mode 0: copy+history+message
    Mode 1: message only
    Mode 2: copy+history+dialog with audio controls
    """
    if self.copy_mode == 0:
      api.copyToClip(text)
      self._addToHistory(text)
      ui.message(text)
    elif self.copy_mode == 1:
      ui.message(text)
    elif self.copy_mode == 2:
      audio_thread = threading.Thread(target=self._fetch_audio_and_show_dialog, args=(text, self.last_selected_word))
      audio_thread.daemon = True
      audio_thread.start()

      api.copyToClip(text)
      self._addToHistory(text)
      self.last_definition_text = text

  def terminate(self):
    """
    Cleanly stop background threads and unregister the settings panel.
    Remove all occurrences of the panel class from NVDA's categoryClasses.
    """
    try:
      self._stop_retention_thread()
    except Exception:
      pass
    try:
      cls_list = getattr(gui.settingsDialogs.NVDASettingsDialog, "categoryClasses", [])
      while MwWordLexiconSettingsPanel in cls_list:
        try:
          cls_list.remove(MwWordLexiconSettingsPanel)
        except Exception:
          break
    except Exception:
      pass

  def threaded_request(self, target_func, *args):
    """
    Generic helper to run a function in a background thread then call handle_output on main thread.
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
    self.copy_mode = (self.copy_mode + 1) % 3
    try:
      config.conf["mwWordLexicon"]["copy_mode"] = self.copy_mode
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

  @script(description="Open Search Dialog", gesture="kb:nvda+alt+a")
  def script_showSearchDialog(self, gesture):
    global OPEN_DIALOG
    if OPEN_DIALOG:
      ui.message("Please close the open dialog before opening another.")
      return
    selected_text = get_selected_text() or ""
    try:
      dialog = SearchDialog(None, self, pre_filled_text=selected_text)
      dialog.Show()
      dialog.Raise()
      if selected_text:
        wx.CallAfter(dialog.on_search, None)
    except Exception as e:
      ui.message(f"Error opening search dialog: {e}")

  @script(description="Get word definition or copy last one if pressed quickly twice.", gesture="kb:control+shift+d")
  def script_get_definition_with_smart_copy(self, gesture):
    now = time.time()
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
    if self.copy_mode == 2:
      self.last_copy_mode2_press_time = now
    else:
      self.last_definition_press_time = now

    word = get_valid_selected_word()
    if not word:
      return
    self.last_selected_word = word

    def get_and_cache_definition(word_to_lookup):
      result = self.get_word_definition(word_to_lookup)
      if result:
        self.last_definition_text = result
      return result

    self.threaded_request(get_and_cache_definition, word)

  @script(description="Get Word of the Day with examples or copy them on quick second press.", gesture="kb:control+shift+w")
  def script_word_of_the_day(self, gesture):
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
      raw = get_word_of_the_day()
      if not raw:
        return "Failed to retrieve Word of the Day."
      word = raw.split(" - ")[0].strip()
      message = f"Word of the Day: {raw}"
      try:
        response = requests.get(DICTIONARY_API_URL.format(word))
        if response.status_code == 200:
          data = response.json()
          examples = []
          for entry in data:
            examples += extract_all_examples(entry, word)
          if examples:
            message += "\n\nExamples:\n" + "\n".join(f"{i+1}. {ex}" for i, ex in enumerate(examples))
      except Exception:
        pass
      self.word_of_the_day_text = message.strip()
      self.last_selected_word = word
      return self.word_of_the_day_text

    self.threaded_request(get_full_wotd)

  @script(description="Show or cycle through history", gesture="kb:control+shift+h")
  def script_show_history_list(self, gesture):
    if not GlobalPlugin.history:
      ui.message("No history available.")
      return

    if self.cycle_history:
      GlobalPlugin.historyIndex = (GlobalPlugin.historyIndex + 1) % len(GlobalPlugin.history)
      reversed_history = list(reversed([h.get("text") for h in GlobalPlugin.history]))
      item_to_copy = reversed_history[GlobalPlugin.historyIndex]
      try:
        api.copyToClip(item_to_copy)
        ui.message(item_to_copy)
      except Exception:
        ui.message("Failed to copy history item.")
    else:
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
      except Exception:
        ui.message("History UI error.")

  @script(description="Get thesaurus (synonyms) for the selected word.", gesture="kb:control+shift+t")
  def script_get_thesaurus(self, gesture):
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
    
    def get_and_cache_thesaurus(word_to_lookup):
      result = thesaurus.get_word_thesaurus(word_to_lookup)
      if result:
        self.last_thesaurus_text = result
      return result

    self.threaded_request(get_and_cache_thesaurus, word)

  @script(description="Get antonyms for the selected word.", gesture="kb:control+shift+u")
  def script_get_antonyms(self, gesture):
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

    def get_and_cache_antonyms(word_to_lookup):
      result = thesaurus.get_word_antonyms(word_to_lookup)
      if result:
        self.last_antonyms_text = result
      return result

    self.threaded_request(get_and_cache_antonyms, word)

# Configuration section name.
SECTION = "mwWordLexicon"

def ensure_config_section(section):
  """
  Ensure a configuration section exists in config.conf defensively.
  This function avoids reassigning config.conf and works with both
  NVDA's ConfigObj-like object or plain dicts.
  Returns a mapping-like object for the section or an ephemeral dict.
  """
  conf_obj = getattr(config, "conf", None)
  if conf_obj is None:
    config.conf = {}
    conf_obj = config.conf

  # 1) Prefer using createSection if available.
  try:
    if hasattr(conf_obj, "createSection") and callable(conf_obj.createSection):
      try:
        if section not in conf_obj:
          conf_obj.createSection(section)
      except Exception:
        pass
      try:
        return conf_obj[section]
      except Exception:
        pass
  except Exception:
    pass

  # 2) If object supports setdefault (mapping-like), use it.
  try:
    if hasattr(conf_obj, "setdefault") and callable(conf_obj.setdefault):
      sec = conf_obj.setdefault(section, {})
      if hasattr(sec, "get"):
        return sec
      try:
        conf_obj[section] = dict(sec) if sec is not None else {}
        return conf_obj[section]
      except Exception:
        return {}
  except Exception:
    pass

  # 3) Try direct assignment.
  try:
    if section not in conf_obj:
      conf_obj[section] = {}
    return conf_obj[section]
  except Exception:
    pass

  # 4) Final fallback: return ephemeral dict.
  return {}

def save_config_if_possible():
  """
  Try to persist config changes using NVDA's APIs if available.
  Tries config.save() then config.conf.write() as fallback.
  """
  try:
    save_func = getattr(config, "save", None)
    if callable(save_func):
      save_func()
      return
  except Exception:
    pass
  try:
    conf_obj = getattr(config, "conf", None)
    if conf_obj and hasattr(conf_obj, "write") and callable(conf_obj.write):
      conf_obj.write()
  except Exception:
    pass

class MwWordLexiconSettingsPanel(gui.settingsDialogs.SettingsPanel):
  """
  MW-word-lexicon settings panel (performance-tuned).
  """

  title = "MW Word Lexicon"

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._values_populated = False
    self._populating_lock = threading.Lock()

  def makeSettings(self, sizer):
    """
    Create a minimal UI quickly. Avoid reading config or performing heavy work here.
    Actual values are placed when the panel becomes visible.
    """
    try:
      settings_box = wx.StaticBox(self, label="Settings")
      settings_sizer = wx.StaticBoxSizer(settings_box, wx.VERTICAL)

      # History size
      hist_row = wx.BoxSizer(wx.HORIZONTAL)
      history_label = wx.StaticText(self, label="History size (items to keep):")
      hist_row.Add(history_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
      self.history_spin = wx.SpinCtrl(self, value="3", min=1, max=100)
      hist_row.Add(self.history_spin, 0, wx.EXPAND)
      settings_sizer.Add(hist_row, 0, wx.EXPAND | wx.ALL, 6)

      # Cycle checkbox
      self.cycle_history_cb = wx.CheckBox(self, label="Cycle through history (copy each item)")
      self.cycle_history_cb.SetValue(False)
      settings_sizer.Add(self.cycle_history_cb, 0, wx.ALL, 6)

      # Retention controls
      retention_label = wx.StaticText(self, label="History retention (0 = keep forever):")
      settings_sizer.Add(retention_label, 0, wx.ALL, 6)
      retention_row = wx.BoxSizer(wx.HORIZONTAL)
      self.retention_spin = wx.SpinCtrl(self, value="0", min=0, max=365000)
      retention_row.Add(self.retention_spin, 0, wx.RIGHT, 8)
      choices = ["minutes", "hours", "days"]
      self.retention_unit = wx.ComboBox(self, choices=choices, style=wx.CB_READONLY)
      self.retention_unit.SetValue("days")
      retention_row.Add(self.retention_unit, 0, wx.EXPAND)
      settings_sizer.Add(retention_row, 0, wx.EXPAND | wx.ALL, 6)

      # Status label for lazy-loading feedback
      self._status_label = wx.StaticText(self, label="")
      settings_sizer.Add(self._status_label, 0, wx.ALL, 4)

      sizer.Add(settings_sizer, 0, wx.EXPAND | wx.ALL, 6)

      # Bind show event to populate data lazily.
      self.Bind(wx.EVT_SHOW, self._on_show)
    except Exception:
      try:
        ui.message("MW-word-lexicon: failed to create settings UI.")
      except Exception:
        pass

  def _on_show(self, evt):
    """
    EVT_SHOW handler - populate values when panel is shown for the first time.
    Use wx.CallAfter to schedule population on the GUI thread without blocking the show.
    """
    try:
      if evt.IsShown() and not self._values_populated:
        self._values_populated = True
        try:
          self._status_label.SetLabel("Loading settings...")
        except Exception:
          pass
        wx.CallAfter(self._populate_values_safe)
    except Exception:
      pass
    try:
      evt.Skip()
    except Exception:
      pass

  def _populate_values_safe(self):
    """
    Populate controls from config in a defensive manner. Keep logic small and fast.
    """
    if not self._populating_lock.acquire(blocking=False):
      return
    try:
      sec = ensure_config_section(SECTION)

      # history_size
      try:
        v = sec.get("history_size", 3)
        self.history_spin.SetValue(str(int(v)))
      except Exception:
        try:
          self.history_spin.SetValue("3")
        except Exception:
          pass

      # cycle_history
      try:
        cv = sec.get("cycle_history", False)
        if isinstance(cv, str):
          cv_val = cv.lower() == "true"
        else:
          cv_val = bool(cv)
        self.cycle_history_cb.SetValue(cv_val)
      except Exception:
        try:
          self.cycle_history_cb.SetValue(False)
        except Exception:
          pass

      # retention value
      try:
        rv = sec.get("history_retention_value", 0)
        self.retention_spin.SetValue(str(int(rv)))
      except Exception:
        try:
          self.retention_spin.SetValue("0")
        except Exception:
          pass

      # retention unit
      try:
        ru = (sec.get("history_retention_unit") or "days").lower()
        if ru.startswith("min"):
          self.retention_unit.SetValue("minutes")
        elif ru.startswith("hour"):
          self.retention_unit.SetValue("hours")
        else:
          self.retention_unit.SetValue("days")
      except Exception:
        try:
          self.retention_unit.SetValue("days")
        except Exception:
          pass

      try:
        self._status_label.SetLabel("")
      except Exception:
        pass
    finally:
      try:
        self._populating_lock.release()
      except Exception:
        pass

  def onSave(self):
    """
    Validate and save settings defensively. Persist via save_config_if_possible
    and dispatch heavier runtime updates to a background daemon thread.
    """
    try:
      ensure_config_section(SECTION)

      # Validate history size
      try:
        new_size = int(self.history_spin.GetValue())
        if new_size < 1:
          raise ValueError("history_size must be >= 1")
      except Exception as e:
        ui.message(f"MW-word-lexicon: invalid history size ({e})")
        return

      try:
        cycle_val = bool(self.cycle_history_cb.GetValue())
      except Exception:
        cycle_val = False

      try:
        retention_value = int(self.retention_spin.GetValue())
        if retention_value < 0:
          retention_value = 0
      except Exception:
        retention_value = 0

      try:
        retention_unit = str(self.retention_unit.GetValue() or "days")
      except Exception:
        retention_unit = "days"

      # Write preserving types
      try:
        config.conf[SECTION]["history_size"] = new_size
        config.conf[SECTION]["cycle_history"] = cycle_val
        config.conf[SECTION]["history_retention_value"] = retention_value
        config.conf[SECTION]["history_retention_unit"] = retention_unit
      except Exception as e:
        ui.message(f"MW-word-lexicon: failed to write settings to config ({e})")

      # Persist configuration using NVDA API without blocking UI.
      try:
        wx.CallAfter(save_config_if_possible)
      except Exception:
        pass
    except Exception:
      try:
        ui.message("MW-word-lexicon: error during save.")
      except Exception:
        pass
      return

    # Update running plugin state off the UI thread to avoid UI lag.
    def update_running_plugins():
      try:
        for plugin in list(globalPluginHandler.runningPlugins):
          if hasattr(plugin, "script_get_definition_with_smart_copy") or plugin.__class__.__name__.endswith("GlobalPlugin"):
            try:
              plugin.history_size = new_size
            except Exception:
              pass
            try:
              plugin.cycle_history = cycle_val
            except Exception:
              pass
            try:
              while len(plugin.history) > new_size:
                plugin.history.pop(0)
            except Exception:
              pass
            try:
              if hasattr(plugin, "_updateAndSaveHistory"):
                plugin._updateAndSaveHistory(plugin.history, prune=False)
            except Exception:
              pass
            break
      except Exception:
        pass

    try:
      t = threading.Thread(target=update_running_plugins)
      t.daemon = True
      t.start()
    except Exception:
      pass