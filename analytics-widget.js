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

  async function initChannelAnalytics() {
    try {
      const res = await fetch("./channel_analytics.json?t=" + Date.now());
      if (!res.ok) return;
      const data = await res.json();
      if (!data || !data.summary) return;

      const s = data.summary;
      const videos = Array.isArray(data.videos) ? data.videos : [];
      const channelName = s.channel || "MSK239";
      const channelUrl = s.channel_url || "https://www.youtube.com/@MSK239";
      const avatarHtml = s.avatar_url
        ? `<img src="${escapeHtml(s.avatar_url)}" alt="${escapeHtml(channelName)}" onerror="this.style.display='none'" style="width:34px;height:34px;border-radius:999px;object-fit:cover;flex-shrink:0;border:1px solid rgba(255,255,255,0.16);">`
        : "";

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

      const rowsHtml = videos.map((v, i) => {
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

      section.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap;">
          <div style="display:flex;align-items:center;gap:10px;min-width:0;">
            ${avatarHtml}
            <div style="font-size:16px;font-weight:700;line-height:1.3;">
              Аналитика канала <a href="${escapeHtml(channelUrl)}" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;text-underline-offset:3px;">${escapeHtml(channelName)}</a>
            </div>
          </div>
          <div style="font-size:12px;opacity:.7;">Всего роликов: ${fmt(s.total_videos)}</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:10px;margin-bottom:14px;">
          <div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:12px;opacity:.7;margin-bottom:4px;">Shorts / Горизонт.</div>
            <div style="font-size:17px;font-weight:700;">${fmt(s.shorts_count)} / ${fmt(s.horizontal_count)}</div>
          </div>
          <div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:12px;opacity:.7;margin-bottom:4px;">Всего просмотров</div>
            <div style="font-size:17px;font-weight:700;">${fmt(s.total_views)}</div>
          </div>
          <div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:12px;opacity:.7;margin-bottom:4px;">Всего лайков</div>
            <div style="font-size:17px;font-weight:700;">${fmt(s.total_likes)}</div>
          </div>
          <div style="padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);">
            <div style="font-size:12px;opacity:.7;margin-bottom:4px;">Просмотры (Shorts / Видео)</div>
            <div style="font-size:14px;font-weight:700;">${fmt(s.total_views)} (${fmt(s.shorts_views)} / ${fmt(s.horizontal_views)})</div>
          </div>
        </div>

        <details style="margin-top:6px;">
          <summary style="cursor:pointer;font-size:13px;font-weight:600;opacity:.9;padding:6px 2px;">
            Показать статистику по каждому видео (${fmt(videos.length)})
          </summary>
          <div style="display:flex;flex-direction:column;gap:8px;margin-top:10px;max-height:420px;overflow-y:auto;">
            ${rowsHtml}
          </div>
        </details>
      `;

      const footer = document.querySelector("footer");
      if (footer && footer.parentNode) {
        footer.parentNode.insertBefore(section, footer);
      } else {
        document.body.appendChild(section);
      }
    } catch (e) {
      console.warn("Channel analytics load skipped:", e);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initChannelAnalytics);
  } else {
    initChannelAnalytics();
  }
})();
