// Fills in the support email (set with CONTACT_EMAIL on the server) on the legal pages.
fetch("/api/config")
  .then((r) => r.json())
  .then((c) => {
    if (!c.contact_email) return;
    document.querySelectorAll(".contact").forEach((el) => {
      const a = document.createElement("a");
      a.href = `mailto:${c.contact_email}`;
      a.textContent = c.contact_email;
      el.replaceWith(a);
    });
  })
  .catch(() => {});
