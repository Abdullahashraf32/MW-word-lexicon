import requests
import re

THESAURUS_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}&type=thesaurus"

def strip_html_tags(text):
  return re.sub(r'<[^>]+>', '', text)

def get_word_thesaurus(word):
  try:
    response = requests.get(THESAURUS_API_URL.format(word))
    if response.status_code == 200:
      data = response.json()
      synonyms = []

      for entry in data:
        meta = entry.get("meta", {})
        synonyms.extend(meta.get("syns", []))

      flat_synonyms = [syn for group in synonyms for syn in group]
      if flat_synonyms:
        syns_text = ", ".join(flat_synonyms[:20])  # نعرض أول 20 مرادف فقط
        return f"Synonyms for {word}: {syns_text}"
      else:
        return f"No synonyms found for {word}."
  except Exception as e:
    print(f"Error fetching thesaurus: {e}")
    return "Failed to fetch thesaurus."
