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
<p>blackbook runs on your computer. The page you see is served by the small program in the terminal window, nothing is uploaded anywhere. Keep that window open while you work.</p>
<p>At the top right, the <b>round arrow</b> restarts blackbook and the <b>power button</b> stops it. Both work also when there is no terminal window. After a restart the page reloads by itself; after a stop, start blackbook again the same way as before. <b>PID</b> at the top left is the process id of blackbook, for the task manager. When the version at the top left turns red ("restart needed"), click it to restart.</p>
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
    { id: "projects", title: "Projects", html: `<p>The projects on the card are listed on the left; a project with missing samples says how many. Click one to see the number of WAVs in its folder, references, missing samples and unused files, its tracks, sequences and samples.</p><p><b>Tracks</b> look like the Tracks screen of the blackbox: four cards in the track colors with name, type icon and sample count. The order is the one on the device. Click a card to select the track. <b>Config</b> on each card sets the MIDI In and MIDI Out channel.</p><p><b>Sequences:</b> the eight sequence slots of the selected track. For one-shot tracks each row is a pad and each column a step: click an empty cell to add a note, click a note to select it and set velocity, probability, offset and length, click the selected note again to remove it. Name, Step Len, Steps (or Open), Quant and Snap apply to the whole sequence. <b>Play</b> loops the sequence with the pad sounds; the BPM field is for playback here only. Filter, envelope, LFO and effects are heard on the device only. <b>Save to card</b> writes the changes into the project; the autosave copy is not changed. Load the project again on the blackbox afterwards.</p><p><b>Samples:</b> play them, or open one in the audio editor with <b>Edit</b>; saving works as in Patches: as a new file, or over the original with all patches and projects adjusted.</p>${todo}` },
    {
      id: "library", title: "Patches",
      html: `
<p>All patches on the card: the factory patches from 1010music and your own user patches.</p>
<ul>
  <li><b>Search</b> finds patches by name or tag.</li>
  <li><b>Source</b> shows only user patches (the default), only factory patches or all.</li>
  <li><b>Type</b> filters by One-shot, Multisample, Loop, Slicer or Shredder.</li>
  <li><b>Tags</b> on the left: click one or more to show only patches with all of them.</li>
</ul>
<p>Click a patch to see its samples. <b>Play preview</b> plays the patch's <code>preview.wav</code>, the play button next to a sample plays that sample. <code>Esc</code> or the Stop button at the top stops playback.</p>
<p>For your own patches you can change the tags and save them. One-shot and multisample patches can be opened in the builder: <b>Edit in builder</b> changes the patch itself, <b>Use as template</b> starts a new patch from it. Factory patches can only be used as templates.</p><p><b>Edit</b> next to a sample opens the audio editor for the file on the card. <b>Save as new file</b> writes the result next to the original (factory samples go to Samples/Edited). <b>Overwrite original</b> replaces the file and first lists every patch and project that uses it; blackbook moves start, length, loop and slice positions with the edit. Factory samples are never overwritten.</p>`,
    },
    { id: "build", title: "Build", html: `<p>One-shot kits on 16 pads and multisample instruments, new or based on an existing patch.</p>
<h3>One-shot pads</h3>
<p>Click a pad to select and hear it. Drag a pad onto another to move it; a filled pad swaps places. <b>Copy</b>, <b>Paste</b> and <b>Clear</b> work as on the device (Ctrl+C, Ctrl+V, Ctrl+X); Clear keeps the pad in the clipboard, so Paste brings it back. The pad editor below the grid has the same tabs as the pad dashboard on the device:</p>
<ul>
  <li><b>Sound:</b> level, pitch, filter, resonance, pan, overdrive, delay and reverb send.</li>
  <li><b>Setup:</b> reverse, launch (trigger, gate, toggle), polyphony, choke group, interpolation.</li>
  <li><b>Env/LFO:</b> attack, decay, sustain, release, velocity, LFO shape, depth, rate, beat sync and restart.</li>
  <li><b>WAV:</b> start and length of the part of the sample the pad plays.</li>
</ul>
<p>In the <b>WAV</b> tab the waveform shows the part the pad plays: drag the white lines. <b>Edit audio</b> opens the editor: select with the mouse, then trim, delete, silence, fade, reverse, change the gain or normalize. Undo and redo with Ctrl+Z and Ctrl+Shift+Z, Space plays. With <b>Snap to zero</b> every edge lands on a zero crossing, so the sample starts and ends without a click. <b>Use edited sample</b> puts the result on the pad as a new file; the original stays untouched, saving the patch copies the new file into the patch folder.</p>
<p>Clicking a pad plays it with its level, pitch, pan, reverse, start and length. Filter, resonance, overdrive, envelope, LFO, delay and reverb are not reproduced on the computer, you hear them on the device. The Env/LFO tab draws the envelope (times from the device manual, curve shape approximated) and the LFO shape.</p>
<p>The loop switch and the volume slider in the header apply to all playback. In the sample browser every row has a play button; switch off <b>Preview</b> if clicking a row should not play it.</p>
<p>Drag a slider or type a value. A double click on a slider sets the value of a new pad.</p>
${todo}` },
    { id: "backup", title: "Backup", html: `<p>Snapshots of the card in a backup folder, with history, diff and restore.</p><p>Restoring a single WAV brings back only that file. blackbook lists the patches and projects that use it and warns when its length no longer fits; restore the whole patch or project folder to keep everything consistent.</p><p>Only one running blackbook may use a backup folder. If the folder is shared between computers through sync, close blackbook on one computer before you start it on the other.</p><p><b>The backup folder must be outside the blackbook folder.</b> An update or a new installation can delete the blackbook folder, and a backup inside it would be lost. blackbook does not accept such a folder.</p>${todo}` },
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
<p>While the blackbox is in microSD mode, the computer sees the card like a USB stick and the blackbox itself cannot be used. Leave microSD mode to play, switch back to work with blackbook. blackbook notices both and shows the state at the top right: the card icon is green when the card is connected, red when it is not, grey after Eject.</p>
<p>Before you unplug the blackbox or leave microSD mode, click the <b>eject icon</b> (triangle over a line) at the top right. blackbook writes everything to the card and ejects it through the operating system. If another program still uses the card, for example a file manager window that shows a folder on the card, blackbook says so: close it and click Eject again. When you connect the card again, blackbook finds it by itself.</p>
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
