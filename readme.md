# MW Word Lexicon: Add-on User Guide

## Introduction
The MW Word Lexicon add-on is a powerful tool designed to integrate a comprehensive dictionary and thesaurus directly into NVDA. Its main goal is to allow you to look up word definitions, synonyms, and antonyms instantly from any application without interrupting your work and having to open a dedicated page in your web browser to access different dictionaries.

This add-on uses the **Merriam-Webster Dictionary API** because it offers a generous free plan of **1,000 requests per day**. This ensures the add-on can remain free and reliable for all users. As a non-profit project, using a service that does not require payment was a key consideration during the add-on's design phases.

## Key Features
* **Instant Lookups:** Get definitions, synonyms, and antonyms for any selected word.
* **Word of the Day:** Discover a new word daily to expand your vocabulary.
* **Flexible Output Modes:** Choose how you receive results: auto-copy to the clipboard while speaking the definition, speak-only (requiring a double press to copy), or a detailed interactive dialog.
* **Interactive Dialogs:** Fully accessible dialogs for definitions, search, and history, complete with keyboard navigation and unique features.
* **Comprehensive History:** The add-on keeps a record of your recent lookups for easy review and management.

## Understanding the Interactive Dialogs
The add-on includes three main dialogs, each designed for a specific purpose to enhance your workflow.

### The Definition Dialog
This dialog appears when you are in "Copy and Show Dialog" mode and provides a rich environment for exploring word definitions. It's more than just a text viewer; it's a learning tool.

* **Pronunciation Playback:** You can listen to the pronunciation of the word you looked up by pressing `Ctrl+P`. More importantly, you can select any **single word** within the results area and press `Ctrl+P` to listen to its pronunciation.

* **Why a single word only?** This feature is intentionally designed to help you learn the correct pronunciation of new words you encounter, especially the synonyms and antonyms that appear in search results. If you try to select more than one word, the action will fail, and you will receive an error message, as the goal is precise, single-word pronunciation.

* **Persistent Audio Controls:** The dialog includes sliders for adjusting playback **Speed** and **Volume**. The add-on remembers your settings. When you adjust the sliders to your preferred levels, these values are saved. The next time you open NVDA, the sliders will be at the same levels you left them, providing a consistent experience.

### The History Dialog
This dialog acts as your personal log of looked-up words. It allows you to review, reuse, and manage your search history efficiently.

* **Central Control via Context Menu:** Your history is displayed in a simple list. The primary way to interact with it is to focus on the  history item you need within the list and press the **Applications key** to open a context menu. This menu gives you full control, with options to "Copy the currently focused item," "Remove the currently focused item," "Copy all history items," and "Clear all history items."

* **Keyboard Shortcuts as a Seamless and Quick Access Method:** For users who prefer the keyboard, shortcuts like `Ctrl+C` to copy the history focused item and `Delete` to remove the current history focused item are provided. These shortcuts are time-saving alternatives that perform the same actions found in the context menu.

### The Manual Search Dialog
You can open it by pressing `NVDA+Alt+A`, this is ideal for words you want to type and search for manually.

* **Flexible Search Types:** It contains a combo box that allows you to specify what you are looking for: a **definition**, **synonyms**, or **antonyms**.

* **Smart Auto-Search:** This dialog has a convenient, time-saving feature. If you select text in the current open window before pressing `NVDA+Alt+A`, the dialog will automatically perform a search for that text the moment it opens. It then intelligently moves the focus directly to the results area, allowing you to start reading the information immediately without any extra steps.

## Settings and Customization
To customize the add-on, go to the NVDA menu, then **Preferences -> Settings -> MW Word Lexicon** category.

* **History size:** Sets the maximum number of lookups you want to store in the history.
* **Cycle through history directly:** Changes the behavior of the history shortcut (`Control+Shift+H`). When checked, each press cycles to the next history item and copies it automatically. When unchecked, it opens the history management dialog.
* **History retention period:** Automatically deletes history items periodically at the specified time. For example, you can set it to keep items for only 7 days. If you wish to keep your history indefinitely, simply set its value to 0.

## Add-on Shortcuts

### General Shortcuts
| Shortcut | Action |
|---|---|
| `Control+Shift+D` | Get the definition for the selected word in the window. |
| `Control+Shift+T` | Get synonyms for the selected word in the window. |
| `Control+Shift+U` | Get antonyms for the selected word in the window. |
| `Control+Shift+W` | Get the Word of the Day. |
| `Control+Shift+H` | Show or cycle through history, depending on your preferred settings. |
| `Control+Shift+A` | Switch between the three "display/show" output modes. |
| `NVDA+Alt+A` | Open the manual search dialog. |

### Definition Dialog Shortcuts
| Shortcut | Action |
|---|---|
| `Ctrl+P` | Play pronunciation of the original word or the single selected word within the dialog. |
| `Shift+Up/Down Arrow` | Increase or decrease audio playback speed. |
| `Ctrl+Up/Down Arrow` | Increase or decrease audio playback volume. |
| `Escape` | Close the dialog. |

### History Dialog Shortcuts
| Shortcut | Action |
|---|---|
| `Ctrl+C` | Copy the currently focused history item. |
| `Ctrl+Shift+C` | Copy all history items. |
| `Delete` | Remove the currently focused history item. |
| `Shift+Delete` | Clear the entire history. |
| `Escape` | Close the dialog. |

## Important Notes
* **One Dialog at a Time:** You must close any open add-on dialog before opening another to ensure smooth operation. If you try to open more than one dialog at the same time, the add-on will show an error message alerting you that there is an active dialog, and you cannot open any other dialog until the active one is closed first.
* **Double-Press to Copy Mode:** In "Display/Show Dialog" modes, pressing a lookup shortcut twice quickly copies the last result.
* **Internet Connection:** An active internet connection is required for all lookups.

## How It Works: The Technology Inside
The add-on uses specific technologies to provide a seamless experience. This is what each component does for you:

| Technology | Its Benefit to You |
|---|---|
| **requests** | Handles communication with the dictionary API to fetch data for you. |
| **ctypes & comtypes** | Allows the add-on to automatically read the text you have selected in other applications. |
| **wxPython** | Builds the accessible user interface components like dialogs and buttons. |
| **subprocess** | Runs the audio player in a separate process to ensure NVDA remains stable. |
| **threading** | Performs slow tasks in the background so NVDA never freezes while waiting for a result. |

## Contact and Support
* If you encounter any issues, have constructive suggestions to enhance and develop the add-on, or want to contribute to its programming, please open an issue or pull request on [the GitHub repository] (https://github.com/Abdullahashraf32/MW-word-lexicon/tree/MW-word-lexicon/).
* You can email me from [Here](mailto: abdullahashraf4846@gmail.com)
* You can contact me via WhatsApp from [Here](https://wa.me/+201148467527)
* In case you need to contact me via Telegram, you can do it from [Here](https://t.me/abdullahashraf4846)
* You can visit my Youtube channel from [Here](https://www.youtube.com/@AbdullahAshraf-zc5dx)