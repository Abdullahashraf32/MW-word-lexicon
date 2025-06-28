import os
import sys

addon_dir = os.path.dirname(__file__)
if addon_dir not in sys.path:
  sys.path.insert(0, addon_dir)
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

DICTIONARY_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}"

def strip_html_tags(text):
  return re.sub(r'<[^>]+>', '', text)

def play_with_ffplay(audio_url, speed=100, volume=100):
  try:
    ffplay_path = os.path.join(os.path.dirname(__file__), "bin", "ffplay.exe")
    rate = max(50, min(speed, 200)) / 100  # Clamp between 0.5x and 2x
    vol = max(0, min(volume, 100))         # Clamp between 0 and 100
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
  text = pattern.sub(lambda m: f"({keyword})", text)
  return text.strip()

def extract_all_examples(entry, keyword):
  examples = []

  def extract_from_dt(dt):
    for part in dt:
      if part[0] == "vis":
        for vis_item in part[1]:
          if isinstance(vis_item, dict):
            text = vis_item.get("t", "")
            if text:
              cleaned = clean_example_text(text, keyword)
              examples.append(cleaned)
      elif isinstance(part[1], list):
        for subpart in part[1]:
          if isinstance(subpart, list):
            extract_from_dt(subpart)

  try:
    defs = entry.get("def", [])
    for d in defs:
      for sseq in d.get("sseq", []):
        for item in sseq:
          if len(item) >= 2 and isinstance(item[1], dict):
            dt = item[1].get("dt", [])
            extract_from_dt(dt)
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
          if not isinstance(entry, dict):
            continue

          defs = entry.get("shortdef", [])
          all_definitions.extend(defs)

          examples = extract_all_examples(entry, word)
          all_examples.extend(examples)

        if not all_definitions and not all_examples:
          return "No definitions found."

        result = f"{word}:\n"

        if all_definitions:
          result += "Definitions:\n"
          for i, d in enumerate(all_definitions, 1):
            result += f"{i}. {d}\n"

        if all_examples:
          result += "\nExamples:\n"
          for i, ex in enumerate(all_examples, 1):
            result += f"{i}. {ex}\n"

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
  return None

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
    self.lastPressTime = None
    self.last_thesaurus_press_time = None
    self.last_thesaurus_text = None
    self.last_antonyms_press_time = None
    self.last_antonyms_text = None

  def _addToHistory(self, text):
    clipboard_text = api.getClipData()
    if not clipboard_text or clipboard_text.strip() != text.strip():
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
          if not data or not isinstance(data, list):
            ui.message("Invalid data format.")
            return

          audio_id = data[0].get('hwi', {}).get('prs', [{}])[0].get('sound', {}).get('audio')
          if not audio_id:
            ui.message("No pronunciation audio available.")
            return

          subfolder = audio_id[0]
          audio_url = f"https://media.merriam-webster.com/audio/prons/en/us/mp3/{subfolder}/{audio_id}.mp3"
          print(audio_url)

          frame = wx.Frame(None, title="Definition", size=(600, 400))
          panel = wx.Panel(frame)
          sizer = wx.BoxSizer(wx.VERTICAL)

          text_ctrl = wx.TextCtrl(panel, value=text, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL)
          sizer.Add(text_ctrl, 1, wx.EXPAND | wx.ALL, 10)

          def on_play(event):
            speed = speed_slider.GetValue()
            volume = volume_slider.GetValue()
            play_with_ffplay(audio_url, speed, volume)

          play_button = wx.Button(panel, label="Play")
          play_button.Bind(wx.EVT_BUTTON, on_play)
          sizer.Add(play_button, 0, wx.ALIGN_CENTER | wx.BOTTOM, 10)
          speed_label = wx.StaticText(panel, label="Speed:")
          sizer.Add(speed_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          speed_slider = wx.Slider(panel, value=100, minValue=50, maxValue=200, style=wx.SL_HORIZONTAL)
          sizer.Add(speed_slider, 0, wx.EXPAND | wx.ALL, 10)
          volume_label = wx.StaticText(panel, label="Volume:")
          sizer.Add(volume_label, 0, wx.ALIGN_CENTER | wx.BOTTOM, 5)
          volume_slider = wx.Slider(panel, value=100, minValue=0, maxValue=100, style=wx.SL_HORIZONTAL)
          sizer.Add(volume_slider, 0, wx.EXPAND | wx.ALL, 10)

          ok_button = wx.Button(panel, label="OK")
          ok_button.Bind(wx.EVT_BUTTON, lambda event: frame.Close())
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
    mode_name = ["Auto copy", "Double press to copy", "Copy and show dialog"][self.copy_mode]
    ui.message(f"Switched to: {mode_name}")

  @script(
    description="Get word definition or copy last one if pressed quickly twice.",
    gesture="kb:control+shift+d"
  )
  def script_get_definition_with_smart_copy(self, gesture):
    current_time = time.time()
    last_time = self.last_definition_press_time
    self.last_definition_press_time = current_time

    if self.copy_mode == 2:
      last_mode2_time = self.last_copy_mode2_press_time
      self.last_copy_mode2_press_time = current_time

      if last_mode2_time and (current_time - last_mode2_time) < 1.0:
        if self.last_definition_text:
          api.copyToClip(self.last_definition_text)
          self._addToHistory(self.last_definition_text)
          ui.message("Text copied to clipboard.")
          self.last_definition_text = None
        else:
          ui.message("No recent definition to copy.")
        return

      selected = get_selected_text()
      self.last_selected_word = selected
      if not selected:
        ui.message("No text selected.")
        return

      definition = self.get_word_definition(selected)
      if definition:
        self.handle_output(definition)
      else:
        ui.message("Definition not found.")

    elif self.copy_mode == 1:
      if last_time and (current_time - last_time) < 1.0:
        if self.last_definition_text:
          api.copyToClip(self.last_definition_text)
          self._addToHistory(self.last_definition_text)
          ui.message("Text copied to clipboard.")
          self.last_definition_text = None
        else:
          ui.message("No recent definition to copy.")
        return

      selected = get_selected_text()
      self.last_selected_word = selected
      if not selected:
        ui.message("No text selected.")
        return

      definition = self.get_word_definition(selected)
      if definition:
        self.handle_output(definition)
      else:
        ui.message("Definition not found.")

    elif self.copy_mode == 0:
      selected = get_selected_text()
      self.last_selected_word = selected
      if not selected:
        ui.message("No text selected.")
        return

      definition = self.get_word_definition(selected)
      if definition:
        self.handle_output(definition)
      else:
        ui.message("Definition not found.")

  @script(description="Get Word of the Day with examples or copy them on quick second press.",
           gesture="kb:control+shift+w"
           )
  def script_word_of_the_day(self, gesture):
    current_time = time.time()
    last_time = self.last_wotd_press_time
    self.last_wotd_press_time = current_time

    if self.copy_mode == 1 and last_time and (current_time - last_time) < 1.5:
      if self.word_of_the_day_text:
        api.copyToClip(self.word_of_the_day_text)
        self._addToHistory(self.word_of_the_day_text)
        ui.message("Text copied to clipboard.")
        self.word_of_the_day_text = None
      else:
        ui.message("No Word of the Day to copy.")
      return

    raw = get_word_of_the_day()
    if raw:
      word = raw.split(" - ")[0].strip()
      message = f"Word of the Day: {raw}"

      response = requests.get(DICTIONARY_API_URL.format(word))
      if response.status_code == 200:
        try:
          data = response.json()
          if data and isinstance(data, list):
            all_examples = []
            for entry in data:
              if not isinstance(entry, dict):
                continue
              examples = extract_all_examples(entry, word)
              all_examples.extend(examples)

            if all_examples:
              message += "\n\nExamples:\n"
              for i, ex in enumerate(all_examples, 1):
                message += f"{i}. {ex}\n"
        except Exception as e:
          print(f"Error extracting examples: {e}")

      self.word_of_the_day_text = message.strip()
      self.last_selected_word = word
      self.handle_output(self.word_of_the_day_text)
    else:
      ui.message("Failed to retrieve Word of the Day.")

  @script( 
    description="Cycle through previously retrieved word definitions.",
    gesture="kb:control+Shift+H"
  )
  def script_cycle_previous_definitions(self, gesture):
    if not GlobalPlugin.history:
      ui.message("No history available.")
      return

    if GlobalPlugin.restoring is False:
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
    current_time = time.time()
    last_time = self.last_thesaurus_press_time
    self.last_thesaurus_press_time = current_time

    if self.copy_mode == 1 and last_time and (current_time - last_time) < 1.5:
      if self.last_thesaurus_text:
        api.copyToClip(self.last_thesaurus_text)
        self._addToHistory(self.last_thesaurus_text)
        ui.message("Text copied to clipboard.")
        self.last_thesaurus_text = None
      else:
        ui.message("No recent thesaurus text to copy.")
      return

    selected = get_selected_text()
    self.last_selected_word = selected
    if not selected:
      ui.message("No text selected.")
      return

    synonyms = thesaurus.get_word_thesaurus(selected)
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
    current_time = time.time()
    last_time = self.last_antonyms_press_time
    self.last_antonyms_press_time = current_time

    if self.copy_mode == 1 and last_time and (current_time - last_time) < 1.5:
      if self.last_antonyms_text:
        api.copyToClip(self.last_antonyms_text)
        self._addToHistory(self.last_antonyms_text)
        ui.message("Text copied to clipboard.")
        self.last_antonyms_text = None
      else:
        ui.message("No recent antonyms to copy.")
      return

    selected = get_selected_text()
    self.last_selected_word = selected
    if not selected:
      ui.message("No text selected.")
      return

    antonyms = thesaurus.get_word_antonyms(selected)
    if antonyms:
      self.last_antonyms_text = antonyms
      self.handle_output(antonyms)
    else:
      ui.message("No antonyms found.")
