-- Live GHL sync (llave/ghl_live.py): retry counter + 'failed' status on the outbox. Mirrors the 0001 edit for databases already migrated.
alter table public.outbox add column if not exists attempts integer not null default 0;
alter table public.outbox drop constraint if exists outbox_status_chk;
alter table public.outbox add constraint outbox_status_chk check (status in ('dry_run','pending','sent','error','failed'));
