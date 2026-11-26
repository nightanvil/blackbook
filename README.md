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

### 1. Download

On the [GitHub page](https://github.com/nightanvil/blackbook) click the green **Code** button, then **Download ZIP**. Unpack the ZIP into a folder of your choice, for example your home folder or `Documents`. Do not put it on the blackbox card.

### 2. Start

**Linux** (tested)

1. Install `git` and `python3` if they are missing. On most systems they are already there. Otherwise, for example on Ubuntu: `sudo apt install git python3`, on Arch and CachyOS: `sudo pacman -S git python`.
2. Open the blackbook folder in your file manager. Right-click on an empty spot and choose **Open in Terminal** (or similar).
3. Type the following and press Enter:

   ```bash
   bash start.sh
   ```

**Windows** (not tested yet)

1. Install [Git for Windows](https://git-scm.com/download/win) with the default settings. blackbook needs it for the backup.
2. Open the blackbook folder and double-click **`start.bat`**. If Windows warns about an unknown app, click **More info**, then **Run anyway**.

Python is not needed: if it is missing, `start.bat` downloads a private copy into the blackbook folder.

**macOS** (not tested yet)

1. Open the Terminal app once and run `xcode-select --install` (installs git), if you have never done this.
2. In the Finder, right-click **`start.command`**, choose **Open** and confirm. Later a double-click is enough.

### 3. Connect the blackbox

Connect the blackbox 2 over USB and switch it to **microSD mode** (or put its card into a card reader). blackbook finds the card by itself and opens in your browser at <http://127.0.0.1:8765/>.

A terminal window stays open while blackbook runs. **Keep it open** while you work. To stop blackbook, close that window (or press `Ctrl+C` in it).

## First steps

1. **Make a backup first.** Open **Backup**, choose a folder on your computer (not on the card) and click **Snapshot now**. From then on blackbook takes snapshots by itself.
2. Look around in **Library**. Nothing is written to the card unless you click **Write to card**.
3. Every write shows a review first: what is copied, what changes.

The built-in help (**?** at the top right, or `F1`) explains more.

## Microsoft, Apple, Linux: what is tested

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
