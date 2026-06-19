#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket Event Handler
Handles routing and processing of WebSocket API events
"""

import json
import logging
from typing import Optional

from config import INTERESTING_PHASES
from lcu import LCU, compute_locked
from state import SharedState
from utils.core.logging import get_logger, log_status, log_event
from injection.config.base_skin_tracker import (
    on_skin_confirmed as _on_skin_confirmed,
    on_champ_select_exit as _on_champ_select_exit,
)

log = get_logger()


class WebSocketEventHandler:
    """Handles routing and processing of WebSocket API events"""
    
    def __init__(
        self,
        lcu: LCU,
        state: SharedState,
        champion_lock_handler=None,
        game_mode_detector=None,
        timer_manager=None,
        injection_manager=None,
        swiftplay_handler=None,
    ):
        """Initialize event handler

        Args:
            lcu: LCU client instance
            state: Shared application state
            champion_lock_handler: Handler for champion lock events
            game_mode_detector: Game mode detector instance
            timer_manager: Timer manager instance
            injection_manager: Injection manager instance
            swiftplay_handler: Swiftplay handler instance for overlay injection
        """
        self.lcu = lcu
        self.state = state
        self.champion_lock_handler = champion_lock_handler
        self.game_mode_detector = game_mode_detector
        self.timer_manager = timer_manager
        self.injection_manager = injection_manager
        self.swiftplay_handler = swiftplay_handler
        # Track the last phase THIS handler observed, independent of state.phase
        # (which the HTTP poller also writes).  Comparing against state.phase let
        # the poller swallow our ChampSelect event on game 2 - see champ_select_reset.
        self._ws_last_phase = None
    
    def handle_message(self, ws, msg):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(msg)
            if isinstance(data, list) and len(data) >= 3:
                if data[0] == 8 and isinstance(data[2], dict):
                    self.handle_api_event(data[2])
                return
            if isinstance(data, dict) and "uri" in data:
                self.handle_api_event(data)
        except Exception:
            pass
    
    def handle_api_event(self, payload: dict):
        """Handle API event from WebSocket"""
        uri = payload.get("uri")
        if not uri:
            return
        
        if uri == "/lol-gameflow/v1/gameflow-phase":
            self._handle_phase_event(payload)
        elif uri == "/lol-champ-select/v1/hovered-champion-id":
            self._handle_hovered_champion_event(payload)
        elif uri == "/lol-champ-select/v1/session":
            self._handle_session_event(payload)
    
    def _handle_phase_event(self, payload: dict):
        """Handle gameflow phase event"""
        ph = payload.get("data")
        # Phase transitions are handled by phase_thread
        # own_champion_locked flag can coexist with any phase
        # Compare against our OWN last-seen phase, not state.phase: the HTTP
        # poller also writes state.phase, and if it advanced to "ChampSelect"
        # first, comparing to state.phase would swallow our ChampSelect event
        # for game 2 and skip the per-game reset.
        if isinstance(ph, str) and ph != self._ws_last_phase and ph is not None:
            if ph in INTERESTING_PHASES:
                log_status(log, "Phase", ph, "")
            prev_phase = self._ws_last_phase
            self._ws_last_phase = ph
            self.state.phase = ph

            # Re-arm the per-game ChampSelect reset guard once we leave ChampSelect
            from threads.handlers.champ_select_reset import note_phase_for_reset
            note_phase_for_reset(self.state, ph)

            # If leaving ChampSelect, record a timeout for any pending base skin confirmation
            if prev_phase == "ChampSelect" and ph != "ChampSelect":
                try:
                    _on_champ_select_exit()
                except Exception:
                    pass
            
            if ph == "ChampSelect":
                # Detect game mode FIRST to get accurate is_swiftplay_mode flag
                if self.game_mode_detector:
                    self.game_mode_detector.detect_game_mode()
                
                # Refresh injection threshold
                if self.injection_manager:
                    try:
                        new_threshold = self.injection_manager.refresh_injection_threshold()
                        log.info(f"[WS] Injection threshold refreshed for ChampSelect: {new_threshold:.2f}s")
                    except Exception as exc:  # noqa: BLE001
                        log.warning(f"[WS] Failed to refresh injection threshold in ChampSelect: {exc}")
                
                if self.state.is_swiftplay_mode:
                    log.debug("[WS] ChampSelect in Swiftplay mode - skipping normal reset")
                    if self.state.swiftplay_extracted_mods and self.swiftplay_handler:
                        import threading
                        log.info("[WS] Triggering Swiftplay overlay injection from WebSocket handler")
                        threading.Thread(
                            target=self.swiftplay_handler.run_swiftplay_overlay,
                            daemon=True,
                            name="SwiftplayOverlay-WS",
                        ).start()
                else:
                    self._handle_champ_select_entry()
            
            elif ph == "FINALIZATION":
                log_event(log, "Entering FINALIZATION phase", "")
            
            elif ph == "InProgress":
                self._handle_in_progress_entry()
            
            else:
                # Exit → reset locks/timer
                self._handle_phase_exit()
    
    def _handle_champ_select_entry(self):
        """Handle entering ChampSelect phase.

        Delegates to the shared, idempotent reset so the HTTP poller and this
        WebSocket handler can't disagree about whether the per-game reset ran.
        The `champion_lock_handler.last_locked_champion_id` reset is routed via
        `state.reset_last_locked` (honoured in ChampionLockHandler).
        """
        from threads.handlers.champ_select_reset import perform_champ_select_reset
        perform_champ_select_reset(self.state, self.lcu)
    
    def _handle_in_progress_entry(self):
        """Handle entering InProgress phase"""
        from utils.core.logging import log_section
        
        if self.state.last_hovered_skin_key:
            log_section(log, f"Game Starting - Last Detected Skin: {self.state.last_hovered_skin_key.upper()}", "", {
                "Champion": self.state.last_hovered_skin_slug,
                "SkinID": self.state.last_hovered_skin_id
            })
        else:
            log_event(log, "No hovered skin detected", "ℹ️")
    
    def _handle_phase_exit(self):
        """Handle exiting a phase"""
        self.state.hovered_champ_id = None
        self.state.players_visible = 0
        self.state.locks_by_cell.clear()
        self.state.all_locked_announced = False
        self.state.loadout_countdown_active = False
    
    def _handle_hovered_champion_event(self, payload: dict):
        """Handle hovered champion ID event"""
        cid = payload.get("data")
        try:
            cid = int(cid) if cid is not None else None
        except Exception:
            cid = None
        
        if cid and cid != self.state.hovered_champ_id:
            nm = f"champ_{cid}"
            log_status(log, "Champion hovered", f"{nm} (ID: {cid})", "👆")
            self.state.hovered_champ_id = cid
    
    def _handle_session_event(self, payload: dict):
        """Handle champion select session event"""
        sess = payload.get("data") or {}
        self.state.local_cell_id = sess.get("localPlayerCellId", self.state.local_cell_id)
        
        # Track selected skin ID from myTeam
        if self.state.local_cell_id is not None:
            my_team = sess.get("myTeam") or []
            for player in my_team:
                if player.get("cellId") == self.state.local_cell_id:
                    selected_skin = player.get("selectedSkinId")
                    if selected_skin is not None:
                        skin_int = int(selected_skin)
                        self.state.selected_skin_id = skin_int
                        # Check if this confirms a pending base skin force
                        try:
                            _on_skin_confirmed(skin_int)
                        except Exception:
                            pass
                    break
        
        # Visible players (distinct cellIds)
        seen = set()
        for side in (sess.get("myTeam") or [], sess.get("theirTeam") or []):
            for p in side or []:
                cid = p.get("cellId")
                if cid is not None:
                    seen.add(int(cid))
        if not seen:
            for rnd in (sess.get("actions") or []):
                for a in rnd or []:
                    cid = a.get("actorCellId")
                    if cid is not None:
                        seen.add(int(cid))
        
        count_visible = len(seen)
        if count_visible != self.state.players_visible and count_visible > 0:
            self.state.players_visible = count_visible
            log_status(log, "Players", count_visible, "")
        
        # Lock counter: diff cellId → championId
        if self.champion_lock_handler:
            self.champion_lock_handler.handle_session_locks(sess)
        
        # Timer
        if self.timer_manager:
            self.timer_manager.maybe_start_timer(sess)

