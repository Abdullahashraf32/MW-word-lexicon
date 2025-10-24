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

import requests
import re

# URL of the custom API used to fetch thesaurus (synonyms and antonyms)
THESAURUS_API_URL = "https://late-lake-4ea8.abdullahashraf4846.workers.dev/?word={}&type=thesaurus"

def strip_html_tags(text):
  """
  Remove HTML tags from a string.

  Args:
    text (str): The input text possibly containing HTML tags.

  Returns:
    str: Cleaned text without any HTML tags.
  """
  return re.sub(r'<[^>]+>', '', text)


def get_word_thesaurus(word):
  """
  Fetch synonyms for a given word using a remote thesaurus API.

  Args:
    word (str): The word to retrieve synonyms for.

  Returns:
    str: A string listing the synonyms if found, or a message indicating none were found.
  """
  try:
    # Send GET request to the API with the target word
    response = requests.get(THESAURUS_API_URL.format(word))
    
    # Check if the request was successful
    if response.status_code == 200:
      data = response.json()  # Parse JSON response
      synonyms = []

      # Iterate over each entry in the returned data
      for entry in data:
        meta = entry.get("meta", {})
        # Collect the 'syns' (synonyms) list if it exists
        synonyms.extend(meta.get("syns", []))

      # Flatten the nested list of synonym groups into a single list
      flat_synonyms = [syn for group in synonyms for syn in group]

      # Return the result string if any synonyms found
      if flat_synonyms:
        syns_text = ", ".join(flat_synonyms)
        return f"Synonyms for {word}: {syns_text}"
      else:
        return f"No synonyms found for {word}."
  except Exception as e:
    # Print error message in case of failure
    print(f"Error fetching thesaurus: {e}")
    return "Failed to fetch thesaurus."


def get_word_antonyms(word):
  """
  Fetch antonyms for a given word using a remote thesaurus API.

  Args:
    word (str): The word to retrieve antonyms for.

  Returns:
    str: A string listing the antonyms if found, or a message indicating none were found.
  """
  try:
    # Send GET request to the API with the target word
    response = requests.get(THESAURUS_API_URL.format(word))
    
    # Check if the request was successful
    if response.status_code == 200:
      data = response.json()  # Parse JSON response
      antonyms = []

      # Iterate over each entry in the returned data
      for entry in data:
        meta = entry.get("meta", {})
        # Collect the 'ants' (antonyms) list if it exists
        antonyms.extend(meta.get("ants", []))

      # Flatten the nested list of antonym groups into a single list
      flat_antonyms = [ant for group in antonyms for ant in group]

      # Return the result string if any antonyms found
      if flat_antonyms:
        ants_text = ", ".join(flat_antonyms)
        return f"Antonyms for {word}: {ants_text}"
      else:
        return f"No antonyms found for {word}."
  except Exception as e:
    # Print error message in case of failure
    print(f"Error fetching antonyms: {e}")
    return "Failed to fetch antonyms."
