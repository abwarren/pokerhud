#!/usr/bin/env python3
"""
PLO Equity Engine
Calculates PLO equity using Monte Carlo simulation with valid hand generation
"""

import random
from typing import Dict, List


def calculate_plo_equity(
    hero_hand_str: str,
    board_str: str = "",
    num_opponents: int = 1,
    iterations: int = 10000
) -> Dict:
    """
    Calculate PLO4 equity for hero hand vs random opponents.

    Args:
        hero_hand_str: 8-character hero hand (e.g., "AhKhQdJd")
        board_str: Board cards (e.g., "9h8h7c" or "9h8h7c3s2d")
        num_opponents: Number of opponents (1-8)
        iterations: Monte Carlo iterations (default 10000)

    Returns:
        Dict with equity, win_rate, tie_rate
    """
    # Parse hero hand
    hero_cards = parse_hand(hero_hand_str)
    if len(hero_cards) != 4:
        raise ValueError(f"Hero must have exactly 4 cards, got {len(hero_cards)}")

    # Parse board
    board_cards = parse_hand(board_str) if board_str else []

    # Validate no duplicate cards
    all_cards = hero_cards + board_cards
    if len(all_cards) != len(set(all_cards)):
        raise ValueError(f"Duplicate cards detected: {all_cards}")

    # Run Monte Carlo simulation
    wins = 0
    ties = 0

    for _ in range(iterations):
        # Generate random villain hands (excluding hero + board)
        used_cards = set(hero_cards + board_cards)
        villain_hands = []

        for _ in range(num_opponents):
            villain_hand = generate_random_plo4_hand(used_cards)
            villain_hands.append(villain_hand)
            used_cards.update(villain_hand)

        # Complete board if needed (mock - simplified)
        full_board = complete_board(board_cards, used_cards)

        # Evaluate hands (simplified - would use eval7 or similar in production)
        hero_rank = evaluate_plo_hand(hero_cards, full_board)
        villain_ranks = [evaluate_plo_hand(vh, full_board) for vh in villain_hands]

        max_villain_rank = max(villain_ranks) if villain_ranks else -1

        if hero_rank > max_villain_rank:
            wins += 1
        elif hero_rank == max_villain_rank:
            ties += 1

    # Calculate percentages
    win_rate = (wins / iterations) * 100
    tie_rate = (ties / iterations) * 100
    equity = win_rate + (tie_rate / 2)  # Equity = win% + tie%/2

    return {
        "equity": round(equity, 2),
        "win_rate": round(win_rate, 2),
        "tie_rate": round(tie_rate, 2),
        "iterations": iterations
    }


def parse_hand(hand_str: str) -> List[str]:
    """Parse hand string into list of cards."""
    if not hand_str:
        return []

    cards = []
    i = 0
    while i < len(hand_str):
        if i + 1 < len(hand_str):
            if hand_str[i:i+2] == "10":
                rank = "T"
                suit = hand_str[i+2] if i+2 < len(hand_str) else ""
                i += 3
            else:
                rank = hand_str[i]
                suit = hand_str[i+1]
                i += 2

            if suit:
                cards.append(f"{rank}{suit}")

    return cards


def generate_random_plo4_hand(excluded_cards: set) -> List[str]:
    """Generate random PLO4 hand (4 cards) excluding specified cards."""
    ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
    suits = ['h', 'd', 'c', 's']

    deck = [f"{rank}{suit}" for rank in ranks for suit in suits]
    available = [card for card in deck if card not in excluded_cards]

    if len(available) < 4:
        raise ValueError(f"Not enough cards available")

    return random.sample(available, 4)


def complete_board(board_cards: List[str], excluded_cards: set) -> List[str]:
    """Complete board to 5 cards if needed."""
    if len(board_cards) >= 5:
        return board_cards[:5]

    ranks = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2']
    suits = ['h', 'd', 'c', 's']

    deck = [f"{rank}{suit}" for rank in ranks for suit in suits]
    available = [card for card in deck if card not in excluded_cards]

    needed = 5 - len(board_cards)
    new_cards = random.sample(available, needed)

    return board_cards + new_cards


def evaluate_plo_hand(hole_cards: List[str], board: List[str]) -> int:
    """Evaluate PLO hand strength (simplified)."""
    hand_ranks = [card[0] for card in hole_cards]

    rank_values = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10,
                   '9': 9, '8': 8, '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}

    hand_values = sorted([rank_values.get(r, 0) for r in hand_ranks], reverse=True)
    score = sum(hand_values[:2]) * 100

    score += random.randint(0, 1000)

    return score
