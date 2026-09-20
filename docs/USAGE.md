# PACMANGRAM — Install, use, build

🌐 **English** · [Türkçe](USAGE.tr.md) · [← back to README](../README.md)

Contents: [1. Install (ready-made exe)](#1-install-ready-made-exe) · [2. First start and login](#2-first-start-and-login) · [3. Using each tool](#3-using-each-tool) · [4. Settings, files and uninstall](#4-settings-files-and-uninstall) · [5. Run from source](#5-run-from-source) · [6. Build the exe yourself](#6-build-the-exe-yourself) · [7. Troubleshooting](#7-troubleshooting)

---

## 1. Install (ready-made exe)

There is **nothing to install** and Python is **not** needed.

1. **Click to download:** [**Pacmangram.exe**](https://github.com/R0YC0LD/pacmangram/releases/latest/download/Pacmangram.exe) (about 28 MB). It always points to the newest release; all versions are on the [Releases page](https://github.com/R0YC0LD/pacmangram/releases).
2. Put the file anywhere (Desktop, Documents…) and **double-click it**.
3. *Optional:* compare the file's SHA-256 with `SHA256.txt` on the release page  
   (`Get-FileHash .\Pacmangram.exe -Algorithm SHA256` in PowerShell).

**"Windows protected your PC" (SmartScreen)?** The exe is not code-signed (that costs money), so Windows may warn about an unknown publisher. Click **More info → Run anyway**. You can inspect the whole source in this repository and build the exe yourself (section 6) if you prefer.

Only Windows 10/11 (64-bit) is supported. Only **one copy** can run at a time.

## 2. First start and login

After a short intro (click or press a key to skip) the **Login** page opens. The app starts in your Windows language; change it any time with the **LANGUAGE** box at the bottom left.

**A · Password login** — type username and password (the password is visible while you type; tick *Hide* to mask it). If you have two-step verification, the app asks for the 6-digit code (or SMS / backup code).

**B · Browser session login** — use this if A says *"Your version of Instagram is out of date"*:

1. Log in to **instagram.com** in your normal browser (two-step code included).
2. Press `F12` → tab **Application** (Chrome/Edge) or **Storage** (Firefox) → **Cookies** → `https://www.instagram.com`.
3. Copy the value of `sessionid`, paste it into box **B**, click **Log in with session**.

Tick **Remember the session encrypted on this computer** if you do not want to log in every time. It is encrypted with Windows DPAPI (only your Windows account can open it). Your password is never saved.

After login every page in the left sidebar unlocks. The **Speed profile** box (bottom left) applies to all tools: **Safe** is slowest, **Balanced** is the default, **Fast** is quickest but riskier.

## 3. Using each tool

All cleanup tools work the same way: **scan → check the plan → confirm → the app finishes on its own.** Keep the window open (the PC will not go to sleep). You can press **Stop** at any time.

- **Double-click a row** to protect it (green **Protected ★**); double-click again to undo. Protected rows are never touched and are remembered next time.
- Irreversible actions ask you to **type a confirmation word** (`DELETE` or `REMOVE` in English, `SİL` / `KALDIR` in Turkish).
- If Instagram shows a warning, the app slows down, rests and continues by itself; on a serious warning it stops. Just start again a few hours later — scanning again continues with what is left.

### Select chat / Messages (DM tools)
Pick a chat on **Select chat** (double-click or *Select this chat*). **Messages** loads the conversation. Grey rows belong to the other person and cannot be unsent. Select yours and press **Unsend selected messages** (deleted for everyone), or **Delete entire chat** to remove the chat from your inbox. Type words in *Word(s)* to list only matching messages.

### DM cleanup (automatic)
1. Set **Number of latest chats to keep** (default 20) and, if you like, *Keep pinned chats*.
2. Press **Scan chats and plan**. The list shows *Keep* / *Delete*.
3. Double-click chats you also want to keep.
4. Press **Start automatic cleanup** and type `DELETE`.

Optional: *Also unsend my own messages before deleting* (very slow, but the other person then loses them too). Without it the other person still sees the chat on their side.

### Chat backup
1. Choose a **Backup folder** (default: `Documents\PACMANGRAM\Backups`) and tick what to download: images (default), videos, voice messages.
2. **Load chats**, select the ones you want (Ctrl/Shift click, or *Select all*).
3. **Back up selected.**

You get one folder per person containing `chat.txt` and an `images` folder. Existing files are skipped, so running it again only tops up the backup. This tool only reads; it deletes nothing.

### Story archive
Enter a date (or click *1 month / 6 months / 1 year ago*), press **Scan archive and plan**, protect days you want to keep, then **Delete old stories** and type `DELETE`.

### Blocks
**Scan blocks and plan** lists everyone you blocked. Protect the accounts that must stay blocked, then **Remove blocks** and type `REMOVE`.

### Likes
**Scan likes and plan** lists posts and reels you liked (comment likes are not included). Protect any like to keep, then **Remove likes**.

### Saved
**Scan saved items and plan** lists your saved posts and reels. **Remove saves** removes them from *Saved*; the posts are not deleted.

### Account info
Shows name, user ID, **when the account was created**, its age, country, former usernames, counts, account type, bio, link, and masked e-mail / phone. Press **Refresh** to reload. (Instagram does not provide the creation date for every account.)

## 4. Settings, files and uninstall

| What | Where |
|---|---|
| Settings, protected lists, saved session, log | `%LOCALAPPDATA%\IGDMTool\` (paste it into the Explorer address bar) |
| Log file | `%LOCALAPPDATA%\IGDMTool\igdmtool.log` (or the *Open log file* link in the app) |
| Chat backups | the folder you chose (default `Documents\PACMANGRAM\Backups`) |

**Uninstall:** use **Log out and delete session** in the app (removes the saved login), delete `Pacmangram.exe`, and optionally delete the `%LOCALAPPDATA%\IGDMTool` folder. Nothing is written to the registry.

## 5. Run from source

Needs Windows, [Python 3.12](https://www.python.org/downloads/) (tick *Add python.exe to PATH*) and Git.

```powershell
git clone https://github.com/R0YC0LD/pacmangram.git
cd pacmangram
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python src\igdm_launcher.py
```

## 6. Build the exe yourself

```powershell
git clone https://github.com/R0YC0LD/pacmangram.git
cd pacmangram
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

The script creates `.venv`, installs the dependencies, redraws the icon, **runs the 231 tests**, and builds a single-file, no-console exe with PyInstaller. Result: `dist\Pacmangram.exe` plus `dist\SHA256.txt` (about 28 MB; the first build takes a few minutes). Use `-SkipTests` to skip the tests.

Only the tests: `.\.venv\Scripts\python tests\run_all.py` (they use a fake client and never contact Instagram).

## 7. Troubleshooting

| Problem | What to do |
|---|---|
| *"Your version of Instagram is out of date"* on password login | Use **B · Browser session login** (section 2). |
| *"Instagram asks for extra verification"* | Approve *"This was me"* in the Instagram app, then try again. |
| Session expired | **Log out and delete session**, then log in again. |
| Instagram warning / rate limit | The app rests by itself. If it stopped, wait a few hours and scan again. Use **Safe** speed for long lists. |
| "The app is already running" | Only one copy can run. Close the other one (check Task Manager). |
| Antivirus flags the exe | Unsigned PyInstaller exes are sometimes flagged by mistake. Compare the SHA-256, or build it yourself (section 6). |
| Something else | Open the log (`%LOCALAPPDATA%\IGDMTool\igdmtool.log`) and create an [issue](https://github.com/R0YC0LD/pacmangram/issues) — **remove usernames and never post your `sessionid`**. |
