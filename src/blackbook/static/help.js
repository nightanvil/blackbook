/*
 * blackbook - built-in help, shown in the help overlay (index left, text right).
 * Each section: { id, title, html }. The HTML is static text written for this file.
 * Browser: window.BlackbookHelp.
 */
(function (root) {
  "use strict";

  const todo = '<p class="placeholder">This section is still being written.</p>';

  const repo = "https://github.com/nightanvil/blackbook";
  const kofi = "https://ko-fi.com/nightanvil";

  const sections = [
    {
      id: "start", title: "Getting started",
      html: `
<p class="note"><b>This is a very, very, very early version.</b> Expect rough edges and missing pieces. Please try it, and tell me what you would like blackbook to do: every idea and every bug report helps. <a href="${repo}/issues" target="_blank" rel="noopener noreferrer">Ideas and feedback</a></p>
<p><b>blackbook</b> organizes the microSD card of the 1010music <b>blackbox 2</b>: browse and tag patches, build one-shot and multisample patches, edit your own patches and keep a versioned backup of the card.</p>
<p>blackbook runs on your computer. The page you see is served by the small program in the terminal window, nothing is uploaded anywhere. Keep that window open while you work, close it to stop blackbook.</p>
<h3>What you need</h3>
<ul>
  <li>The blackbox 2 connected over USB and switched to <b>microSD mode</b>, or its card in a card reader. blackbook finds the card by itself.</li>
  <li>For the backup: <b>git</b>. The start script takes care of it, see "What is git".</li>
</ul>
<h3>Before the first save</h3>
<p>On the first start a welcome window offers to set up the backup: <b>Set up backup</b> uses <code>blackbook-backup</code> in your documents folder, <b>Choose folder</b> lets you pick another place. The first snapshot copies the whole card and can take several minutes. From then on blackbook saves a snapshot before and after every write, and every time the card is connected. If you skip it, a bar at the top reminds you.</p>
<h3>Updates</h3>
<p>When blackbook starts, it checks GitHub for a newer version. If there is one, a bar at the top offers <b>Update now</b>. After the update blackbook stops, start it again as usual. Settings, backup and card stay untouched.</p>
${todo}`,
    },
    { id: "library", title: "Library", html: `<p>Factory and user patches with their tags and samples.</p>${todo}` },
    { id: "build", title: "Build", html: `<p>One-shot kits on 16 pads and multisample instruments, new or based on an existing patch.</p>${todo}` },
    { id: "projects", title: "Projects", html: `<p>The projects on the card.</p>${todo}` },
    { id: "backup", title: "Backup", html: `<p>Snapshots of the card in a backup folder, with history, diff and restore.</p>${todo}` },
    {
      id: "git", title: "What is git",
      html: `
<p>git is a free program that keeps every version of a set of files. blackbook uses it as a <b>time machine for your card</b>:</p>
<ul>
  <li>A <b>snapshot</b> stores the state of the card at one moment: when you connect the card, before blackbook writes and after it has written.</li>
  <li>In <b>Backup</b> you see all snapshots and what changed, and you can bring back a file, a folder or the whole card.</li>
  <li>Unchanged files are stored only once. The snapshots stay in a folder on your computer, nothing is uploaded.</li>
</ul>
<p>You never use git yourself. On Windows blackbook brings its own copy, on macOS and Linux the start script offers to install it. <b>Without git</b> blackbook works the same, only Backup is switched off. Then copy the whole card to your computer yourself before you write to it.</p>
<h3>Install git yourself</h3>
<ul>
  <li><b>Windows:</b> in PowerShell <code>winget install --id Git.Git -e --source winget</code>, or the installer from <a href="https://git-scm.com/downloads/win" target="_blank" rel="noopener noreferrer">git-scm.com</a> (click Next on every page).</li>
  <li><b>macOS:</b> in Terminal <code>xcode-select --install</code>.</li>
  <li><b>Linux:</b> <code>sudo apt install git</code> (Ubuntu, Debian, Mint), <code>sudo dnf install git</code> (Fedora), <code>sudo pacman -S git</code> (Arch, CachyOS), <code>sudo zypper install git</code> (openSUSE).</li>
</ul>
<p>Then close blackbook (the terminal window) and start it again.</p>`,
    },
    {
      id: "card", title: "Card and microSD mode",
      html: `
<p>While the blackbox is in microSD mode, the computer sees the card like a USB stick and the blackbox itself cannot be used. Leave microSD mode to play, switch back to work with blackbook. blackbook notices both and shows the state at the top right.</p>
<p>Before you unplug the blackbox or leave microSD mode, wait until blackbook has finished writing (the message at the bottom has disappeared).</p>
${todo}`,
    },
    {
      id: "about", title: "About",
      html: `
<p>blackbook is an unofficial hobby project, <b>not affiliated with 1010music</b>. The card format was worked out by looking at the files the blackbox writes. A firmware update can change it. Use blackbook at your own risk and keep backups of your card.</p>
<p>blackbook was built together with Claude (Anthropic) as a coding assistant.</p>
<p>1010music and blackbox are trademarks of 1010music LLC, used here only to describe compatibility.</p>
<p>License: MIT, without any warranty. Source code: <a href="${repo}" target="_blank" rel="noopener noreferrer">GitHub</a>.</p>`,
    },
    {
      id: "support", title: "Feedback and support",
      html: `
<p>Questions, ideas, bug reports: <a href="${repo}/issues" target="_blank" rel="noopener noreferrer">GitHub Issues</a>. Please describe what you did, what you expected and what happened instead, and which system you use (Linux, Windows, macOS).</p>
<p>blackbook is free and stays free. If it helps you, you can buy me a coffee on <a href="${kofi}" target="_blank" rel="noopener noreferrer">Ko-fi</a>.</p>`,
    },
  ];

  root.BlackbookHelp = { sections };
})(window);
