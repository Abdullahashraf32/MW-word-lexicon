# MW Word Lexicon: Add-on User Guide

## Introduction

The MW Word Lexicon add-on is a powerful tool designed to integrate a comprehensive dictionary and thesaurus directly into NVDA. Its main goal is to allow you to look up word definitions, synonyms, and antonyms instantly from any application without interrupting your work and having to open a dedicated page in your web browser to access different dictionaries.

This add-on uses the **Merriam-Webster Dictionary API** because it offers a generous free plan of **1,000 requests per day**. This ensures the add-on can remain free and reliable for all users. As a non-profit project, using a service that does not require payment was a key consideration during the add-on's design phases.

## v1.3: What's New

This update introduces important stability fixes and improvements that make the add-on more reliable and easier to use.

### 1\. New Layer-Based Shortcut System

Instead of using many global shortcuts that may conflict with other programs, version 1.3 introduces a cleaner and safer shortcut system.
Now, you only need to press `Control+Shift+D` to enter the add-on’s **main layer**.
After entering this layer, you simply press a single letter (such as `a`, `d`, `t`, etc.) to perform the desired action.
This design keeps your keyboard clean, avoids shortcut conflicts, and makes the add-on easier to remember and use.

### 2\. Reliable Playback and Instant Pronunciation

The Play button in the "Definition Dialog" has been fully fixed and now appears consistently, ensuring dependable playback. To further enhance stability and streamline your workflow, you can now listen to the pronunciation of the word under your cursor immediately—without needing to open the dialog at all—simply by pressing `P` inside the main layer. Note that this direct playback automatically uses the same speed and volume settings currently configured within the Definition Dialog.

### 3\. Smart Word Detection and Improved Accuracy

Text interaction is now faster and more intuitive. You are no longer required to manually highlight a word to look it up. Simply place your cursor on the desired word, and the add-on will automatically detect it when you request a definition, pronunciation, synonyms, or antonyms. Furthermore, detection accuracy has been significantly improved across various applications, including Notepad and WordPad, resolving previous issues with bulleted lists and incomplete word capture.

### 4\. Comprehensive Sound Scheme

The add-on introduces a comprehensive sound scheme to enhance interaction. While general sound effects—such as those for search results and dialog navigation—can be toggled on or off in the Settings, the specific sounds for opening and closing the command layer are designed to function independently. This ensures you always receive audible confirmation of the layer's status, regardless of your general sound preferences.

## Key Features

- **Instant Lookups:** Get definitions, synonyms, and antonyms for any selected word.
- **Word of the Day:** Discover a new word daily to expand your vocabulary.
- **Flexible Output Modes:** Choose how you receive results: auto-copy to the clipboard while speaking the definition, speak-only (requiring a double press to copy), or a detailed interactive dialog.
- **Interactive Dialogs:** Fully accessible dialogs for definitions, search, and history, complete with keyboard navigation and unique features.
- **Comprehensive History:** The add-on keeps a record of your recent lookups for easy review and management.

## Understanding the Interactive Dialogs

The add-on includes three main dialogs, each designed for a specific purpose to enhance your workflow.

### The Definition Dialog

This dialog appears when you are in "Copy and Show Dialog" mode and provides a rich environment for exploring word definitions. It's more than just a text viewer; it's a learning tool.

- **Pronunciation Playback:** You can listen to the pronunciation of the word you looked up by pressing `Ctrl+P`. More importantly, you can select any **single word** within the results area and press `Ctrl+P` to listen to its pronunciation.
- **Why a single word only?** This feature is intentionally designed to help you learn the correct pronunciation of new words you encounter, especially the synonyms and antonyms that appear in search results. If you try to select more than one word, the action will fail, and you will receive an error message, as the goal is precise, single-word pronunciation.
- **Persistent Audio Controls:** The dialog includes sliders for adjusting playback **Speed** and **Volume**. The add-on remembers your settings. When you adjust the sliders to your preferred levels, these values are saved. The next time you open NVDA, the sliders will be at the same levels you left them, providing a consistent experience.

### The History Dialog

This dialog acts as your personal log of looked-up words. It allows you to review, reuse, and manage your search history efficiently.

- **Central Control via Context Menu:** Your history is displayed in a simple list. The primary way to interact with it is to focus on the history item you need within the list and press the **Applications key** to open a context menu. This menu gives you full control, with options to "Copy the currently focused item," "Remove the currently focused item," "Copy all history items," and "Clear all history items."
- **Keyboard Shortcuts as a Seamless and Quick Access Method:** For users who prefer the keyboard, shortcuts like `Ctrl+C` to copy the history focused item and `Delete` to remove the current history focused item are provided. These shortcuts are time-saving alternatives that perform the same actions found in the context menu.

### The Manual Search Dialog

You can open this dialog by entering the main layer (`Ctrl+Shift+D`) and then pressing `S`. This is ideal for words you want to type and search for manually. Once you type the word you are looking for and press the **Enter** key, the search begins. As soon as the search is complete and the word is found, the focus automatically moves to the results area. If sound effects are enabled, this will be accompanied by a success sound indicating that the word is found.

- **Flexible Search Types:** It contains a combo box that allows you to specify what you are looking for: a **definition**, **synonyms**, or **antonyms**.
- **Smart Auto-Search:** This dialog has a convenient, time-saving feature. If you select text in the current open window before pressing `S` after opening the add-on's main layer, the dialog will automatically perform a search for that text the moment it opens. It then intelligently moves the focus directly to the results area, allowing you to start reading the information immediately without any extra steps.

## Settings and Customization

To customize the add-on, go to the NVDA menu, then **Preferences -\> Settings -\> MW Word Lexicon** category.

- **Enable Sound Effects:** Toggles the add-on's sound feedback (audible cues for layer operations, dialog interactions, and errors) on or off according to your preference.
- **History size:** Sets the maximum number of lookups you want to store in the history.
- **Cycle through history directly:** Changes the behavior of the history shortcut within the add-on's main layer (`H`). When checked, each press cycles to the next history item and copies it automatically. When unchecked, it opens the history management dialog.
- **History retention period:** Automatically deletes history items periodically at the specified time. For example, you can set it to keep items for only 7 days. If you wish to keep your history indefinitely, simply set its value to 0.

## Add-on Shortcuts

### General Shortcuts

To use the add-on general shortcuts, you must first press `Control+Shift+D` to enter the add-on’s main layer. While you are inside this layer, press a single letter to perform an action such as getting a definition, showing synonyms, getting the Word of the Day, cycling history, and more. This system reduces shortcut conflicts with other applications and keeps the keyboard layout simple and organized.

To ensure a fluid workflow, the add-on's main layer is designed to stay open during repetitive tasks. To demonstrate, when you press `A` to cycle through output modes, the layer remains active for **1.5 seconds**, allowing you to switch modes rapidly without re-entering the layer. Similarly, if "Cycle through history" option is enabled, pressing `H` keeps the layer open for **2 seconds**, enabling you to browse and copy your history items quickly in succession.

| Shortcut          | Action                                                                                                   |
| :---------------- | :------------------------------------------------------------------------------------------------------- |
| `control+shift+D` | Enter the add-on’s main layer which manages you to perform the complete add-on's general shortcuts list. |
| `D`               | Get the definition for the selected word in the window.                                                  |
| `T`               | Get synonyms for the selected word in the window.                                                        |
| `U`               | Get antonyms for the selected word in the window.                                                        |
| `W`               | Get the Word of the Day.                                                                                 |
| `P`               | Listen to the pronunciation of the word that is under your cursor directly.                              |
| `H`               | Show or cycle through history, depending on your preferred settings.                                     |
| `A`               | Switch between the three display output modes.                                                           |
| `S`               | Open the manual search dialog.                                                                           |
| `F1`              | Open the Add-on's User Guide in your browser.                                                            |

### Definition Dialog Shortcuts

| Shortcut              | Action                                                                                            |
| :-------------------- | :------------------------------------------------------------------------------------------------ |
| `Ctrl+P`              | Play pronunciation of the original word or the single selected word within the definition dialog. |
| `Shift+Up/Down Arrow` | Increase or decrease audio playback speed.                                                        |
| `Ctrl+Up/Down Arrow`  | Increase or decrease audio playback volume.                                                       |
| `Escape`              | Close the dialog.                                                                                 |

### History Dialog Shortcuts

| Shortcut       | Action                                     |
| :------------- | :----------------------------------------- |
| `Ctrl+C`       | Copy the currently focused history item.   |
| `Alt+Shift+C`  | Copy all history items.                    |
| `Delete`       | Remove the currently focused history item. |
| `Shift+Delete` | Clear the entire history.                  |
| `Escape`       | Close the dialog.                          |

## Important Notes

- **One Dialog at a Time:** You must close any open add-on dialog before opening another to ensure smooth operation. If you attempt to open a new dialog while one is already active, NVDA will announce a warning message. Additionally, if sound effects option is enabled in the settings, a distinct error sound will accompany this warning, alerting you that the current dialog must be closed first.
- **Double-Press Mode Logic:** When this mode is active, the layer remains open briefly after you request a definition, synonym, or antonym. This deliberate pause gives you a sufficient window to press the shortcut key a second time, triggering the "Smart Copy" feature to save the result to your clipboard immediately.
- **Internet Connection:** An active internet connection is required for all lookups.

## How It Works: The Technology Inside

The add-on uses specific technologies to provide a seamless experience. This is what each component does for you:

| Technology            | Its Benefit to You                                                                        |
| :-------------------- | :---------------------------------------------------------------------------------------- |
| **requests**          | Handles communication with the dictionary API to fetch data for you.                      |
| **ctypes & comtypes** | Allows the add-on to automatically read the text you have selected in other applications. |
| **wxPython**          | Builds the accessible user interface components like dialogs and buttons.                 |
| **subprocess**        | Runs the audio player in a separate process to ensure NVDA remains stable.                |
| **threading**         | Performs slow tasks in the background so NVDA never freezes while waiting for a result.   |

## Contact and Support

- If you encounter any issues, have constructive suggestions to enhance and develop the add-on, or want to contribute to its programming, please open an issue or pull request on the [GitHub repository](https://github.com/Abdullahashraf32/MW-word-lexicon/tree/MW-word-lexicon/).
- You can email me from [Here](mailto: abdullahashraf4846@gmail.com)
- You can contact me via WhatsApp from [Here](https://wa.me/+201148467527)
- In case you need to contact me via Telegram, you can do it from [Here](https://t.me/abdullahashraf4846)
- You can visit my Youtube channel from [Here](https://www.youtube.com/@AbdullahAshraf-zc5dx)
- You can watch the full video tutorial explaining how to use the MW Word Lexicon add-on in Arabic from [Here](https://youtu.be/tCNyqbxFJzY)
