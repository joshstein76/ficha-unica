-- Fourth agent-site design 'loteria' (Josh 2026-11-03), and it becomes the default for NEW agencies (existing rows keep their design).
-- Mirrors the 0001 edit for databases already migrated (same pattern as 0004).
alter table public.agencies alter column design set default 'loteria';
alter table public.agencies drop constraint if exists agencies_design_chk;
alter table public.agencies add constraint agencies_design_chk check (design in ('loteria','ciudad','costa','residencia'));
