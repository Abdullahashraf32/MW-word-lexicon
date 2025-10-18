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

addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
  sys.path.insert(0, addon_dir)

try:
  from . import selection_helper
except Exception:
  try:
    import selection_helper
  except Exception:
    selection_helper = None
OPEN_DIALOG = None

def _clear_open_dialog(evt, frame):
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
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_hwnd(hwnd)
      out_container.append(res)
  except Exception:
    out_container.append(None)

def _call_selection_helper_foreground(out_container):
  try:
    if selection_helper:
      res = selection_helper.get_selection_for_foreground()
      out_container.append(res)
  except Exception:
    out_container.append(None)

DICTIONARY_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}"

def strip_html_tags(text):
  return re.sub(r'<[^>]+>', '', text)

def play_with_ffplay(audio_url, speed=100, volume=100):
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
  url = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/wotd"
  response = requests.get(url)
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
  text = re.sub(r"{[^{}]+}", "", text)
  pattern = re.compile(r"{[^{}]*}?" + re.escape(keyword) + r"{[^{}]*}?|(?<!\w)" + re.escape(keyword) + r"(?!\w)", re.IGNORECASE)
  return pattern.sub(lambda m: f"({keyword})", text).strip()

def extract_all_examples(entry, keyword):
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
  except Exception as e:
    print(f"Error extracting examples: {e}")
  return examples

def get_word_definition_from_proxy(word):
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
      except Exception as e:
        print(f"Error parsing definition: {e}")
  except requests.RequestException:
    return "Failed to connect to the dictionary service."
  return None

def get_selected_text_via_helper_with_hwnd(hwnd, timeout_seconds=0.5):
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
    try:
      wh = getattr(reviewPos, "windowHandle", None)
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
      wh = getattr(reviewPos, "hwnd", None)
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
  selected = get_selected_text()
  if not selected:
    ui.message("No text selected.")
    return None
  return selected

def handle_double_press(last_time, current_time, cached_text, label="Text"):
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
  seconds = _get_history_retention_seconds()
  if not seconds:
    return history_list
  cutoff = time.time() - seconds
  return [item for item in history_list if item.get("ts", 0) >= cutoff]

class SearchDialog(wx.Frame):
  def __init__(self, parent, pre_filled_text=""):
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

      wx.CallAfter(on_complete)
      
    thread = threading.Thread(target=worker)
    thread.daemon = True
    thread.start()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
  history = []
  historyIndex = -1
  restoring = False

  def __init__(self):
    super().__init__()
    gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(MwWordLexiconSettingsPanel)
    self.last_definition_press_time = None
    self.last_wotd_press_time = None
    self.last_definition_text = None
    self.word_of_the_day_text = None
    if "mwWordLexicon" not in config.conf:
      config.conf.createSection("mwWordLexicon")
    try:
      self.history_size = int(config.conf["mwWordLexicon"].get("history_size", 3))
    except:
      self.history_size = 3
    hist_json = config.conf["mwWordLexicon"].get("history_json", "[]")
    try:
      parsed = json.loads(hist_json)
      if isinstance(parsed, list):
        normalized = []
        now = time.time()
        for item in parsed:
          if isinstance(item, dict) and "text" in item:
            text = item.get("text") or ""
            ts = float(item.get("ts", 0))
            normalized.append({"text": text, "ts": ts})
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
    self._retention_stop_event = threading.Event()
    self._retention_thread = threading.Thread(target=self._retention_worker)
    self._retention_thread.daemon = True
    self._retention_thread.start()
    try:
      self._periodic_prune_check()
    except Exception:
      pass

  def _updateAndSaveHistory(self, new_history, prune=True):
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
    except Exception as e:
      print(f"Failed to save history: {e}")

  def _addToHistory(self, text):
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

  def handle_output(self, text):
    if self.copy_mode == 0:
      api.copyToClip(text)
      self._addToHistory(text)
      ui.message(text)
    elif self.copy_mode == 1:
      ui.message(text)
    elif self.copy_mode == 2:
      def fetch_audio_and_show_dialog(text, word):
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

          wx.CallAfter(create_and_show_dialog, text, audio_url, word)

        except Exception as e:
          wx.CallAfter(ui.message, f"Error: {str(e)}")

      def create_and_show_dialog(text, audio_url, original_word):
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
            try:
              sp = speed_slider.GetValue() if speed_slider else 100
            except Exception:
              sp = 100
            try:
              vol = volume_slider.GetValue() if volume_slider else 100
            except Exception:
              vol = 100
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
              wx.CallAfter(ui.message, "Failed to retrieve audio data.")
              return
            data = resp.json()
            audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
            if not audio_id:
              wx.CallAfter(ui.message, "No pronunciation audio available for that word.")
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
            sel = ""
            try:
              sel = text_ctrl.GetStringSelection().strip()
            except Exception:
              sel = ""
            if sel:
              words = [w for w in re.split(r'\s+', sel) if w]
              if len(words) > 1:
                ui.message("Cannot play pronunciation: select a single word.")
              else:
                sel_word = words[0]
                threading.Thread(target=_play_word_lookup, args=(sel_word,), daemon=True).start()
            else:
              if audio_url:
                threading.Thread(target=do_play_for_url, args=(audio_url,), daemon=True).start()
              else:
                threading.Thread(target=_play_word_lookup, args=(original_word,), daemon=True).start()
            return
          if evt.ShiftDown() and kc in (wx.WXK_UP, wx.WXK_DOWN):
            if speed_slider:
              cur = speed_slider.GetValue()
              step = 5
              newv = cur + (step if kc == wx.WXK_UP else -step)
              newv = max(speed_slider.GetMin(), min(speed_slider.GetMax(), newv))
              speed_slider.SetValue(newv)
              ui.message(f"Speed {newv}%")
            else:
              evt.Skip()
            return
          if evt.ControlDown() and kc in (wx.WXK_UP, wx.WXK_DOWN):
            if volume_slider:
              cur = volume_slider.GetValue()
              step = 5
              newv = cur + (step if kc == wx.WXK_UP else -step)
              newv = max(volume_slider.GetMin(), min(volume_slider.GetMax(), newv))
              volume_slider.SetValue(newv)
              ui.message(f"Volume {newv}%")
            else:
              evt.Skip()
            return
          evt.Skip()

        frame.Bind(wx.EVT_CHAR_HOOK, on_char_hook)
        frame.Bind(wx.EVT_CLOSE, lambda evt: _clear_open_dialog(evt, frame))
        panel.SetSizer(sizer)
        frame.Show()
        frame.Raise()

      audio_thread = threading.Thread(target=fetch_audio_and_show_dialog, args=(text, self.last_selected_word))
      audio_thread.daemon = True
      audio_thread.start()

      api.copyToClip(text)
      self._addToHistory(text)
      self.last_definition_text = text

  def terminate(self):
    try:
      self._stop_retention_thread()
    except Exception:
      pass
    try:
      NVDASettingsDialog.categoryClasses.remove(MwWordLexiconSettingsPanel)
    except (ValueError, AttributeError):
      pass

  def threaded_request(self, target_func, *args):
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

  @script(
      description="Open Search Dialog", 
      gesture="kb:nvda+alt+a"
      )
  def script_showSearchDialog(self, gesture):
    global OPEN_DIALOG
    if OPEN_DIALOG:
      ui.message("Please close the open dialog before opening another.")
      return
    selected_text = get_selected_text() or ""
    try:
      dialog = SearchDialog(None, pre_filled_text=selected_text)
      dialog.Show()
      dialog.Raise()
      if selected_text:
        wx.CallAfter(dialog.on_search, None)
    except Exception as e:
      ui.message(f"Error opening search dialog: {e}")

  @script(
      description="Get word definition or copy last one if pressed quickly twice.",
      gesture="kb:control+shift+d"
      )
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
      if status == "copied":
        self._addToHistory(self.last_definition_text)
        self.last_definition_text = None
        return
      elif status == "empty":
        return

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
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_wotd_press_time, now, self.word_of_the_day_text, "Word of the Day")
      if status == "copied":
        self._addToHistory(self.word_of_the_day_text)
        self.word_of_the_day_text = None
        return
      elif status == "empty":
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
    if not GlobalPlugin.history:
      ui.message("No history available.")
      return

    if self.cycle_history:
      GlobalPlugin.historyIndex = (GlobalPlugin.historyIndex + 1) % len(GlobalPlugin.history)
      reversed_history = list(reversed(GlobalPlugin.history))
      item_to_copy = reversed_history[GlobalPlugin.historyIndex]
      try:
        api.copyToClip(item_to_copy)
        ui.message(item_to_copy)
      except Exception as e:
        ui.message(f"Failed to copy history item: {e}")
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
          sel = lb.GetSelection()
          if sel == wx.NOT_FOUND:
            ui.message("No item selected.")
            return
          text = lb.GetString(sel)
          try:
            api.copyToClip(text)
            ui.message("History item copied.")
          except:
            ui.message("Failed to copy item.")

        def do_copy_all(event=None):
          all_items = "\n\n".join(lb.GetItems())
          if not all_items:
            ui.message("History is empty.")
            return
          try:
            api.copyToClip(all_items)
            ui.message("All history items copied.")
          except:
            ui.message("Failed to copy all items.")

        def do_remove_selected(event=None):
          sel = lb.GetSelection()
          if sel == wx.NOT_FOUND:
            ui.message("No item selected.")
            return

          original_index = len(GlobalPlugin.history) - 1 - sel
          GlobalPlugin.history.pop(original_index)
          self._updateAndSaveHistory(GlobalPlugin.history)

          lb.Delete(sel)
          ui.message("Item removed.")

          if lb.GetCount() > 0:
            new_sel = min(sel, lb.GetCount() - 1)
            lb.SetSelection(new_sel)

        def do_clear_history(event=None):
          dialog = wx.MessageDialog(frame, "Are you sure you want to clear the entire history?", "Confirm Clear", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
          if dialog.ShowModal() == wx.ID_YES:
            self._updateAndSaveHistory([])
            lb.Clear()
            ui.message("History cleared.")
            frame.Close()
          dialog.Destroy()

        ID_COPY = wx.NewIdRef()
        ID_COPY_ALL = wx.NewIdRef()
        ID_REMOVE = wx.NewIdRef()
        ID_CLEAR = wx.NewIdRef()

        def on_context_menu(event):
          menu = wx.Menu()
          menu.Append(ID_COPY, "Copy\tCtrl+C")
          menu.Append(ID_COPY_ALL, "Copy All History Items\tCtrl+Shift+C")
          menu.AppendSeparator()
          menu.Append(ID_REMOVE, "Remove Current History Item\tDelete")
          menu.Append(ID_CLEAR, "Clear History\tShift+Delete")

          frame.PopupMenu(menu)
          menu.Destroy()

        lb.Bind(wx.EVT_CONTEXT_MENU, on_context_menu)

        frame.Bind(wx.EVT_MENU, do_copy_selected, id=ID_COPY)
        frame.Bind(wx.EVT_MENU, do_copy_all, id=ID_COPY_ALL)
        frame.Bind(wx.EVT_MENU, do_remove_selected, id=ID_REMOVE)
        frame.Bind(wx.EVT_MENU, do_clear_history, id=ID_CLEAR)
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())

        accel_tbl = wx.AcceleratorTable([
          (wx.ACCEL_CTRL, ord('C'), ID_COPY),
          (wx.ACCEL_CTRL | wx.ACCEL_SHIFT, ord('C'), ID_COPY_ALL),
          (wx.ACCEL_NORMAL, wx.WXK_DELETE, ID_REMOVE),
          (wx.ACCEL_SHIFT, wx.WXK_DELETE, ID_CLEAR)
        ])
        frame.SetAcceleratorTable(accel_tbl)

        def on_char_hook(evt):
          if evt.GetKeyCode() == wx.WXK_ESCAPE:
            frame.Close()
          else:
            evt.Skip()

        frame.Bind(wx.EVT_CHAR_HOOK, on_char_hook)
        frame.Bind(wx.EVT_CLOSE, lambda evt: _clear_open_dialog(evt, frame))

        panel.SetSizer(sizer)
        frame.Show()
        frame.Raise()
        wx.CallAfter(lb.SetFocus)
      except Exception as e:
        ui.message(f"History UI error: {e}")

  @script(
      description="Get thesaurus (synonyms) for the selected word.",
      gesture="kb:control+shift+t"
      )
  def script_get_thesaurus(self, gesture):
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_thesaurus_press_time, now, self.last_thesaurus_text, "Thesaurus")
      if status == "copied":
        self._addToHistory(self.last_thesaurus_text)
        self.last_thesaurus_text = None
        return
      elif status == "empty":
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
    now = time.time()
    if self.copy_mode == 1:
      status = handle_double_press(self.last_antonyms_press_time, now, self.last_antonyms_text, "Antonyms")
      if status == "copied":
        self._addToHistory(self.last_antonyms_text)
        self.last_antonyms_text = None
        return
      elif status == "empty":
        return
    self.last_antonyms_press_time = now

    word = get_valid_selected_word()
    if not word:
      return
    self.last_selected_word = word
    self.threaded_request(thesaurus.get_word_antonyms, word)

SECTION = "mwWordLexicon"

class MwWordLexiconSettingsPanel(SettingsPanel):
  title = "MW Word Lexicon"

  def makeSettings(self, sizer):
    if SECTION not in config.conf:
      config.conf.createSection(SECTION)

    current_size = int(config.conf[SECTION].get("history_size", "3"))
    cycle_history = str(config.conf[SECTION].get("cycle_history", False)).lower() == 'true'
    current_retention_value = int(config.conf[SECTION].get("history_retention_value", "0"))
    current_retention_unit = str(config.conf[SECTION].get("history_retention_unit", "days"))

    settings_sizer = wx.StaticBoxSizer(wx.VERTICAL, self, label="Settings")

    history_label = wx.StaticText(self, label="History size (number of items to keep):")
    settings_sizer.Add(history_label, 0, wx.ALL, 5)

    self.history_spin = wx.SpinCtrl(self, value=str(current_size), min=1, max=100)
    settings_sizer.Add(self.history_spin, 0, wx.EXPAND | wx.ALL, 5)

    self.cycle_history_cb = wx.CheckBox(self, label="Cycle through history directly (copies each item)")
    self.cycle_history_cb.SetValue(cycle_history)
    settings_sizer.Add(self.cycle_history_cb, 0, wx.ALL, 5)

    retention_label = wx.StaticText(self, label="History retention (value + unit, 0 = keep forever):")
    settings_sizer.Add(retention_label, 0, wx.ALL, 5)

    retention_row = wx.BoxSizer(wx.HORIZONTAL)
    self.retention_spin = wx.SpinCtrl(self, value=str(current_retention_value), min=0, max=365000)
    retention_row.Add(self.retention_spin, 0, wx.RIGHT | wx.ALL, 5)
    choices = ["minutes", "hours", "days"]
    self.retention_unit = wx.ComboBox(self, choices=choices, style=wx.CB_READONLY)
    cu = str(current_retention_unit).lower()
    if cu.startswith("min"):
      self.retention_unit.SetValue("minutes")
    elif cu.startswith("hour"):
      self.retention_unit.SetValue("hours")
    else:
      self.retention_unit.SetValue("days")
    retention_row.Add(self.retention_unit, 0, wx.ALL, 5)

    settings_sizer.Add(retention_row, 0, wx.EXPAND | wx.ALL, 5)

    sizer.Add(settings_sizer, 0, wx.EXPAND | wx.ALL, 5)

  def onSave(self):
    new_size = self.history_spin.GetValue()
    config.conf[SECTION]["history_size"] = new_size
    config.conf[SECTION]["cycle_history"] = self.cycle_history_cb.GetValue()

    try:
      retention_value = int(self.retention_spin.GetValue())
    except Exception:
      retention_value = 0
    retention_unit = str(self.retention_unit.GetValue() or "days")

    config.conf[SECTION]["history_retention_value"] = retention_value
    config.conf[SECTION]["history_retention_unit"] = retention_unit

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

    now = time.time()
    for plugin in globalPluginHandler.runningPlugins:
      if hasattr(plugin, "script_get_definition_with_smart_copy"):
        plugin.history_size = new_size
        plugin.cycle_history = self.cycle_history_cb.GetValue()
        while len(plugin.history) > new_size:
          plugin.history.pop(0)
        try:
          normalized = []
          for item in plugin.history:
            if isinstance(item, dict) and "text" in item:
              ts = float(item.get("ts", 0))
              if not ts:
                ts = now
              normalized.append({"text": item.get("text") or "", "ts": ts})
            elif isinstance(item, str):
              normalized.append({"text": item, "ts": now})
          plugin._updateAndSaveHistory(normalized, prune=False)
        except Exception:
          pass
        break
