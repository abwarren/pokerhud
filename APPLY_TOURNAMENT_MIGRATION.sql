-- ============================================================
-- PokerBet Tournament Schema Migration
-- ============================================================
-- Run this in Supabase SQL Editor:
-- https://supabase.com/dashboard/project/kzqrdtagpykoylhuqcyv/sql/new
-- ============================================================

-- ============================================================
-- PokerBet Tournament Schema
-- ============================================================
-- Stores scraped tournament data from pokerbet.co.za
-- BetConstruct Skillgames platform, Partner ID: 18751019
-- ============================================================

-- Tournament types enum
create type tournament_type as enum (
  'freezeout',
  'freeroll',
  'satellite',
  'knockout',
  'mystery_bounty',
  'sit_and_go',
  'spin_and_go',
  'other'
);

-- Tournament status enum
create type tournament_status as enum (
  'announced',
  'registering',
  'late_registration',
  'running',
  'on_break',
  'completed',
  'canceled'
);

-- Game variant enum
create type game_variant as enum (
  'holdem',
  'omaha_4',
  'omaha_5',
  'omaha_6',
  'other'
);

-- ============================================================
-- Core tables
-- ============================================================

-- Tournaments: scraped tournament listings
create table tournaments (
  id bigint generated always as identity primary key,
  external_id text unique,
  name text not null,
  tournament_type tournament_type not null default 'other',
  game_variant game_variant not null default 'holdem',
  status tournament_status not null default 'announced',

  -- Buy-in structure (ZAR)
  buy_in numeric(12,2),
  rake numeric(12,2),
  total_entry numeric(12,2),
  rebuy_amount numeric(12,2),
  addon_amount numeric(12,2),
  bounty_amount numeric(12,2),

  -- Prize
  guarantee numeric(12,2),
  prize_pool numeric(12,2),
  currency text not null default 'ZAR',

  -- Schedule
  start_time timestamptz,
  late_reg_until timestamptz,
  end_time timestamptz,
  recurrence text,

  -- Structure
  starting_chips integer,
  blind_levels jsonb,
  max_players integer,
  registered_players integer default 0,
  remaining_players integer,
  current_level integer,

  -- Satellite info
  qualifies_for_id bigint references tournaments(id),
  tickets_awarded integer,

  -- Meta
  source text not null default 'scraper',
  raw_data jsonb,
  scraped_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Tournament results
create table tournament_results (
  id bigint generated always as identity primary key,
  tournament_id bigint not null references tournaments(id) on delete cascade,
  player_name text not null,
  finish_position integer not null,
  prize_amount numeric(12,2),
  bounties_won integer default 0,
  bounty_earnings numeric(12,2) default 0,
  rebuys integer default 0,
  addons integer default 0,
  created_at timestamptz not null default now(),

  unique(tournament_id, player_name)
);

-- Scrape log
create table scrape_runs (
  id bigint generated always as identity primary key,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  source text not null,
  status text not null default 'running',
  tournaments_found integer default 0,
  tournaments_new integer default 0,
  tournaments_updated integer default 0,
  error_message text,
  metadata jsonb
);

-- Promotions from CMS
create table promotions (
  id bigint generated always as identity primary key,
  external_id integer unique,
  title text not null,
  content text,
  image_url text,
  category text default 'poker',
  is_active boolean not null default true,
  scraped_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Cash tables lobby snapshot
create table cash_tables (
  id bigint generated always as identity primary key,
  external_id text unique,
  name text not null,
  game_variant game_variant not null default 'omaha_4',
  stakes text,
  small_blind numeric(10,2),
  big_blind numeric(10,2),
  max_players integer,
  seated_players integer default 0,
  waiting_players integer default 0,
  average_pot numeric(12,2),
  currency text not null default 'ZAR',
  scraped_at timestamptz not null default now()
);

-- ============================================================
-- Indexes
-- ============================================================
create index idx_tournaments_status on tournaments(status);
create index idx_tournaments_start_time on tournaments(start_time);
create index idx_tournaments_type on tournaments(tournament_type);
create index idx_tournaments_scraped on tournaments(scraped_at);
create index idx_results_tournament on tournament_results(tournament_id);
create index idx_results_player on tournament_results(player_name);
create index idx_scrape_runs_started on scrape_runs(started_at);
create index idx_cash_tables_variant on cash_tables(game_variant);

-- ============================================================
-- Auto-update updated_at
-- ============================================================
create or replace function update_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger tournaments_updated_at
  before update on tournaments
  for each row execute function update_updated_at();

create trigger promotions_updated_at
  before update on promotions
  for each row execute function update_updated_at();

-- ============================================================
-- Row Level Security
-- ============================================================
alter table tournaments enable row level security;
alter table tournament_results enable row level security;
alter table scrape_runs enable row level security;
alter table promotions enable row level security;
alter table cash_tables enable row level security;

-- Public read access
create policy "Public read tournaments" on tournaments for select using (true);
create policy "Public read results" on tournament_results for select using (true);
create policy "Public read promotions" on promotions for select using (true);
create policy "Public read cash_tables" on cash_tables for select using (true);
create policy "Public read scrape_runs" on scrape_runs for select using (true);

-- Service role write access (scraper uses service_role key)
create policy "Service write tournaments" on tournaments for all using (true) with check (true);
create policy "Service write results" on tournament_results for all using (true) with check (true);
create policy "Service write scrape_runs" on scrape_runs for all using (true) with check (true);
create policy "Service write promotions" on promotions for all using (true) with check (true);
create policy "Service write cash_tables" on cash_tables for all using (true) with check (true);

-- ============================================================
-- Seed known tournament data from REST scrape
-- ============================================================
insert into promotions (external_id, title, content, category) values
  (109866, 'Sunday Slam R200k Guaranteed',
   'Begins at 6:00pm every Sunday, with a buy-in of R700+R70, and a guaranteed prize pool of R200,000. Satellites run from every Thursday through to Sunday afternoon for as little as R22.',
   'poker'),
  (646107, 'Weekly Rake Back Programme',
   'Receive 10% of your total rake paid back into your account every week. Min payout: R150, Max: R10,000. Paid every Monday by 15:00 UTC.',
   'poker')
on conflict (external_id) do nothing;

insert into tournaments (name, tournament_type, game_variant, buy_in, rake, total_entry, guarantee, currency, recurrence, source, status) values
  ('Sunday Slam', 'freezeout', 'holdem', 700, 70, 770, 200000, 'ZAR', 'weekly_sunday', 'rest_scrape', 'announced'),
  ('Sunday Slam Satellite', 'satellite', 'holdem', 22, 0, 22, null, 'ZAR', 'thu_to_sun', 'rest_scrape', 'announced');
