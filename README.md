# <img src="src/blackbook/static/icon.svg" alt="" width="40" align="top"> blackbook

**blackbook** is an unofficial organizer for the microSD card of the **1010music blackbox 2**. It runs on your computer and opens in your web browser. Nothing is uploaded anywhere.

> [!IMPORTANT]
> **This is a very, very, very early version.** Expect rough edges and missing pieces. It is shared now so you can try it and tell me what you need. Every idea and every bug report helps: [Ideas and feedback](https://github.com/nightanvil/blackbook/issues).

blackbook is free and stays free. If it helps you, you can buy me a coffee on [Ko-fi](https://ko-fi.com/nightanvil).

## What it does

- **Library:** all factory and user patches with type and tag filter. Listen to samples and previews.
- **Tags:** tag your own patches, as on the device.
- **Build:** one-shot kits on 16 pads and multisample instruments, by drag and drop. Key and velocity ranges are read from the file names.
- **Edit:** change your own patches in place. Sequences, modulation and everything blackbook does not know stay untouched.
- **Templates:** any one-shot or multisample patch, also factory patches, as a starting point for a new one.
- **Projects:** missing samples and unused files per project.
- **Backup:** snapshots of the card with history, comparison and restore. Automatic when the card is connected, and before and after blackbook writes.

Planned: loop, slicer and shredder patches, an external audio editor, renaming with all references kept intact. Tell me what you need most.

## Installation and start

You do this once. blackbook sets itself up inside its own folder and changes nothing else on your computer. The first start needs internet and takes a few minutes, later starts take seconds.

### What blackbook needs

| | Needed? | Why |
|---|---|---|
| **Python** | **No**, you do not have to install it | blackbook is written in Python. If your computer has no Python, the start script downloads a private copy into the blackbook folder. Nothing is installed system-wide. |
| **git** | **Recommended**, mostly automatic | For the backup of your card, see [What is git?](#what-is-git). **Windows:** the start script downloads the official portable git into the blackbook folder, nothing to do. **macOS:** Apple's install window opens by itself, click **Install**. **Linux:** the start script offers to install it and asks for your password. Without git blackbook works, only the backup is switched off. |

<details>
<summary>I want to install Python myself anyway</summary>

Not needed, but possible. blackbook then uses your Python only for the setup and still keeps its own copy in its folder.

- Windows: `winget install --id Python.Python.3.13 -e --source winget`, or the installer from <https://www.python.org/downloads/> (always the current version). In the installer tick **Add python.exe to PATH**.
- macOS: comes with `xcode-select --install` (see git below).
- Linux: package `python3` (Ubuntu, Debian, Fedora, openSUSE) or `python` (Arch, CachyOS).

</details>

### 1. Download

On the [GitHub page](https://github.com/nightanvil/blackbook) click the green **Code** button, then **Download ZIP**. Unpack the ZIP into a folder of your choice, for example your home folder or `Documents`. Do not put it on the blackbox card.

### 2. git (usually nothing to do)

The start script takes care of git, see the table above. Install it yourself only if that did not work, or if you prefer to do it before. You can add git later at any time.

<details>
<summary><b>Windows</b></summary>

Either with the command line tool `winget`, which is part of Windows 10 and 11:

1. Open the Start menu, type `PowerShell` and open it.
2. Copy this line into the window and press Enter:

   ```powershell
   winget install --id Git.Git -e --source winget
   ```

Or with the installer: download it from <https://git-scm.com/downloads/win> (always the current version), run it and click **Next** on every page. The default settings are fine.

</details>

<details>
<summary><b>macOS</b></summary>

1. Open the app **Terminal** (Finder, Applications, Utilities).
2. Type this and press Enter, then click **Install** in the dialog:

   ```bash
   xcode-select --install
   ```

This installs Apple's command line tools, which include git and Python. If you use Homebrew, `brew install git` works as well.

</details>

<details>
<summary><b>Linux</b></summary>

Most distributions have git already. Check in a terminal:

```bash
git --version
```

If it says "command not found", install it with the command for your distribution:

| Distribution | Command |
|---|---|
| Ubuntu, Debian, Linux Mint, Pop!_OS | `sudo apt install git` |
| Fedora | `sudo dnf install git` |
| Arch, Manjaro, EndeavourOS, CachyOS | `sudo pacman -S git` |
| openSUSE | `sudo zypper install git` |

`sudo` asks for your password. While you type it, nothing is shown, that is normal.

</details>

### 3. Start

**Linux** (tested)

1. Open the blackbook folder in your file manager.
2. Right-click on an empty spot in the folder and choose **Open in Terminal** (the wording differs between file managers).
3. Type the following and press Enter:

   ```bash
   bash start.sh
   ```

**Windows** (not tested yet)

1. Open the blackbook folder and double-click **`start.bat`**.
2. If Windows shows "Windows protected your PC", click **More info**, then **Run anyway**. This appears because blackbook is not signed by a company.

**macOS** (not tested yet)

1. In the Finder, right-click **`start.command`**, choose **Open** and confirm. Later a double-click is enough.

### 4. Connect the blackbox

Connect the blackbox 2 over USB and switch it to **microSD mode** (or put its card into a card reader). blackbook finds the card by itself and opens in your browser at <http://127.0.0.1:8765/>.

A window with text (the terminal) stays open while blackbook runs. **Keep it open** while you work. To stop blackbook, close that window (or press `Ctrl+C` in it).

### Starting again later

Do the same as in step 3. If git was installed after blackbook was started, close blackbook and start it again, then git is found.

## What is git?

git is a free program that keeps every version of a set of files. Programmers use it so they can always go back to an earlier state of their work.

blackbook uses git as a **time machine for your card**:

- A **snapshot** stores the state of the card at one moment. blackbook takes one when you connect the card, before it writes to the card and after it has written.
- In the **Backup** tab you see all snapshots, what changed between them, and you can bring back a single file, a folder or the whole card as it was.
- Files that did not change are stored only once, so many snapshots need little extra space.
- The snapshots are kept in a folder on your computer that you choose. Nothing is uploaded anywhere.

You never have to use git yourself, blackbook does everything in the background, including setting up the backup folder.

**Without git** blackbook works the same, only the Backup tab is switched off, and every save shows a reminder. Then please copy the whole card to your computer yourself before you write to it.

## First steps

1. **Set up the backup.** When the card is connected for the first time, a bar at the top offers it: click **Set up backup**. blackbook creates the folder `blackbook-backup` in your documents folder and takes the first snapshot. From then on it takes snapshots by itself. With **Other folder** you choose a different place (not on the card). Without git: copy the whole card to your computer yourself.
2. Look around in **Library**. Nothing is written to the card unless you click **Write to card**.
3. Every write shows a review first: what is copied, what changes.

The built-in help (**?** at the top right, or `F1`) explains more.

## Tested systems

| System | Status |
|---|---|
| Linux | tested |
| Windows | should work, not tested yet |
| macOS | should work, not tested yet |

Feedback from Windows and macOS users is very welcome.

## Feedback

Please use [GitHub Issues](https://github.com/nightanvil/blackbook/issues) for ideas and bug reports. Helpful in a bug report: what you did, what you expected, what happened instead, and your system.

## Use at your own risk

> [!WARNING]
> blackbook is a hobby project and **not affiliated with 1010music**. The card format was worked out by looking at the files the blackbox writes, and a firmware update can change it. blackbook writes to your card, so keep backups. Factory patches are never changed.

1010music and blackbox are trademarks of 1010music LLC, used here only to describe compatibility. No 1010music content is part of this repository.

## How it was made

blackbook was built together with Claude (Anthropic) as a coding assistant, credited as co-author in the commits. Technical details, command line options and the code layout: [docs/development.md](docs/development.md). Card format: [docs/card-format.md](docs/card-format.md).

## License

[MIT](LICENSE), without any warranty.

## Authors

- Gabriel Köhl ([@gabrielkoehl](https://github.com/gabrielkoehl))
- Claude (Anthropic), AI coding assistant, co-author
