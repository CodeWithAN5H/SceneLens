"""Recognition result screen: compared frames, metadata, fallback and sharing."""

from __future__ import annotations

import threading
import webbrowser

import customtkinter as ctk
from PIL import Image

from ..engines.router import ScanReport
from ..utils.clipboard import copy_image_to_clipboard, copy_text, reveal_in_file_manager
from ..utils.discord_card import build_discord_markdown, render_share_card
from ..utils.remote import fetch_remote_image
from . import theme as t
from .widgets import Badge, ConfidenceMeter, Divider, ImagePanel, MetricRow, SectionTitle


class LinkLabel(ctk.CTkLabel):
    """Compact text link that behaves like a button."""

    def __init__(self, master, text: str, url: str, accent: str = t.CYAN):
        super().__init__(
            master,
            text=text,
            font=t.ui_font(9, "bold"),
            text_color=t.MUTED,
            fg_color=t.PANEL_ALT,
            corner_radius=6,
            height=24,
            cursor="hand2",
        )
        self._accent = accent
        self.bind("<Button-1>", lambda _event: webbrowser.open(url))
        self.bind("<Enter>", lambda _event: self.configure(text_color=accent))
        self.bind("<Leave>", lambda _event: self.configure(text_color=t.MUTED))


class ResultsView(ctk.CTkFrame):
    def __init__(
        self,
        master,
        app,
        report: ScanReport,
        own_image: Image.Image | None,
        *,
        from_history: bool = False,
    ) -> None:
        super().__init__(master, fg_color=t.BG)
        self.app = app
        self.report = report
        self.best = report.best
        self._own_image = own_image
        self._matched_image: Image.Image | None = None
        self._card_busy = False
        self._from_history = from_history

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_fg_color="transparent",
            scrollbar_button_color=t.BORDER,
            scrollbar_button_hover_color=t.FAINT,
        )
        self.scroll.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid_columnconfigure(0, weight=1)

        if self.best is None:
            self._build_empty()
        else:
            self._build_result()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_result(self) -> None:
        assert self.best is not None
        accent = t.accent_for(self.best.media_type)

        summary = ctk.CTkFrame(self.scroll, fg_color="transparent")
        summary.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 12))
        summary.grid_columnconfigure(1, weight=1)

        Badge(
            summary,
            "SAVED SCAN" if self._from_history else "SCAN COMPLETE",
            text_color=t.CYAN if self._from_history else t.GREEN,
            fg_color=t.CYAN_SOFT if self._from_history else t.GREEN_SOFT,
            height=26,
        ).grid(row=0, column=0, sticky="w")

        engine_names = []
        for status in self.report.statuses:
            if status.ok and status.name not in engine_names:
                engine_names.append(status.name)
        detail = " + ".join(engine_names) if engine_names else self.best.source
        timing = "" if self._from_history else f"   ·   {self.report.elapsed_seconds:0.1f}s"
        ctk.CTkLabel(
            summary,
            text=f"{detail}{timing}",
            font=t.mono_font(9),
            text_color=t.FAINT,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=12)

        ctk.CTkButton(
            summary,
            text="New scan  Ctrl+N",
            command=self.app.new_scan,
            width=128,
            height=30,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(10, "bold"),
        ).grid(row=0, column=2, sticky="e")

        compare = ctk.CTkFrame(self.scroll, fg_color="transparent")
        compare.grid(row=1, column=0, sticky="ew")
        compare.grid_columnconfigure(0, weight=1, uniform="frames")
        compare.grid_columnconfigure(1, weight=1, uniform="frames")

        own = ImagePanel(compare, "Your frame", accent=t.CYAN, placeholder="NO FRAME")
        own.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        own.set_image(self._own_image)
        if self._own_image:
            own.set_tag(f"{self._own_image.width}×{self._own_image.height}")

        reference = ImagePanel(
            compare,
            "Best match",
            accent=accent,
            placeholder="NO REFERENCE FRAME",
            height=236,
        )
        reference.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self._reference_panel = reference

        reference_url = self.best.matched_frame_url
        if reference_url:
            self._load_reference(reference_url, "BEST MATCH")
        elif self.best.cover_url:
            self._load_reference(self.best.cover_url, "REFERENCE ART")
        else:
            reference.set_caption("Best match", accent)

        lower = ctk.CTkFrame(self.scroll, fg_color="transparent")
        lower.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)

        left = ctk.CTkFrame(
            lower,
            fg_color=t.PANEL,
            corner_radius=14,
            border_width=1,
            border_color=t.BORDER,
        )
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        left.grid_columnconfigure(0, weight=1)

        right = ctk.CTkFrame(
            lower,
            fg_color=t.PANEL,
            corner_radius=14,
            border_width=1,
            border_color=t.BORDER,
        )
        right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        right.grid_columnconfigure(0, weight=1)

        self._build_title_block(left, accent)
        self._build_details_block(right, accent)

        row = 3
        if self.report.used_fallback:
            self._build_fallback(row)
            row += 1

        if self.report.notices:
            self._build_notices(row, accent)
            row += 1

        if not self._from_history and self.report.statuses:
            self._build_engine_log(row)

    # ---- left column -----------------------------------------------------

    def _build_title_block(self, parent, accent: str) -> None:
        assert self.best is not None
        best = self.best

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=22, pady=20)
        body.grid_columnconfigure(0, weight=1)
        self._title_block = body

        badges = ctk.CTkFrame(body, fg_color="transparent")
        badges.grid(row=0, column=0, sticky="w")
        Badge(
            badges,
            best.tag,
            text_color=accent,
            fg_color=t.soft_for(best.media_type),
            border_color=accent,
            height=26,
        ).grid(row=0, column=0, padx=(0, 6))
        if best.episode_code:
            Badge(badges, best.episode_code, text_color=t.TEXT, fg_color=t.PANEL_ALT).grid(
                row=0, column=1, padx=(0, 6)
            )
        if self.report.used_fallback:
            Badge(
                badges,
                "LOW CONFIDENCE",
                text_color=t.RED,
                fg_color="#2A121A",
                height=26,
            ).grid(row=0, column=2)
        elif self._is_unverified_anime():
            Badge(
                badges,
                "UNVERIFIED · ANIME",
                text_color=t.AMBER,
                fg_color=t.AMBER_SOFT,
                height=26,
            ).grid(row=0, column=2)
        elif self._from_history:
            Badge(badges, "HISTORY", text_color=t.FAINT, fg_color=t.PANEL_ALT).grid(
                row=0, column=2
            )

        self.title_label = ctk.CTkLabel(
            body,
            text=best.title,
            font=t.ui_font(30, "bold"),
            text_color=t.TEXT,
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.title_label.grid(row=1, column=0, sticky="w", pady=(14, 2))

        subtitle = best.subtitle
        if best.alt_titles:
            subtitle = f"{subtitle}   ·   {best.alt_titles[0]}" if subtitle else best.alt_titles[0]
        self.subtitle_label = ctk.CTkLabel(
            body,
            text=subtitle,
            font=t.ui_font(12),
            text_color=t.MUTED,
            anchor="w",
            justify="left",
            wraplength=560,
        )
        self.subtitle_label.grid(row=2, column=0, sticky="w")

        scene_parts = []
        if best.episode_code:
            scene_parts.append(best.episode_code)
        if best.timestamp:
            scene_parts.append(best.timestamp)
        if best.level:
            scene_parts.append(best.level)
        if scene_parts:
            ctk.CTkLabel(
                body,
                text="   ·   ".join(scene_parts),
                font=t.mono_font(11, "bold"),
                text_color=accent,
                anchor="w",
            ).grid(row=3, column=0, sticky="w", pady=(7, 0))

        if best.synopsis:
            self.synopsis_label = ctk.CTkLabel(
                body,
                text=best.synopsis,
                font=t.ui_font(11),
                text_color=t.MUTED,
                anchor="w",
                justify="left",
                wraplength=560,
            )
            self.synopsis_label.grid(row=4, column=0, sticky="w", pady=(14, 0))

        if best.evidence:
            quote = ctk.CTkFrame(body, fg_color=t.PANEL_ALT, corner_radius=8)
            quote.grid(row=5, column=0, sticky="ew", pady=(16, 0))
            quote.grid_columnconfigure(1, weight=1)
            ctk.CTkFrame(quote, width=3, fg_color=accent, corner_radius=2).grid(
                row=0, column=0, sticky="ns", padx=(0, 12), pady=10
            )
            text_frame = ctk.CTkFrame(quote, fg_color="transparent")
            text_frame.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=10)
            text_frame.grid_columnconfigure(0, weight=1)
            SectionTitle(text_frame, "Visual evidence").grid(row=0, column=0, sticky="w")
            self.evidence_label = ctk.CTkLabel(
                text_frame,
                text=best.evidence,
                font=t.ui_font(10),
                text_color=t.MUTED,
                anchor="w",
                justify="left",
                wraplength=500,
            )
            self.evidence_label.grid(row=1, column=0, sticky="w", pady=(3, 0))

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=6, column=0, sticky="ew", pady=(20, 0))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            actions,
            text="Copy Discord card",
            command=self._copy_markdown,
            height=38,
            corner_radius=9,
            fg_color=accent,
            hover_color=accent,
            text_color="#06141A",
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._share_button = ctk.CTkButton(
            actions,
            text="Share card PNG",
            command=self._share_card,
            height=38,
            corner_radius=9,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(11, "bold"),
        )
        self._share_button.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        second = ctk.CTkFrame(body, fg_color="transparent")
        second.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        second.grid_columnconfigure(0, weight=1)
        second.grid_columnconfigure(1, weight=1)

        target_url = self.best.preview_video_url or self.best.external_url
        target_label = "Open preview clip" if self.best.preview_video_url else "Open source page"
        if target_url:
            ctk.CTkButton(
                second,
                text=target_label,
                command=lambda: webbrowser.open(target_url),
                height=32,
                corner_radius=8,
                fg_color="transparent",
                hover_color=t.PANEL_HOVER,
                text_color=t.MUTED,
                font=t.ui_font(10, "bold"),
            ).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            second,
            text="New scan",
            command=self.app.new_scan,
            height=32,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            text_color=t.MUTED,
            font=t.ui_font(10, "bold"),
        ).grid(
            row=0,
            column=1 if target_url else 0,
            columnspan=1 if target_url else 2,
            sticky="ew",
            padx=(6, 0) if target_url else (0, 0),
        )

        links = ctk.CTkFrame(body, fg_color="transparent")
        links.grid(row=8, column=0, sticky="ew", pady=(18, 0))
        SectionTitle(links, "Look it up").pack(side="left", padx=(0, 10))
        for index, (name, url) in enumerate(list(self.best.search_links.items())[:4]):
            LinkLabel(links, name, url, accent=accent).pack(side="left", padx=(0, 6))

        body.bind("<Configure>", self._reflow_text)

    def _is_unverified_anime(self) -> bool:
        """trace.moe always returns a nearest frame; flag it without a vision check."""
        return bool(
            self.best is not None
            and self.best.source == "trace.moe"
            and not self.app.settings.vision_configured
        )

    def _reflow_text(self, event) -> None:
        width = max(320, event.width - 44)
        for attribute in ("title_label", "subtitle_label", "synopsis_label", "evidence_label"):
            label = getattr(self, attribute, None)
            if label is not None:
                try:
                    label.configure(wraplength=width)
                except Exception:  # noqa: BLE001
                    pass

    # ---- right column ----------------------------------------------------

    def _build_details_block(self, parent, accent: str) -> None:
        assert self.best is not None
        best = self.best

        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        body.grid_columnconfigure(0, weight=1)

        SectionTitle(body, "Match details").grid(row=0, column=0, sticky="w", pady=(0, 8))

        row_index = 1
        for label, value in best.detail_rows():
            if label == "Engine":
                continue
            MetricRow(body, label, value).grid(row=row_index, column=0, sticky="ew")
            row_index += 1

        Divider(body).grid(row=row_index, column=0, sticky="ew", pady=(10, 14))
        row_index += 1

        ConfidenceMeter(
            body,
            best.confidence,
            accent=accent,
            threshold=self.report.threshold if not self._from_history else None,
        ).grid(row=row_index, column=0, sticky="ew")
        row_index += 1

        Divider(body).grid(row=row_index, column=0, sticky="ew", pady=(16, 12))
        row_index += 1

        SectionTitle(body, "Source").grid(row=row_index, column=0, sticky="w")
        row_index += 1
        source_row = ctk.CTkFrame(body, fg_color="transparent")
        source_row.grid(row=row_index, column=0, sticky="ew", pady=(4, 0))
        ctk.CTkLabel(source_row, text="●", font=t.ui_font(8), text_color=accent, width=12).pack(
            side="left", padx=(0, 4)
        )
        ctk.CTkLabel(
            source_row,
            text=best.source,
            font=t.mono_font(10),
            text_color=t.MUTED,
            anchor="w",
        ).pack(side="left")
        row_index += 1

        if self.report.image_hash:
            ctk.CTkLabel(
                body,
                text=f"frame {self.report.image_hash[:12]}",
                font=t.mono_font(9),
                text_color=t.FAINT,
                anchor="w",
            ).grid(row=row_index, column=0, sticky="w", pady=(4, 0))
            row_index += 1

        if best.external_url:
            ctk.CTkButton(
                body,
                text="Open source",
                command=lambda: webbrowser.open(best.external_url or ""),
                height=32,
                corner_radius=8,
                fg_color="transparent",
                hover_color=t.PANEL_HOVER,
                border_width=1,
                border_color=t.BORDER,
                text_color=t.MUTED,
                font=t.ui_font(10, "bold"),
            ).grid(row=row_index, column=0, sticky="ew", pady=(16, 0))

    # ---- reference image -------------------------------------------------

    def _load_reference(self, url: str, caption: str) -> None:
        self._reference_panel.set_caption(caption, accent=t.accent_for(self.best.media_type))
        self._reference_panel.image_label.configure(text="LOADING REFERENCE…")

        def worker() -> None:
            image = fetch_remote_image(url)
            self.app.post(self._apply_reference, image)

        threading.Thread(target=worker, daemon=True, name="scenelens-reference").start()

    def _apply_reference(self, image: Image.Image | None) -> None:
        if not self.winfo_exists():
            return
        if image is None:
            self._reference_panel.set_image(None, "REFERENCE UNAVAILABLE")
            return
        self._matched_image = image
        self._reference_panel.set_image(image)
        self._reference_panel.set_tag(f"{image.width}×{image.height}")

    # ---- fallback, notices, engine log ----------------------------------

    def _build_fallback(self, row: int) -> None:
        assert self.best is not None
        panel = ctk.CTkFrame(
            self.scroll,
            fg_color="#181316",
            corner_radius=12,
            border_width=1,
            border_color="#4A2530",
        )
        panel.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))
        header.grid_columnconfigure(1, weight=1)
        Badge(header, "LOW CONFIDENCE", text_color=t.RED, fg_color="#2A121A", height=24).grid(
            row=0, column=0, sticky="w"
        )
        ctk.CTkLabel(
            header,
            text=f"Below your {round(self.report.threshold * 100)}% threshold — verify before sharing",
            font=t.ui_font(10),
            text_color=t.MUTED,
            anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=10)

        alternatives: list[tuple[str, str, str, int | None, float, dict[str, str]]] = []
        if self.report.alternatives:
            for result in self.report.alternatives[:3]:
                alternatives.append(
                    (
                        result.title,
                        result.tag,
                        result.media_type,
                        result.year,
                        result.confidence,
                        result.search_links,
                    )
                )
        elif self.best.candidates:
            for candidate in self.best.candidates[:3]:
                if candidate.title == self.best.title:
                    continue
                alternatives.append(
                    (
                        candidate.title,
                        candidate.label,
                        candidate.media_type,
                        candidate.year,
                        candidate.confidence,
                        candidate.links,
                    )
                )

        if not alternatives:
            ctk.CTkLabel(
                panel,
                text="No other plausible matches were returned by the engines.",
                font=t.ui_font(10),
                text_color=t.FAINT,
                anchor="w",
            ).grid(row=1, column=0, sticky="w", padx=18, pady=(4, 16))
            return

        for index, (title, tag, media_type, year, confidence, links) in enumerate(alternatives):
            item = ctk.CTkFrame(panel, fg_color="transparent")
            item.grid(row=index + 1, column=0, sticky="ew", padx=18, pady=(6, 10 if index == len(alternatives) - 1 else 4))
            item.grid_columnconfigure(1, weight=1)

            ctk.CTkLabel(
                item,
                text=f"{index + 1:02d}",
                font=t.mono_font(10),
                text_color=t.FAINT,
                width=24,
            ).grid(row=0, column=0, sticky="nw", padx=(0, 8))

            ctk.CTkLabel(
                item,
                text=title,
                font=t.ui_font(12, "bold"),
                text_color=t.TEXT,
                anchor="w",
                justify="left",
                wraplength=360,
            ).grid(row=0, column=1, sticky="w")

            meta = ctk.CTkFrame(item, fg_color="transparent")
            meta.grid(row=1, column=1, sticky="w", pady=(3, 0))
            Badge(
                meta,
                tag,
                text_color=t.accent_for(media_type),
                fg_color=t.soft_for(media_type),
                height=20,
                font_size=8,
            ).pack(side="left", padx=(0, 6))
            if year:
                ctk.CTkLabel(
                    meta,
                    text=str(year),
                    font=t.ui_font(9),
                    text_color=t.FAINT,
                ).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                meta,
                text=f"{round(confidence * 100)}%",
                font=t.mono_font(9),
                text_color=t.MUTED,
            ).pack(side="left")

            links_row = ctk.CTkFrame(item, fg_color="transparent")
            links_row.grid(row=0, column=2, rowspan=2, sticky="e", padx=(10, 0))
            for name, url in list(links.items())[:3]:
                LinkLabel(links_row, name, url, accent=t.accent_for(media_type)).pack(
                    side="left", padx=(4, 0)
                )

    def _build_notices(self, row: int, accent: str) -> None:
        panel = ctk.CTkFrame(self.scroll, fg_color=t.PANEL, corner_radius=10, border_width=1, border_color=t.BORDER)
        panel.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        panel.grid_columnconfigure(0, weight=1)

        for index, notice in enumerate(self.report.notices[:3]):
            row_frame = ctk.CTkFrame(panel, fg_color="transparent")
            row_frame.grid(row=index, column=0, sticky="ew", padx=16, pady=(10 if index == 0 else 4, 10 if index == len(self.report.notices[:3]) - 1 else 0))
            ctk.CTkLabel(
                row_frame,
                text="●",
                font=t.ui_font(7),
                text_color=t.AMBER if not notice.startswith("Vision engine is off") else accent,
                width=12,
            ).pack(side="left", padx=(0, 6), anchor="n")
            ctk.CTkLabel(
                row_frame,
                text=notice,
                font=t.ui_font(10),
                text_color=t.MUTED,
                anchor="w",
                justify="left",
                wraplength=820,
            ).pack(side="left", fill="x", expand=True)

    def _build_engine_log(self, row: int) -> None:
        panel = ctk.CTkFrame(self.scroll, fg_color="transparent")
        panel.grid(row=row, column=0, sticky="ew", pady=(14, 10))
        panel.grid_columnconfigure(1, weight=1)

        SectionTitle(panel, "Engine log").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        for index, status in enumerate(self.report.statuses, start=1):
            ctk.CTkLabel(
                panel,
                text="●",
                font=t.ui_font(7),
                text_color=t.GREEN if status.ok else t.AMBER,
                width=12,
            ).grid(row=index, column=0, sticky="w", padx=(0, 4), pady=2)
            ctk.CTkLabel(
                panel,
                text=status.name,
                font=t.ui_font(10, "bold"),
                text_color=t.TEXT if status.ok else t.MUTED,
                anchor="w",
            ).grid(row=index, column=1, sticky="w", pady=2)
            ctk.CTkLabel(
                panel,
                text=f"{status.detail}   {status.elapsed_ms} ms" if status.ok else status.detail,
                font=t.mono_font(9),
                text_color=t.FAINT,
                anchor="e",
            ).grid(row=index, column=2, sticky="e", pady=2)

    def _build_empty(self) -> None:
        panel = ctk.CTkFrame(
            self.scroll,
            fg_color=t.PANEL,
            corner_radius=16,
            border_width=1,
            border_color=t.BORDER,
        )
        panel.grid(row=0, column=0, sticky="ew", pady=(6, 0))
        panel.grid_columnconfigure(0, weight=1)

        body = ctk.CTkFrame(panel, fg_color="transparent")
        body.grid(row=0, column=0, pady=46)
        ctk.CTkLabel(
            body,
            text="NO CONFIDENT MATCH",
            font=t.mono_font(10, "bold"),
            text_color=t.AMBER,
        ).pack()
        ctk.CTkLabel(
            body,
            text="SceneLens could not identify this frame.",
            font=t.ui_font(20, "bold"),
            text_color=t.TEXT,
        ).pack(pady=(10, 4))
        ctk.CTkLabel(
            body,
            text="Try a clearer frame, a screenshot without heavy overlays, or configure a vision model in Settings.",
            font=t.ui_font(11),
            text_color=t.MUTED,
            wraplength=520,
            justify="center",
        ).pack()

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(pady=(22, 0))
        ctk.CTkButton(
            actions,
            text="New scan",
            command=self.app.new_scan,
            width=140,
            height=36,
            corner_radius=8,
            fg_color=t.CYAN,
            hover_color="#5BF0FF",
            text_color="#06141A",
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=0, padx=5)
        ctk.CTkButton(
            actions,
            text="Open settings",
            command=self.app.open_settings,
            width=140,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=t.PANEL_HOVER,
            border_width=1,
            border_color=t.BORDER,
            text_color=t.TEXT,
            font=t.ui_font(11, "bold"),
        ).grid(row=0, column=1, padx=5)

        if self.report.notices:
            notice_frame = ctk.CTkFrame(panel, fg_color="transparent")
            notice_frame.grid(row=1, column=0, sticky="ew", padx=30, pady=(0, 26))
            notice_frame.grid_columnconfigure(0, weight=1)
            for index, notice in enumerate(self.report.notices[:3]):
                ctk.CTkLabel(
                    notice_frame,
                    text=f"·  {notice}",
                    font=t.ui_font(10),
                    text_color=t.FAINT,
                    anchor="w",
                    justify="left",
                    wraplength=720,
                ).grid(row=index, column=0, sticky="w", pady=2)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _copy_markdown(self) -> None:
        if self.best is None:
            return
        markdown = build_discord_markdown(self.best)
        if copy_text(self, markdown):
            self.app.toast.show("Discord card copied to clipboard.", kind="success")
        else:
            self.app.toast.show("Could not access the clipboard.", kind="error")

    def _share_card(self) -> None:
        if self.best is None or self._card_busy:
            return
        self._card_busy = True
        self._share_button.configure(state="disabled", text="Rendering…")
        if getattr(self.app, "clipboard_watcher", None):
            # The card itself becomes a clipboard image; don't offer to scan it.
            self.app.clipboard_watcher.pause(5.0)
        self.app.toast.show("Rendering your share card…", kind="info", duration=2200)

        best = self.best
        own = self._own_image
        matched = self._matched_image

        def worker() -> None:
            reference = matched
            if reference is None and best.matched_frame_url:
                reference = fetch_remote_image(best.matched_frame_url)
            if reference is None and best.cover_url:
                reference = fetch_remote_image(best.cover_url)
            try:
                path = render_share_card(best, own, reference)
                copied = copy_image_to_clipboard(path)
            except Exception as error:  # noqa: BLE001
                self.app.post(self._card_failed, str(error))
                return
            self.app.post(self._card_ready, path, copied)

        threading.Thread(target=worker, daemon=True, name="scenelens-card").start()

    def _card_ready(self, path, copied: bool) -> None:
        self._card_busy = False
        if not self.winfo_exists():
            return
        try:
            self._share_button.configure(state="normal", text="Share card PNG")
        except Exception:  # noqa: BLE001
            pass
        if getattr(self.app, "clipboard_watcher", None):
            self.app.clipboard_watcher.pause(3.0)
        message = "Card image copied to the clipboard." if copied else "Share card saved to your exports folder."
        self.app.toast.show(
            message,
            kind="success",
            action_label="Show folder",
            action=lambda: reveal_in_file_manager(path),
            duration=6000,
        )

    def _card_failed(self, message: str) -> None:
        self._card_busy = False
        if self.winfo_exists():
            try:
                self._share_button.configure(state="normal", text="Share card PNG")
            except Exception:  # noqa: BLE001
                pass
        self.app.toast.show(f"Could not render the card: {message}", kind="error")
