# Veil

> Instant workspace cleanup. One key. No distractions.

Veil is a lightweight Windows utility that lets you instantly kill the active window with a single hotkey — keeping your workspace clean, focused, and distraction-free.

---

## ✨ Features

- **One-key kill** — Press `F8` to instantly close the foreground window
- **ARMED / SAFE toggle** — Circle indicator in the GUI; arm it when you need focus, disarm when you don't
- **Kill Log** — Every closed window is logged with a timestamp, so you always know what got cleared
- **System Tray** — Runs quietly in the background, out of your way
- **Dark / Light theme** — Switch to whatever your eyes prefer
- **Startup support** — Optionally runs on Windows startup so it's always ready
- **Focus Mode** - After some selected period of time the app is force closed (distraction only)

---

## 📸 Screenshots

> <img width="419" height="625" alt="killlog" src="https://github.com/user-attachments/assets/7d3edba7-1f05-43fe-9cca-583369b5c164" />
<img width="413" height="623" alt="veil" src="https://github.com/user-attachments/assets/c5af0cf9-f61f-47e0-b600-34922ea8c924" />
<img width="423" height="629" alt="veilarmed" src="https://github.com/user-attachments/assets/6cdd4528-ba91-4ef3-9fac-c197fbd6afd0" />


---

## 🚀 Getting Started

### Option 1 — Download the .exe (recommended)

1. Go to [Releases](../../releases)
2. Download `Veil.vbs` and veil.vbs in same folder. 
3. Run it — no install needed

### Option 2 — Run from source

**Requirements:** Python 3.8+

```bash
git clone https://github.com/Xarvyn/veil.git
cd veil
pip install -r requirements.txt
python veil.py
```

---

## 🛠️ Requirements (source only)

```
keyboard
pywin32
tkinter (built-in)
pystray
Pillow
```

Install all:
```bash
pip install keyboard pywin32 pystray Pillow
```

---

## 💡 Use Cases

- Studying and someone walks in — clear the screen instantly
- Gaming on a work PC — one key and it's gone
- Keeping your desktop clean during screen shares
- Building a distraction-free coding environment

---

## ⚠️ Note

Veil force-closes windows without saving. Unsaved work in killed apps **will be lost**. Use the SAFE mode toggle when you're working on something important.

---

## 📄 License

MIT — free to use, modify, and distribute.

---

## 🙌 Contributing

PRs welcome. Open an issue first if it's a big change.

---

*Built by [Xarvyn] aka (https://github.com/arpitthegamedev)*
