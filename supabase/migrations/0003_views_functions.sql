-- LLAVE public surface. DRAFT, not executed.
-- Views run as their owner (security_invoker = false, the default) ON PURPOSE: they are the only door
-- for anon, and they hard-code exactly which rows and columns leave the building.
-- Never add internal_note, commission_pct, ghl_location_id, first_reply* to any of them.

-- Exact street/ext_number/lat/lng leave only when show_exact_location; otherwise blanked.
create or replace view public.public_listings as
select l.id, l.agency_id, a.slug as agency_slug, l.ref, l.slug, l.status, l.operation, l.property_type,
       l.title, l.description, l.price_cents, l.currency, l.price_date, l.maintenance_cents,
       l.m2_built, l.m2_land, l.bedrooms, l.bathrooms, l.parking, l.floor, l.year_built,
       l.furnished, l.pets, l.amenities,
       case when l.show_exact_location then l.street     end as street,
       case when l.show_exact_location then l.ext_number end as ext_number,
       l.colonia, l.municipio, l.estado, l.cp,
       case when l.show_exact_location then l.lat end as lat,
       case when l.show_exact_location then l.lng end as lng,
       l.show_exact_location, l.share_in_bolsa, l.share_split_pct, l.rentapoliza_offer, l.updated_at
  from public.listings l join public.agencies a on a.id = l.agency_id
 where l.status in ('activa','apartada');

-- Listings an agency site shows through an ACTIVE Bolsa share (mirror of public_listing_ids second query).
create or replace view public.public_shared_listings as
select s.sharing_agency_id as site_agency_id, sa.slug as site_agency_slug, s.split_pct, pl.*
  from public.shares s
  join public.public_listings pl on pl.id = s.listing_id and pl.share_in_bolsa
  join public.agencies sa on sa.id = s.sharing_agency_id
 where s.status = 'activa';

create or replace view public.public_photos as
select p.id, p.listing_id, p.position, p.width, p.height, p.sizes, p.alt
  from public.photos p join public.public_listings pl on pl.id = p.listing_id;

create or replace view public.public_agencies as
select a.id, a.slug, a.name, a.tagline, a.whatsapp,
       case when a.email_public then a.email end as email,
       a.city, a.logo_path, a.design, a.accent, a.about, a.plan,
       case when a.domain_verified_at is not null then a.custom_domain end as custom_domain
  from public.agencies a;  -- demo agencies are public on purpose (sales demo)

-- Bolsa catalogue for logged-in agencies: other agencies' opted-in listings.
create or replace view public.bolsa_listings as
select pl.*, l.share_split_pct as offered_split_pct
  from public.listings l
  join public.public_listings pl on pl.id = l.id
 where l.share_in_bolsa
   and l.agency_id <> public.current_agency_id()
   and public.current_agency_id() is not null;

revoke all on public.public_listings, public.public_shared_listings, public.public_photos,
              public.public_agencies, public.bolsa_listings from public, anon, authenticated;
grant select on public.public_listings, public.public_shared_listings, public.public_photos,
                public.public_agencies to anon, authenticated;
grant select on public.bolsa_listings to authenticated;

-- ------------------------------------------------------------------ submit_lead (the only lead door)
create or replace function public.submit_lead(
  p_agency_slug text, p_listing_id bigint, p_name text, p_phone text, p_email text,
  p_message text, p_consent boolean, p_website text default null   -- p_website = honeypot, must stay empty
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_agency   public.agencies%rowtype;
  v_owner    bigint;
  v_source   text := 'sitio';
  v_phone    text;
  v_email    text := lower(btrim(coalesce(p_email, '')));
  v_name     text := btrim(coalesce(p_name, ''));
  v_msg      text := btrim(coalesce(p_message, ''));
  v_dup      bigint;
  v_id       bigint;
begin
  if coalesce(btrim(p_website), '') <> '' then            -- bot: pretend success, store nothing
    return jsonb_build_object('ok', true, 'id', null, 'duplicate', false);
  end if;
  if not coalesce(p_consent, false) then
    raise exception 'Debes aceptar el aviso de privacidad para enviar tu solicitud.' using errcode = 'P0001';
  end if;
  select * into v_agency from public.agencies where slug = lower(btrim(coalesce(p_agency_slug, '')));
  if not found then raise exception 'Agencia no encontrada.' using errcode = 'P0002'; end if;

  v_phone := regexp_replace(coalesce(p_phone, ''), '[^0-9+]', '', 'g');   -- TODO: full parity with whatsapp.norm_phone
  if v_phone = '' then v_phone := null; end if;
  if v_phone is null and v_email = '' then
    raise exception 'Necesitamos un teléfono o un correo para contactarte.' using errcode = 'P0001';
  end if;
  if v_email <> '' and v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
    raise exception 'El correo no parece válido.' using errcode = 'P0001';
  end if;
  if char_length(v_name) > 200 or char_length(v_msg) > 4000 then
    raise exception 'Texto demasiado largo.' using errcode = 'P0001';
  end if;

  if p_listing_id is not null then
    select agency_id into v_owner from public.listings
     where id = p_listing_id and status in ('activa','apartada');
    if not found then raise exception 'La propiedad no existe.' using errcode = 'P0002'; end if;
    if v_owner <> v_agency.id then                       -- must be an active Bolsa share on this site
      if not exists (select 1 from public.shares s join public.listings l on l.id = s.listing_id
                      where s.listing_id = p_listing_id and s.sharing_agency_id = v_agency.id
                        and s.status = 'activa' and l.share_in_bolsa) then
        raise exception 'La propiedad no está disponible en este sitio.' using errcode = 'P0002';
      end if;
      v_source := 'bolsa';
    end if;
  else
    v_owner := v_agency.id;
  end if;

  if v_phone is not null and (select count(*) from public.leads
        where phone = v_phone and created_at > now() - interval '1 hour') >= 5 then
    raise exception 'Demasiadas solicitudes. Intenta más tarde.' using errcode = 'P0001';
  end if;

  select id into v_dup from public.leads
   where agency_id = v_agency.id and listing_id is not distinct from p_listing_id
     and created_at >= now() - interval '10 minutes'
     and ((v_phone is not null and phone = v_phone) or (v_email <> '' and email = v_email))
   order by id limit 1;
  if found then return jsonb_build_object('ok', true, 'id', v_dup, 'duplicate', true); end if;

  insert into public.leads(agency_id, owner_agency_id, listing_id, name, phone, email, message, source, consent)
  values (v_agency.id, v_owner, p_listing_id, v_name, v_phone, v_email, v_msg, v_source, true)
  returning id into v_id;
  -- Blocklist (llave/ghl.is_blocked) and GHL outbox queueing stay in the Python worker, which polls
  -- leads where ghl_status = 'pendiente'.
  return jsonb_build_object('ok', true, 'id', v_id, 'duplicate', false);
end $$;

revoke all on function public.submit_lead(text,bigint,text,text,text,text,boolean,text) from public;
grant execute on function public.submit_lead(text,bigint,text,text,text,text,boolean,text) to anon, authenticated;

-- ------------------------------------------------------------------ Storage (configure in Supabase; policies via dashboard/CLI)
-- bucket  listing-photos : public = true (public read by URL), file_size_limit ~ 15MB, mime image/jpeg|webp|png
-- key layout             : <agency_id>/<sha[:2]>/<sha>/<size>.jpg   (agency_id prefix is NEW vs local layout)
-- write policy (storage.objects), authenticated only:
--   insert/update/delete  using/with check
--     bucket_id = 'listing-photos' and (storage.foldername(name))[1] = public.current_agency_id()::text
-- no select policy needed for public buckets; do not allow listing the bucket (no list for anon).
-- Resizing worker uses the service role and writes the same prefix.
