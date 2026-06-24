-- Throwaway local Postgres for the Story A Claude Code researcher (proposer).
-- A trimmed Join Order Benchmark / IMDB-shaped schema with enough rows that a
-- sequential scan is visibly slower than an index scan, but small enough that
-- CREATE INDEX builds in milliseconds. Swapped for Aiven / Story B's harness at
-- Phase 1 — the read-only MCP shape stays identical.

-- pg_stat_statements is preloaded via the server command flag; just register it.
create extension if not exists pg_stat_statements;

drop table if exists cast_info, movie_keyword, title, name, keyword, kind_type cascade;

create table kind_type (
  id   int primary key,
  kind text not null
);

create table title (
  id              int primary key,
  title           text not null,
  production_year int,
  kind_id         int references kind_type(id)
);

create table name (
  id   int primary key,
  name text not null
);

create table keyword (
  id      int primary key,
  keyword text not null
);

create table cast_info (
  id        int primary key,
  person_id int references name(id),
  movie_id  int references title(id),
  role_id   int,
  nr_order  int
);

create table movie_keyword (
  id         int primary key,
  movie_id   int references title(id),
  keyword_id int references keyword(id)
);

-- ---- data ----------------------------------------------------------------
insert into kind_type (id, kind)
values (1,'movie'),(2,'tv series'),(3,'video'),(4,'episode');

-- ~6000 titles spanning production years 1950..2020 (no index on production_year)
insert into title (id, title, production_year, kind_id)
select g,
       'title_' || g,
       1950 + (g % 71),
       1 + (g % 4)
from generate_series(1, 6000) g;

-- ~4000 people
insert into name (id, name)
select g, 'person_' || g
from generate_series(1, 4000) g;

-- ~600 keywords
insert into keyword (id, keyword)
select g, 'kw_' || g
from generate_series(1, 600) g;

-- ~30000 cast rows; movie_id spread across titles (no index on movie_id)
insert into cast_info (id, person_id, movie_id, role_id, nr_order)
select g,
       1 + (g % 4000),
       1 + (g % 6000),
       1 + (g % 12),
       1 + (g % 30)
from generate_series(1, 30000) g;

-- ~10000 movie/keyword links
insert into movie_keyword (id, movie_id, keyword_id)
select g,
       1 + (g % 6000),
       1 + (g % 600)
from generate_series(1, 10000) g;

analyze;

-- The "slow" workload query the researcher should diagnose: filters on
-- title.production_year and joins cast_info on movie_id — both unindexed, so
-- this is two sequential scans. Obvious index candidates:
--   title(production_year)  and/or  cast_info(movie_id)
-- (left here as a comment; Story B's benchmark owns actually running it.)
--
-- select t.id, t.title, count(*)
-- from title t join cast_info ci on ci.movie_id = t.id
-- where t.production_year between 2000 and 2005
-- group by t.id, t.title order by count(*) desc limit 20;

-- ---- read-only role for the MCP ------------------------------------------
-- The researcher connects as this role: SELECT-only, cannot mutate. This is the
-- declarative half of the "the researcher can't apply/score its own work" split
-- (the allowedTools whitelist is the other half).
drop role if exists researcher_ro;
create role researcher_ro login password 'readonly';
grant connect on database postgres to researcher_ro;
grant usage on schema public to researcher_ro;
grant select on all tables in schema public to researcher_ro;
alter default privileges in schema public grant select on tables to researcher_ro;
-- pg_stat_statements view access
grant pg_read_all_stats to researcher_ro;
