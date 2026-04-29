#!/usr/bin/env python3
"""
Equity Flow Control Module
Manages auto/manual equity calculation based on street detection

RULES:
- PREFLOP (0 cards): No calculation
- FLOP (3 cards): AUTO trigger ONCE per hand
- TURN (4 cards): MANUAL only (no auto)
- RIVER (5 cards): RESET state for next hand
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class EquityFlowController:
    """
    Controls when equity calculations are triggered based on poker street.
    """
    
    def __init__(self):
        # State tracking per table
        self._table_states = {}
        
    def detect_street(self, board: Dict) -> str:
        """
        Detect poker street from board cards.
        
        Args:
            board: Dict with keys "flop" (list), "turn" (str/None), "river" (str/None)
            
        Returns:
            One of: "PREFLOP", "FLOP", "TURN", "RIVER"
        """
        flop = board.get("flop", [])
        turn = board.get("turn")
        river = board.get("river")
        
        # Count total board cards
        total_cards = len(flop)
        if turn:
            total_cards += 1
        if river:
            total_cards += 1
            
        if total_cards == 0:
            return "PREFLOP"
        elif total_cards == 3:
            return "FLOP"
        elif total_cards == 4:
            return "TURN"
        elif total_cards >= 5:
            return "RIVER"
        else:
            # Edge case: 1-2 cards (shouldn't happen in normal PLO)
            return "PREFLOP"
    
    def _get_table_state(self, table_id: str) -> Dict:
        """Get or create state for a table."""
        if table_id not in self._table_states:
            self._table_states[table_id] = {
                "last_street": None,
                "last_board": None,
                "flop_equity_done": False,
                "hand_key": None,
                "last_updated": None
            }
        return self._table_states[table_id]
    
    def should_trigger_equity(
        self, 
        table_id: str, 
        board: Dict,
        hand_key: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Determine if equity calculation should trigger.
        
        Args:
            table_id: Unique table identifier
            board: Current board state
            hand_key: Optional hand identifier to detect new hands
            
        Returns:
            Tuple of (should_trigger: bool, reason: str)
        """
        state = self._get_table_state(table_id)
        current_street = self.detect_street(board)
        
        # Check if this is a new hand (hand_key changed)
        if hand_key and hand_key != state["hand_key"]:
            logger.info(f"[EquityFlow] New hand detected for {table_id}, resetting state")
            self._reset_table_state(table_id)
            state["hand_key"] = hand_key
        
        # RIVER: Reset state
        if current_street == "RIVER":
            if state["last_street"] != "RIVER":
                logger.info(f"[EquityFlow] RIVER detected for {table_id}, resetting state")
                self._reset_table_state(table_id)
                state["last_street"] = "RIVER"
            return False, "RIVER: State reset, no equity calculation"
        
        # PREFLOP: No action
        if current_street == "PREFLOP":
            state["last_street"] = "PREFLOP"
            return False, "PREFLOP: No equity calculation"
        
        # FLOP: Auto-trigger once
        if current_street == "FLOP":
            # Check if we transitioned to FLOP and haven't calculated yet
            if not state["flop_equity_done"]:
                logger.info(f"[EquityFlow] FLOP auto-trigger for {table_id}")
                state["flop_equity_done"] = True
                state["last_street"] = "FLOP"
                state["last_board"] = self._serialize_board(board)
                state["last_updated"] = datetime.now().isoformat()
                return True, "FLOP: Auto-triggered"
            else:
                # Already calculated for this flop
                state["last_street"] = "FLOP"
                return False, "FLOP: Already calculated"
        
        # TURN: Manual only (never auto-trigger)
        if current_street == "TURN":
            state["last_street"] = "TURN"
            return False, "TURN: Manual trigger only"
        
        return False, f"Unknown street: {current_street}"
    
    def trigger_manual_equity(self, table_id: str) -> Tuple[bool, str]:
        """
        Manually trigger equity calculation (for TURN).
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        state = self._get_table_state(table_id)
        
        if state["last_street"] == "TURN":
            logger.info(f"[EquityFlow] Manual equity trigger for {table_id} on TURN")
            state["last_updated"] = datetime.now().isoformat()
            return True, "Manual equity calculation triggered on TURN"
        else:
            current_street = state["last_street"] or "UNKNOWN"
            logger.warning(f"[EquityFlow] Manual trigger on {current_street} (expected TURN)")
            return True, f"Manual equity calculation triggered on {current_street}"
    
    def _reset_table_state(self, table_id: str):
        """Reset equity state for a table (called on RIVER or new hand)."""
        state = self._get_table_state(table_id)
        state["last_street"] = None
        state["last_board"] = None
        state["flop_equity_done"] = False
        state["last_updated"] = datetime.now().isoformat()
        logger.info(f"[EquityFlow] State reset for {table_id}")
    
    def _serialize_board(self, board: Dict) -> str:
        """Serialize board to string for comparison."""
        flop = board.get("flop", [])
        turn = board.get("turn", "")
        river = board.get("river", "")
        return f"{''.join(flop)}|{turn}|{river}"
    
    def get_table_state(self, table_id: str) -> Dict:
        """Get current state for a table (for debugging/monitoring)."""
        return self._get_table_state(table_id).copy()
    
    def get_all_states(self) -> Dict:
        """Get all table states (for debugging/monitoring)."""
        return {
            table_id: state.copy() 
            for table_id, state in self._table_states.items()
        }


# Global instance
_equity_flow_controller = EquityFlowController()


def detect_street(board: Dict) -> str:
    """Convenience function: Detect street from board."""
    return _equity_flow_controller.detect_street(board)


def should_trigger_equity(table_id: str, board: Dict, hand_key: Optional[str] = None) -> Tuple[bool, str]:
    """Convenience function: Check if equity should auto-trigger."""
    return _equity_flow_controller.should_trigger_equity(table_id, board, hand_key)


def trigger_manual_equity(table_id: str) -> Tuple[bool, str]:
    """Convenience function: Manually trigger equity calculation."""
    return _equity_flow_controller.trigger_manual_equity(table_id)


def get_equity_flow_state(table_id: str) -> Dict:
    """Convenience function: Get state for debugging."""
    return _equity_flow_controller.get_table_state(table_id)


def get_all_equity_flow_states() -> Dict:
    """Convenience function: Get all states for debugging."""
    return _equity_flow_controller.get_all_states()
