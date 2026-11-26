/*
 * blackbook - built-in help, shown in the help overlay (index left, text right).
 * Each section: { id, title, html }. The HTML is static text written for this file.
 * Browser: window.BlackbookHelp.
 */
(function (root) {
  "use strict";

  const todo = '<p class="placeholder">This section is still being written.</p>';

  const sections = [
    {
      id: "start", title: "Getting started",
      html: `
<p><b>blackbook</b> organizes the microSD card of the 1010music <b>blackbox 2</b>: browse and tag patches, build one-shot and multisample patches, edit your own patches and keep a versioned backup of the card.</p>
<h3>What you need</h3>
<ul>
  <li>The blackbox in <b>microSD mode</b>, connected over USB, or the card in a card reader.</li>
  <li>blackbook running on this computer. It only reads and writes the card and the backup folder.</li>
</ul>
${todo}`,
    },
    { id: "library", title: "Library", html: `<p>Factory and user patches with their tags and samples.</p>${todo}` },
    { id: "build", title: "Build", html: `<p>One-shot kits on 16 pads and multisample instruments, new or based on an existing patch.</p>${todo}` },
    { id: "projects", title: "Projects", html: `<p>The projects on the card.</p>${todo}` },
    { id: "backup", title: "Backup", html: `<p>Snapshots of the card in a backup folder, with history, diff and restore.</p>${todo}` },
    { id: "card", title: "Card and microSD mode", html: todo },
    {
      id: "support", title: "Feedback and support",
      html: `<p>blackbook is free. If it helps you, you can support it on <a href="https://ko-fi.com/nightanvil" target="_blank" rel="noopener noreferrer">Ko-fi</a>.</p>`,
    },
  ];

  root.BlackbookHelp = { sections };
})(window);
