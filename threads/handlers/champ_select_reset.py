#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Champ-Select Reset (single source of truth)

The per-game "re-arm" reset used to live only in the WebSocket phase handler
(`_handle_champ_select_entry`).  Because two threads (the HTTP poller
`PhaseThread` and the `WSEventThread`) both write `state.phase`, the WebSocket
handler could see its ChampSelect event swallowed for the *second* game (the
poller had already advanced `state.phase` to "ChampSelect"), leaving
`last_hover_written` / `loadout_countdown_active` / `owned_skin_ids` stale from
game 1.  The visible symptom was "injection works for one game, then stops".

This module exposes one idempotent reset that EITHER phase observer can call on
ChampSelect entry.  An entry guard (`state.champ_select_reset_done`) ensures it
runs exactly once per ChampSelect, regardless of which thread gets there first.
Call `note_phase_for_reset()` on every observed phase so the guard re-arms when
a new game's ChampSelect begins.
"""

import logging

log = logging.getLogger(__name__)

# Phases during which the ChampSelect reset must NOT be re-armed.  Anything else
# (InProgress, EndOfGame, Lobby, GameStart, Matchmaking, None, ...) clears the
# guard so the next ChampSelect entry performs a fresh reset.
_CHAMP_SELECT_PHASES = {"ChampSelect", "FINALIZATION"}


def note_phase_for_reset(state, phase) -> None:
    """Re-arm the ChampSelect reset guard once we leave ChampSelect/FINALIZATION."""
    if phase not in _CHAMP_SELECT_PHASES:
        if getattr(state, "champ_select_reset_done", False):
            state.champ_select_reset_done = False


def perform_champ_select_reset(state, lcu) -> bool:
    """Reset all per-game state for a fresh ChampSelect.

    Idempotent: only the first caller per ChampSelect entry performs the work;
    subsequent callers (the other phase observer) no-op until the guard is
    re-armed by `note_phase_for_reset()`.

    Returns True if the reset actually ran, False if it was skipped.
    """
    if getattr(state, "champ_select_reset_done", False):
        return False
    state.champ_select_reset_done = True

    log.info("[reset] Entering ChampSelect - resetting state for new game")

    # Reset skin detection state
    state.last_hovered_skin_key = None
    state.last_hovered_skin_id = None
    state.last_hovered_skin_slug = None
    state.ui_last_text = None
    state.ui_skin_id = None

    # Reset LCU skin selection
    state.selected_skin_id = None
    try:
        state.owned_skin_ids.clear()
    except Exception:
        state.owned_skin_ids = set()

    # The two flags that gate injection for the next game (this is the bug fix)
    state.last_hover_written = False
    state.injection_completed = False
    state.loadout_countdown_active = False

    # Reset champion lock state for new game
    state.locked_champ_id = None
    state.locked_champ_timestamp = 0.0
    state.own_champion_locked = False

    # Ask ChampionLockHandler to forget its last lock (it lives on the WS thread
    # and isn't reachable from the poll path, so we route it through a flag).
    state.reset_last_locked = True

    # Broadcast champion unlock state to JavaScript
    try:
        if getattr(state, "ui_skin_thread", None):
            state.ui_skin_thread._broadcast_champion_locked(False)
    except Exception as e:
        log.debug(f"[reset] Failed to broadcast champion unlock state: {e}")

    # Reset random skin state
    state.random_skin_name = None
    state.random_skin_id = None
    state.random_mode_active = False

    # Reset historic mode state
    state.historic_mode_active = False
    state.historic_skin_id = None
    state.historic_first_detection_done = False

    # Clear custom mod selection from previous game so the mod-name popup
    # doesn't re-appear until the user (or historic auto-select) picks it.
    state.selected_custom_mod = None

    # Reset exchange tracking
    state.champion_exchange_triggered = False

    # Signal main thread to reset skin notification debouncing
    state.reset_skin_notification = True
    try:
        state.processed_action_ids.clear()
    except Exception:
        state.processed_action_ids = set()

    # Request UI initialization when entering ChampSelect
    try:
        from ui.core.user_interface import get_user_interface
        user_interface = get_user_interface(state, None)  # skin_scraper not needed here
        user_interface.reset_skin_state()
        user_interface._force_reinitialize = True
        user_interface.request_ui_initialization()
        log.debug("[reset] UI reinitialization requested for ChampSelect")
    except Exception as e:
        log.warning(f"[reset] Failed to request UI initialization for ChampSelect: {e}")

    # Load owned skins immediately when entering ChampSelect
    try:
        owned_skins = lcu.owned_skins() if lcu else None
        if owned_skins and isinstance(owned_skins, list):
            state.owned_skin_ids = set(owned_skins)
            log.info(f"[reset] Loaded {len(state.owned_skin_ids)} owned skins from inventory")
        else:
            log.warning(f"[reset] Failed to fetch owned skins from LCU - no data returned (response: {owned_skins})")
    except Exception as e:
        log.warning(f"[reset] Error fetching owned skins: {e}")

    log.debug("[reset] State reset complete - ready for new champion select")
    return True
