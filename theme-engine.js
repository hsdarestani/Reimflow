
(() => {
  const themes = {
    "sonic-art": { label: "Pop Comic", color: "#FF603D", comic: "pop" },
    "comic-graffiti": { label: "Street Graffiti", color: "#C5FA38", comic: "graffiti" },
    "comic-novel": { label: "Graphic Novel", color: "#E34948", comic: "novel" },
    "comic-clean": { label: "Clean Comic", color: "#EE7358", comic: "clean" },
    playful: { label: "Playful", color: "#8B5CF6" },
    linear: { label: "Linear", color: "#5E6AD2" },
    "minimal-dark": { label: "Minimal Dark", color: "#F59E0B" },
    vaporwave: { label: "Vaporwave", color: "#FF00FF" },
    "art-deco": { label: "Art Deco", color: "#D4AF37" }
  };

  const root = document.documentElement;
  const switcher = document.querySelector(".theme-switcher");
  const toggle = document.getElementById("themeToggle");
  const menu = document.getElementById("themeMenu");
  const currentLabel = document.querySelector(".theme-current");
  const themeMeta = document.querySelector('meta[name="theme-color"]');

  function setTheme(name, persist = true) {
    if (!themes[name]) name = "sonic-art";
    root.dataset.theme = themes[name].comic ? "sonic-art" : name;
    if (themes[name].comic) root.dataset.comicStyle = themes[name].comic;
    else delete root.dataset.comicStyle;
    if (persist) localStorage.setItem("reimflow_theme_v3", name);
    if (currentLabel) currentLabel.textContent = themes[name].label;
    if (themeMeta) themeMeta.setAttribute("content", themes[name].color);
    document.querySelectorAll("[data-theme-pick]").forEach((button) => {
      const active = button.dataset.themePick === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.querySelectorAll("[data-theme-option]").forEach((button) => {
      const active = button.dataset.themeOption === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-checked", String(active));
    });
    window.dispatchEvent(new CustomEvent("reimflow:themechange", { detail: { theme: name, comicStyle: themes[name].comic || null } }));
  }

  const stored = localStorage.getItem("reimflow_theme_v3");
  setTheme(themes[stored] ? stored : (root.dataset.theme || "sonic-art"), false);

  toggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = !switcher.classList.contains("open");
    switcher.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  });

  document.querySelectorAll("[data-theme-pick]").forEach(button => {
    button.addEventListener("click", () => setTheme(button.dataset.themePick));
  });

  menu?.addEventListener("click", (event) => {
    const option = event.target.closest("[data-theme-option]");
    if (!option) return;
    setTheme(option.dataset.themeOption);
    switcher.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  });

  document.addEventListener("click", (event) => {
    if (switcher && !switcher.contains(event.target)) {
      switcher.classList.remove("open");
      toggle?.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      switcher?.classList.remove("open");
      toggle?.setAttribute("aria-expanded", "false");
    }
  });

  // Linear's ambient pointer lighting and card spotlights.
  window.addEventListener("pointermove", (event) => {
    root.style.setProperty("--pointer-x", event.clientX + "px");
    root.style.setProperty("--pointer-y", event.clientY + "px");
  }, { passive: true });

  document.addEventListener("pointermove", (event) => {
    if (root.dataset.theme !== "linear") return;
    const card = event.target.closest(".sticker-card");
    if (!card) return;
    const rect = card.getBoundingClientRect();
    card.style.setProperty("--spot-x", (event.clientX - rect.left) + "px");
    card.style.setProperty("--spot-y", (event.clientY - rect.top) + "px");
  }, { passive: true });

  // Restrained scroll-linked hero depth. CSS only consumes these values in Linear.
  let ticking = false;
  window.addEventListener("scroll", () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const y = Math.min(window.scrollY, 520);
      root.style.setProperty("--hero-shift", y + "px");
      root.style.setProperty("--hero-scale", String(1 - (y / 520) * 0.045));
      root.style.setProperty("--hero-opacity", String(Math.max(.3, 1 - (y / 520) * .72)));
      ticking = false;
    });
  }, { passive: true });
})();
