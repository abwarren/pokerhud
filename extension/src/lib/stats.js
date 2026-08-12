/* ── PokerBet HUD: Poker Stats Calculator ── */

/**
 * All stat calculations are sample-size-aware.
 * A stat with too few hands defaults to null (not shown).
 */
export const MIN_HANDS = {
  vpip: 5, pfr: 5, threeBet: 10, af: 5,
  wtsd: 10, wsd: 10, cbet: 10, foldToCbet: 10,
  steal: 20, fourBet: 20, squeeze: 20,
};

/**
 * Player stats accumulator.
 * Feed it hand records; it produces aggregated stats.
 */
export class StatsEngine {
  constructor() {
    this.hands = [];           // raw hand records
    this.playerMap = {};       // playerName -> PlayerStat
  }

  /** Add a single hand record from the scraper */
  ingest(hand) {
    this.hands.push(hand);
    for (const action of hand.actions || []) {
      this._recordAction(action, hand);
    }
  }

  _recordAction(action, hand) {
    const name = action.player;
    if (!name) return;
    if (!this.playerMap[name]) this.playerMap[name] = new PlayerStat(name);
    this.playerMap[name].record(action, hand);
  }

  /** Get computed stats for a player */
  getStats(playerName) {
    const ps = this.playerMap[playerName];
    if (!ps) return null;
    return ps.compute();
  }

  /** All known players */
  getPlayers() {
    return Object.keys(this.playerMap).sort();
  }
}

export class PlayerStat {
  constructor(name) {
    this.name = name;
    this.totalHands = 0;
    this.vpipCount = 0;
    this.pfrCount = 0;
    this.threeBetCount = 0;
    this.threeBetOpportunities = 0;
    this.foldCount = 0;
    this.callCount = 0;
    this.raiseCount = 0;
    this.wentToShowdown = 0;
    this.wonAtShowdown = 0;
    this.showdownHands = 0;
    this.cbetOpportunities = 0;
    this.cbetMade = 0;
    this.foldToCbetOpportunities = 0;
    this.foldToCbet = 0;
    this.stealOpportunities = 0;
    this.stealAttempted = 0;
    this.fourBetOpportunities = 0;
    this.fourBetMade = 0;
    this.positions = {}; // position -> {vpip, pfr, hands}
  }

  /** Record one player action */
  record(action, hand) {
    this.totalHands++;

    // VPIP: voluntarily put money in preflop
    if (['call', 'raise', 'bet'].includes(action.type) && action.street === 'preflop') {
      // Don't count blinds as VPIP unless there was a raise before them
      if (!action.isBlind) this.vpipCount++;
    }

    // PFR: raised preflop
    if (action.type === 'raise' && action.street === 'preflop') {
      this.pfrCount++;
    }

    // 3-Bet: re-raised preflop after a raise
    if (action.type === 'raise' && action.street === 'preflop' && action.isThreeBet) {
      this.threeBetCount++;
    }
    if (action.isThreeBetOpportunity) {
      this.threeBetOpportunities++;
    }

    // Aggression factor
    if (action.type === 'fold') this.foldCount++;
    else if (action.type === 'call') this.callCount++;
    else if (['raise', 'bet'].includes(action.type)) this.raiseCount++;

    // Showdown
    if (action.street === 'showdown') {
      this.showdownHands++;
      this.wentToShowdown++;
      if (action.won) this.wonAtShowdown++;
    }

    // C-Bet
    if (action.isCbetOpportunity) this.cbetOpportunities++;
    if (action.isCbet) this.cbetMade++;
    if (action.isFoldToCbetOpportunity) this.foldToCbetOpportunities++;
    if (action.isFoldToCbet) this.foldToCbet++;

    // Steal
    if (action.isStealOpportunity) this.stealOpportunities++;
    if (action.isStealAttempt) this.stealAttempted++;

    // 4-Bet
    if (action.isFourBetOpportunity) this.fourBetOpportunities++;
    if (action.isFourBet) this.fourBetMade++;

    // Positional
    const pos = action.position || 'unknown';
    if (!this.positions[pos]) this.positions[pos] = { vpip: 0, pfr: 0, hands: 0 };
    this.positions[pos].hands++;
    if (['call', 'raise', 'bet'].includes(action.type) && action.street === 'preflop' && !action.isBlind) {
      this.positions[pos].vpip++;
    }
    if (action.type === 'raise' && action.street === 'preflop') {
      this.positions[pos].pfr++;
    }
  }

  compute() {
    const pct = (num, den) => (den > 0 ? Math.round((num / den) * 1000) / 10 : null);

    return {
      name: this.name,
      hands: this.totalHands,
      vpip: pct(this.vpipCount, this.totalHands),
      pfr: pct(this.pfrCount, this.totalHands),
      threeBet: pct(this.threeBetCount, this.threeBetOpportunities),
      af: this.callCount + this.raiseCount > 0
        ? Math.round((this.raiseCount / (this.callCount || 1)) * 100) / 100
        : null,
      wtsd: pct(this.wentToShowdown, this.totalHands),
      wsd: pct(this.wonAtShowdown, this.showdownHands),
      cbet: pct(this.cbetMade, this.cbetOpportunities),
      foldToCbet: pct(this.foldToCbet, this.foldToCbetOpportunities),
      steal: pct(this.stealAttempted, this.stealOpportunities),
      fourBet: pct(this.fourBetMade, this.fourBetOpportunities),
      positions: this.positions,
    };
  }
}
