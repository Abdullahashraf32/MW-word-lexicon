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
from . import thesaurus

addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
  sys.path.insert(0, addon_dir)

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
  return None

def get_selected_text():
  try:
    reviewPos = api.getReviewPosition()
    if reviewPos and reviewPos.text:
      return reviewPos.text.strip()
  except Exception:
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

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
  history = []
  historyIndex = -1
  restoring = False

  def __init__(self):
    super().__init__()
    self.last_definition_press_time = None
    self.last_wotd_press_time = None
    self.last_definition_text = None
    self.word_of_the_day_text = None
    if "mwWordLexicon" not in config.conf:
      config.conf.createSection("mwWordLexicon")
    self.copy_mode = int(config.conf["mwWordLexicon"].get("copy_mode", 1))
    self.last_copy_mode2_press_time = None
    self.last_thesaurus_press_time = None
    self.last_thesaurus_text = None
    self.last_antonyms_press_time = None
    self.last_antonyms_text = None

  def _addToHistory(self, text):
    if not api.getClipData() or api.getClipData().strip() != text.strip():
      return
    if not GlobalPlugin.history or text != GlobalPlugin.history[-1]:
      GlobalPlugin.history.append(text)
      if len(GlobalPlugin.history) > 3:
        GlobalPlugin.history.pop(0)
    GlobalPlugin.historyIndex = -1

  def get_word_definition(self, word):
    return get_word_definition_from_proxy(word)

  def handle_output(self, text):
    if self.copy_mode == 0:
      api.copyToClip(text)
      self._addToHistory(text)
      ui.message(text)
    elif self.copy_mode == 1:
      ui.message(text)
      self.last_definition_text = text
    elif self.copy_mode == 2:
      def show_dialog_with_audio(text, word):
        try:
          response = requests.get(DICTIONARY_API_URL.format(word))
          if response.status_code != 200:
            ui.message("Failed to retrieve audio data.")
            return

          data = response.json()
          audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
          if not audio_id:
            ui.message("No pronunciation audio available.")
            return

          subfolder = audio_id[0]
          audio_url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subfolder}/{audio_id}.mp3"

          frame = wx.Frame(None, title="Definition", size=(600, 400))
          panel = wx.Panel(frame)
          sizer = wx.BoxSizer(wx.VERTICAL)

          text_ctrl = wx.TextCtrl(panel, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
          sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)

          play_button = wx.Button(panel, label="Play")
          sizer.Add(play_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
          play_button.Bind(wx.EVT_BUTTON, lambda evt: play_with_ffplay(audio_url, speed_slider.GetValue(), volume_slider.GetValue()))

          speed_label = wx.StaticText(panel, label="Speed:")
          sizer.Add(speed_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          speed_slider = wx.Slider(panel, value=100, minValue=50, maxValue=200, style=wx.SL_HORIZONTAL)
          sizer.Add(speed_slider, 0, wx.EXPAND | wx.ALL, 10)

          volume_label = wx.StaticText(panel, label="Volume:")
          sizer.Add(volume_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          volume_slider = wx.Slider(panel, value=100, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
          sizer.Add(volume_slider, 0, wx.EXPAND | wx.ALL, 10)

          ok_button = wx.Button(panel, label="OK")
          ok_button.Bind(wx.EVT_BUTTON, lambda evt: frame.Close())
          sizer.Add(ok_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)

          panel.SetSizer(sizer)
          frame.Show()
          frame.Raise()

        except Exception as e:
          ui.message(f"Error: {str(e)}")

      wx.CallAfter(show_dialog_with_audio, text, self.last_selected_word)
      api.copyToClip(text)
      self._addToHistory(text)
      self.last_definition_text = text

  @script(description="Cycle copy/display modes", gesture="kb:control+shift+a")
  def script_cycle_copy_mode(self, gesture):
    self.copy_mode = (self.copy_mode + 1) % 3
    try:
      config.conf["mwWordLexicon"]["copy_mode"] = self.copy_mode
      config.save()
    except Exception:
      pass
    ui.message(["Auto copy", "Double press to copy", "Copy and show dialog"][self.copy_mode])

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
    definition = self.get_word_definition(word)
    if definition:
      self.last_definition_text = definition
      self.handle_output(definition)
    else:
      ui.message("Definition not found.")

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

    raw = get_word_of_the_day()
    if not raw:
      ui.message("Failed to retrieve Word of the Day.")
      return

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
    self.handle_output(self.word_of_the_day_text)

  @script(description="Cycle through previously retrieved word definitions.", gesture="kb:control+shift+h")
  def script_cycle_previous_definitions(self, gesture):
    if not GlobalPlugin.history:
      ui.message("No history available.")
      return
    if not GlobalPlugin.restoring:
      GlobalPlugin.restoring = True
      GlobalPlugin.historyIndex = len(GlobalPlugin.history) - 1
    else:
      GlobalPlugin.historyIndex -= 1
    if GlobalPlugin.historyIndex < 0:
      ui.message("Reached the beginning of history.")
      GlobalPlugin.restoring = False
      GlobalPlugin.historyIndex = -1
      return
    text = GlobalPlugin.history[GlobalPlugin.historyIndex]
    api.copyToClip(text)
    ui.message(text)

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
    synonyms = thesaurus.get_word_thesaurus(word)
    if synonyms:
      self.last_thesaurus_text = synonyms
      self.handle_output(synonyms)
    else:
      ui.message("No synonyms found.")

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
    antonyms = thesaurus.get_word_antonyms(word)
    if antonyms:
      self.last_antonyms_text = antonyms
      self.handle_output(antonyms)
    else:
      ui.message("No antonyms found.")
