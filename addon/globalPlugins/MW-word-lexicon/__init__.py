import globalPluginHandler
import ui
import time
import api
import requests
import re
from scriptHandler import script

DICTIONARY_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}"

def get_word_of_the_day():
  response = requests.get(DICTIONARY_API_URL.replace("{}", ""))
  if response.status_code == 200:
    match = re.search(r'Word of the day: <strong>(.*?)</strong>', response.text)
    if match:
      return match.group(1)
  return None

def extract_all_examples(entry):
  examples = []

  def extract_from_dt(dt):
    for part in dt:
      if part[0] == "vis":
        for vis_item in part[1]:
          if isinstance(vis_item, dict):
            text = vis_item.get("t", "")
            if text:
              examples.append(text)
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

          examples = extract_all_examples(entry)
          all_examples.extend(examples)

        if not all_definitions and not all_examples:
          return "No definitions or examples found."

        result = ""

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
  def __init__(self):
    super().__init__()
    self.last_definition_press_time = None
    self.last_wotd_press_time = None
    self.last_definition_text = None
    self.word_of_the_day_text = None

  def get_word_definition(self, word):
    return get_word_definition_from_proxy(word)

  @script(
    description="Get word definition or copy last one if pressed quickly twice.",
    gesture="kb:control+shift+d"
  )
  def script_get_definition_with_smart_copy(self, gesture):
    current_time = time.time()
    last_time = self.last_definition_press_time
    self.last_definition_press_time = current_time

    if last_time and (current_time - last_time) < 1.0:
      if self.last_definition_text:
        api.copyToClip(self.last_definition_text)
        ui.message("Text copied to clipboard.")
        self.last_definition_text = None
      else:
        ui.message("No recent definition to copy.")
      return

    selected = get_selected_text()
    if not selected:
      ui.message("No text selected.")
      return

    definition = self.get_word_definition(selected)
    if definition:
      self.last_definition_text = definition
      ui.message(definition)
    else:
      ui.message("Definition not found.")

  @script(
    description="Get Word of the Day or copy it on quick second press.",
    gesture="kb:control+shift+w"
  )
  def script_word_of_the_day(self, gesture):
    current_time = time.time()
    last_time = self.last_wotd_press_time
    self.last_wotd_press_time = current_time

    if last_time and (current_time - last_time) < 1.0:
      if self.word_of_the_day_text:
        api.copyToClip(self.word_of_the_day_text)
        ui.message("Text copied to clipboard.")
        self.word_of_the_day_text = None
      else:
        ui.message("No Word of the Day to copy.")
      return

    word = get_word_of_the_day()
    if word:
      definition = self.get_word_definition(word)
      if definition:
        full_text = f"Word of the Day: {word} - {definition}"
        self.word_of_the_day_text = full_text
        ui.message(full_text)
      else:
        message = f"Word of the Day: {word} (No definition found)"
        self.word_of_the_day_text = message
        ui.message(message)
    else:
      ui.message("Failed to retrieve Word of the Day.")
