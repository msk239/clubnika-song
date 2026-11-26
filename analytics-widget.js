(function () {
  function fmt(n) {
    return Number(n || 0).toLocaleString("ru-RU");
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderRows(videos, sortBy) {
    const sorted = [...videos].sort((a, b) => {
      const av = Number(a[sortBy] || 0);
      const bv = Number(b[sortBy] || 0);
      if (bv !== av) return bv - av;
      return Number(b.views || 0) - Number(a.views || 0);
    });

    return sorted.map((v, i) => {
      const badge = v.type === "shorts" ? "Shorts" : "Видео";
      const badgeBg = v.type === "shorts"
        ? "rgba(225, 29, 72, 0.18); color: #fda4af; border: 1px solid rgba(225, 29, 72, 0.35);"
        : "rgba(234, 179, 8, 0.16); color: #fde047; border: 1px solid rgba(234, 179, 8, 0.32);";
      return `
        <a href="${escapeHtml(v.url)}" target="_blank" rel="noopener"
           style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;background:rgba(255,255,255,0.03);text-decoration:none;color:inherit;border:1px solid rgba(255,255,255,0.05);">
          <div style="min-width:0;flex:1;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <span style="font-size:12px;opacity:.65;">#${i + 1}</span>
              <span style="font-size:11px;padding:2px 7px;border-radius:999px;${badgeBg}">${badge}</span>
            </div>
            <div style="font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
              ${escapeHtml(v.title || v.id)}
            </div>
          </div>
          <div style="text-align:right;white-space:nowrap;font-size:12px;line-height:1.45;">
            <div>👁 ${fmt(v.views)}</div>
            <div style="opacity:.8;">❤️ ${fmt(v.likes)}</div>
          </div>
        </a>
      `;
    }).join("");
  }

  function buildAnalyticsCardHtml(s, videos, idxPrefix) {
    const titleText = s.channel || s.name || "Канал";
    const handleText = s.handle ? ` <span style="font-size:12px;font-weight:400;opacity:.65;">${escapeHtml(s.handle)}</span>` : "";
    const channelUrl = s.channel_url || "https://www.youtube.com";
    const avatarHtml = s.avatar_url
      ? `<img src="${escapeHtml(s.avatar_url)}" alt="${escapeHtml(titleText)}" onerror="this.style.display='none'" style="width:34px;height:34px;border-radius:999px;object-fit:cover;flex-shrink:0;border:1px solid rgba(255,255,255,0.16);">`
      : "";

    const listId = `analytics-list-${idxPrefix}`;
    const groupId = `analytics-group-${idxPrefix}`;

    return `
      <div data-analytics-group="${groupId}" style="padding:14px;border-radius:14px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:10px;min-width:0;">
            ${avatarHtml}
            <div style="font-size:15px;font-weight:700;line-height:1.3;">
              <a href="${escapeHtml(channelUrl)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;text-underline-offset:3px;">${escapeHtml(titleText)}</a>${handleText}
            </div>
          </div>
          <div style="font-size:12px;opacity:.7;">Роликов: ${fmt(s.total_videos)}</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:8px;margin-bottom:12px;">
          <div style="padding:9px 11px;border-radius:10px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:11px;opacity:.7;margin-bottom:3px;">Shorts / Горизонт.</div>
            <div style="font-size:15px;font-weight:700;">${fmt(s.shorts_count)} / ${fmt(s.horizontal_count)}</div>
          </div>
          <div style="padding:9px 11px;border-radius:10px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:11px;opacity:.7;margin-bottom:3px;">Всего просмотров</div>
            <div style="font-size:15px;font-weight:700;">${fmt(s.total_views)}</div>
          </div>
          <div style="padding:9px 11px;border-radius:10px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:11px;opacity:.7;margin-bottom:3px;">Всего лайков</div>
            <div style="font-size:15px;font-weight:700;">${fmt(s.total_likes)}</div>
          </div>
          <div style="padding:9px 11px;border-radius:10px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:11px;opacity:.7;margin-bottom:3px;">Просмотры (Shorts / Видео)</div>
            <div style="font-size:13px;font-weight:700;">${fmt(s.total_views)} (${fmt(s.shorts_views)} / ${fmt(s.horizontal_views)})</div>
          </div>
        </div>

        <details style="margin-top:4px;">
          <summary style="cursor:pointer;font-size:13px;font-weight:600;opacity:.9;padding:4px 2px;">
            Показать статистику по каждому видео (${fmt(videos.length)})
          </summary>
          <div style="display:flex;align-items:center;gap:8px;margin-top:10px;margin-bottom:8px;flex-wrap:wrap;">
            <button type="button" data-group="${groupId}" data-sort="views" style="cursor:pointer;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid rgba(225,29,72,0.45);background:rgba(225,29,72,0.22);color:#fda4af;">
              По просмотрам
            </button>
            <button type="button" data-group="${groupId}" data-sort="likes" style="cursor:pointer;padding:6px 12px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid rgba(255,255,255,0.14);background:rgba(255,255,255,0.04);color:#e5e7eb;">
              По лайкам
            </button>
          </div>
          <div id="${listId}" style="display:flex;flex-direction:column;gap:8px;max-height:420px;overflow-y:auto;">
            ${renderRows(videos, "views")}
          </div>
        </details>
      </div>
    `;
  }

  function bindSortButtons(container, datasetsByGroup) {
    const buttons = Array.from(container.querySelectorAll("button[data-group][data-sort]"));
    buttons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const groupId = btn.getAttribute("data-group");
        const nextSort = btn.getAttribute("data-sort");
        const dataset = datasetsByGroup[groupId];
        if (!dataset || !nextSort || dataset.currentSort === nextSort) return;

        dataset.currentSort = nextSort;
        const groupButtons = buttons.filter((b) => b.getAttribute("data-group") === groupId);
        groupButtons.forEach((b) => {
          const active = b.getAttribute("data-sort") === nextSort;
          b.style.border = active
            ? "1px solid rgba(225,29,72,0.45)"
            : "1px solid rgba(255,255,255,0.14)";
          b.style.background = active
            ? "rgba(225,29,72,0.22)"
            : "rgba(255,255,255,0.04)";
          b.style.color = active ? "#fda4af" : "#e5e7eb";
        });

        const listEl = container.querySelector(`#${dataset.listId}`);
        if (listEl) {
          listEl.innerHTML = renderRows(dataset.videos, nextSort);
        }
      });
    });
  }

  function findRemixersSection() {
    const allSections = Array.from(document.querySelectorAll("section, div"));
    for (const el of allSections) {
      if (el.id === "channel-analytics-section" || el.id === "creators-analytics-section") continue;
      const text = (el.textContent || "");
      if (text.includes("Ремиксы на Shorts Ники") && text.includes("Авторов:")) {
        const hasFooter = el.querySelector("footer") || el.tagName === "BODY";
        if (!hasFooter) return el;
      }
    }
    return null;
  }

  async function initAnalytics() {
    try {
      const [ownRes, creatorsRes] = await Promise.all([
        fetch("./channel_analytics.json?t=" + Date.now()),
        fetch("./creators_analytics.json?t=" + Date.now()).catch(() => null),
      ]);

      const datasetsByGroup = {};

      if (ownRes && ownRes.ok) {
        const ownData = await ownRes.json();
        if (ownData && ownData.summary) {
          const s = ownData.summary;
          const videos = Array.isArray(ownData.videos) ? ownData.videos : [];
          const groupId = "own-channel";
          datasetsByGroup[groupId] = {
            videos,
            currentSort: "views",
            listId: "analytics-list-own",
          };

          const existingOwn = document.getElementById("channel-analytics-section");
          if (existingOwn) existingOwn.remove();

          const section = document.createElement("section");
          section.id = "channel-analytics-section";
          section.style.cssText = [
            "max-width: 920px",
            "margin: 20px auto 24px",
            "padding: 16px",
            "border-radius: 16px",
            "background: rgba(255, 255, 255, 0.04)",
            "border: 1px solid rgba(255, 255, 255, 0.08)",
            "color: #f3f4f6",
            "font-family: inherit"
          ].join(";");

          section.innerHTML = `
            <div style="font-size:16px;font-weight:700;margin-bottom:12px;">Аналитика канала</div>
            ${buildAnalyticsCardHtml(s, videos, "own")}
          `;

          bindSortButtons(section, datasetsByGroup);

          const footer = document.querySelector("footer");
          if (footer && footer.parentNode) {
            footer.parentNode.insertBefore(section, footer);
          } else {
            document.body.appendChild(section);
          }
        }
      }

      if (creatorsRes && creatorsRes.ok) {
        const creatorsData = await creatorsRes.json();
        const creators = Array.isArray(creatorsData && creatorsData.creators) ? creatorsData.creators : [];
        const remixersBlock = findRemixersSection();

        if (remixersBlock) {
          const existingCreatorsBlock = document.getElementById("creators-analytics-section");
          if (existingCreatorsBlock) existingCreatorsBlock.remove();

          const wrapper = document.createElement("div");
          wrapper.id = "creators-analytics-section";
          wrapper.style.cssText = "margin-top: 12px;";

          const cardsHtml = creators.map((item, idx) => {
            const cs = (item && item.summary) || {};
            const cv = Array.isArray(item && item.videos) ? item.videos : [];
            const gId = `creator-${idx}`;
            datasetsByGroup[gId] = {
              videos: cv,
              currentSort: "views",
              listId: `analytics-list-creator-${idx}`,
            };
            return buildAnalyticsCardHtml(cs, cv, `creator-${idx}`);
          }).join("");

          wrapper.innerHTML = cardsHtml || `<div style="padding:12px;font-size:13px;opacity:.75;">Данные по авторам пока собираются.</div>`;

          Array.from(remixersBlock.children).forEach((child) => {
            const txt = child.textContent || "";
            const isHeaderBar = txt.includes("Ремиксы на Shorts Ники") || txt.includes("Авторов:");
            if (!isHeaderBar) {
              child.style.display = "none";
            }
          });

          remixersBlock.appendChild(wrapper);
          bindSortButtons(wrapper, datasetsByGroup);
        }
      }
    } catch (e) {
      console.warn("Analytics load skipped:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAnalytics);
  } else {
    initAnalytics();
  }
})();
